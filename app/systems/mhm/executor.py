from __future__ import annotations

import argparse
import contextlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_common import LineWriter, StepExecutionResult, write_log_line
from app.systems.mhm.steps import (
    compensation_cancel,
    compensation_charge,
    compensation_result,
    contract_detail,
    contract_list,
    kakao_login,
    login_common as common,
    login_move,
    long_term_policy_certificate,
    main_access,
    phone_login,
)


@dataclass
class MhmWorkflowRuntime:
    config: common.LoginConfig
    playwright_manager: object
    browser: object
    context: object
    page: object
    dialog_messages: list[str]
    executor: ThreadPoolExecutor | None = None
    phone_login_sms_requested: bool = False
    closed: bool = False


class MhmWorkflowExecutor:
    execution_mode = "mhm_workflow_step"

    def __init__(self, artifact_manager: ArtifactManager) -> None:
        self._artifact_manager = artifact_manager

    @staticmethod
    def _resolve_headless(input_data: dict[str, str]) -> bool:
        browser_mode = (input_data.get("browser_mode") or "headed").strip().lower()
        return browser_mode not in {"headed", "visible", "ui", "false", "0", "no"}

    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> MhmWorkflowRuntime:
        screenshot_path = self._artifact_manager.screenshot_path(run_id, module_id)
        headless = self._resolve_headless(input_data)
        args = argparse.Namespace(
            env_file=str(common.DEFAULT_ENV_FILE_PATH),
            auth_method=(input_data.get("auth_method") or "phone").strip().lower(),
            base_url=input_data.get("base_url") or common.DEFAULT_BASE_URL,
            name=input_data.get("name"),
            birthdate=input_data.get("birthdate"),
            gender=input_data.get("gender"),
            residency=input_data.get("residency"),
            carrier=input_data.get("carrier"),
            phone_number=input_data.get("phone_number"),
            phone_prefix=input_data.get("phone_prefix"),
            otp_code=input_data.get("otp_code"),
            headless=headless,
            slow_mo=250 if not headless else 0,
            timeout_ms=common.MAX_TIMEOUT_MS,
            success_stabilization_ms=common.MAX_TIMEOUT_MS,
            keep_open=False,
            post_login_fragment="/myh/mai/MySubMain1000",
            screenshot=str(screenshot_path),
        )
        config = common.build_config(args)
        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        context = common.launch_persistent_browser_context(playwright, config.headless, config.slow_mo)
        page = context.pages[0] if context.pages else context.new_page()
        common.apply_mobile_device_mode(playwright, page)
        common.grant_browser_permissions(context, config.base_url)
        page.set_default_timeout(config.timeout_ms)
        page.set_default_navigation_timeout(config.timeout_ms)
        dialog_messages = common.add_dialog_logger(page)
        return MhmWorkflowRuntime(
            config=config,
            playwright_manager=playwright_manager,
            browser=None,
            context=context,
            page=page,
            dialog_messages=dialog_messages,
        )

    def execute_step(
        self,
        runtime: MhmWorkflowRuntime,
        run_id: str,
        module: ModuleDefinition,
        emit_log: Callable[[str], None],
    ) -> StepExecutionResult:
        log_path = self._artifact_manager.log_path(run_id, module.module_id)
        screenshot_path = self._artifact_manager.screenshot_path(run_id, module.module_id)
        artifacts: list[str] = []
        writer = LineWriter(emit_log)
        dialog_index = len(runtime.dialog_messages)

        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                tee = LineWriter(lambda line: write_log_line(line, emit_log, log_file))
                with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                    message = self._run_step(runtime, module, screenshot_path)
            if isinstance(message, str) and message.startswith("WAITING_INPUT::"):
                artifacts.append(self._artifact_manager.relative_path(log_path))
                if screenshot_path.exists():
                    artifacts.append(self._artifact_manager.relative_path(screenshot_path))
                return StepExecutionResult(
                    status=ModuleStatus.WAITING_INPUT,
                    message=message.split("::", 1)[1],
                    artifacts=artifacts,
                    current_url=self._safe_page_url(runtime),
                    dialog_messages=runtime.dialog_messages[dialog_index:],
                    screenshot_path=screenshot_path if screenshot_path.exists() else None,
                )
            artifacts.append(self._artifact_manager.relative_path(log_path))
            if screenshot_path.exists():
                artifacts.append(self._artifact_manager.relative_path(screenshot_path))
            return StepExecutionResult(
                status=ModuleStatus.PASSED,
                message=message,
                artifacts=artifacts,
                current_url=self._safe_page_url(runtime),
                dialog_messages=runtime.dialog_messages[dialog_index:],
                screenshot_path=screenshot_path if screenshot_path.exists() else None,
            )
        except Exception as exc:
            writer.flush()
            if not log_path.exists():
                log_path.write_text("", encoding="utf-8")
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"[error] {exc}\n")
            emit_log(f"[error] {exc}")
            artifacts.append(self._artifact_manager.relative_path(log_path))
            if screenshot_path.exists():
                artifacts.append(self._artifact_manager.relative_path(screenshot_path))
            return StepExecutionResult(
                status=ModuleStatus.FAILED,
                message=str(exc),
                artifacts=artifacts,
                current_url=self._safe_page_url(runtime),
                dialog_messages=runtime.dialog_messages[dialog_index:],
                last_error=str(exc),
                screenshot_path=screenshot_path if screenshot_path.exists() else None,
            )

    def close_runtime(self, runtime: MhmWorkflowRuntime) -> None:
        if runtime.closed:
            return
        try:
            common.shutdown_browser(runtime.page, runtime.context, runtime.browser)
        finally:
            runtime.playwright_manager.__exit__(None, None, None)
            runtime.closed = True

    def _run_step(self, runtime: MhmWorkflowRuntime, module: ModuleDefinition, screenshot_path: Path) -> str:
        if module.workflow_step == "main_access":
            return main_access.run(runtime.page, runtime.config)

        if module.workflow_step == "login":
            if runtime.config.auth_method == "kakao":
                login_move.run(runtime.page)
                return kakao_login.run(
                    runtime.page,
                    runtime.config,
                    runtime.dialog_messages,
                    screenshot_path,
                )
            if not runtime.phone_login_sms_requested:
                login_move.run(runtime.page)
                message = phone_login.request_sms(runtime.page, runtime.config, runtime.dialog_messages)
                runtime.phone_login_sms_requested = True
                if not runtime.config.otp_code:
                    return f"WAITING_INPUT::{message}"
            return phone_login.submit_otp_and_login(
                runtime.page,
                runtime.config,
                runtime.dialog_messages,
                screenshot_path,
            )

        if module.workflow_step == "contract_list":
            return contract_list.run(runtime.page, runtime.config, screenshot_path)

        if module.workflow_step == "contract_detail":
            return contract_detail.run(runtime.page, runtime.config, screenshot_path)

        if module.workflow_step == "compensation_charge":
            return compensation_charge.run(runtime.page, runtime.config, screenshot_path)

        if module.workflow_step == "compensation_result":
            return compensation_result.run(runtime.page, runtime.config, screenshot_path)

        if module.workflow_step == "compensation_cancel":
            return compensation_cancel.run(runtime.page, runtime.config, screenshot_path)

        if module.workflow_step == "long_term_policy_certificate":
            return long_term_policy_certificate.run(
                runtime.page,
                runtime.config,
                screenshot_path,
                runtime.dialog_messages,
            )

        raise RuntimeError(f"Unsupported MHM workflow step: {module.workflow_step}")

    @staticmethod
    def update_otp_code(runtime: MhmWorkflowRuntime, otp_code: str) -> None:
        runtime.config = replace(runtime.config, otp_code=otp_code)

    @staticmethod
    def _safe_page_url(runtime: MhmWorkflowRuntime) -> str | None:
        try:
            return str(runtime.page.url)
        except Exception:
            return None


def create_executor(artifact_manager: ArtifactManager) -> MhmWorkflowExecutor:
    return MhmWorkflowExecutor(artifact_manager)
