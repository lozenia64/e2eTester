from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import hom_login_common as common
import hom_contract_list
import hom_login_move
import hom_main_access
import hom_phone_login

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager


@dataclass
class HomWorkflowRuntime:
    config: common.LoginConfig
    playwright_manager: object
    browser: object
    context: object
    page: object
    dialog_messages: list[str]
    phone_login_sms_requested: bool = False
    closed: bool = False


@dataclass(frozen=True)
class StepExecutionResult:
    status: ModuleStatus
    message: str
    artifacts: list[str]
    current_url: str | None
    dialog_messages: list[str]
    last_error: str | None = None
    screenshot_path: Path | None = None

    @classmethod
    def failure(
        cls,
        message: str,
        current_url: str | None,
        dialog_messages: list[str],
        last_error: str | None,
        screenshot_path: Path | None = None,
    ) -> "StepExecutionResult":
        return cls(
            status=ModuleStatus.FAILED,
            message=message,
            artifacts=[],
            current_url=current_url,
            dialog_messages=dialog_messages,
            last_error=last_error,
            screenshot_path=screenshot_path,
        )


class _LineWriter(io.TextIOBase):
    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            stripped = line.rstrip()
            if stripped:
                self._emit(stripped)
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            self._emit(self._buffer.strip())
        self._buffer = ""


class HomWorkflowExecutor:
    def __init__(self, artifact_manager: ArtifactManager) -> None:
        self._artifact_manager = artifact_manager

    @staticmethod
    def _resolve_headless(input_data: dict[str, str]) -> bool:
        browser_mode = (input_data.get("browser_mode") or "headed").strip().lower()
        return browser_mode not in {"headed", "visible", "ui", "false", "0", "no"}

    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> HomWorkflowRuntime:
        screenshot_path = self._artifact_manager.screenshot_path(run_id, module_id)
        headless = self._resolve_headless(input_data)
        args = argparse.Namespace(
            env_file=str(common.DEFAULT_ENV_FILE_PATH),
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
            post_login_fragment="/my/main.do",
            screenshot=str(screenshot_path),
        )
        config = common.build_config(args)
        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        browser = common.launch_browser(playwright, config.headless, config.slow_mo)
        context = browser.new_context(viewport={"width": 1440, "height": 1200}, locale="ko-KR")
        common.configure_browser_context(context)
        common.grant_browser_permissions(context, config.base_url)
        page = context.new_page()
        page.set_default_timeout(config.timeout_ms)
        page.set_default_navigation_timeout(config.timeout_ms)
        dialog_messages = common.add_dialog_logger(page)
        return HomWorkflowRuntime(
            config=config,
            playwright_manager=playwright_manager,
            browser=browser,
            context=context,
            page=page,
            dialog_messages=dialog_messages,
        )

    def execute_step(
        self,
        runtime: HomWorkflowRuntime,
        run_id: str,
        module: ModuleDefinition,
        emit_log: Callable[[str], None],
    ) -> StepExecutionResult:
        log_path = self._artifact_manager.log_path(run_id, module.module_id)
        screenshot_path = self._artifact_manager.screenshot_path(run_id, module.module_id)
        artifacts: list[str] = []
        writer = _LineWriter(emit_log)
        dialog_index = len(runtime.dialog_messages)

        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                tee = _LineWriter(lambda line: self._write_log_line(line, emit_log, log_file))
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

    def close_runtime(self, runtime: HomWorkflowRuntime) -> None:
        if runtime.closed:
            return
        try:
            common.shutdown_browser(runtime.page, runtime.context, runtime.browser)
        finally:
            runtime.playwright_manager.__exit__(None, None, None)
            runtime.closed = True

    def _run_step(self, runtime: HomWorkflowRuntime, module: ModuleDefinition, screenshot_path: Path) -> str:
        if module.workflow_step == "main_access":
            return hom_main_access.run(runtime.page, runtime.config)

        if module.workflow_step == "login_move":
            return hom_login_move.run(runtime.page)

        if module.workflow_step == "phone_login":
            if not runtime.phone_login_sms_requested:
                message = hom_phone_login.request_sms(runtime.page, runtime.config, runtime.dialog_messages)
                runtime.phone_login_sms_requested = True
                if not runtime.config.otp_code:
                    return f"WAITING_INPUT::{message}"
            return hom_phone_login.submit_otp_and_login(
                runtime.page,
                runtime.config,
                runtime.dialog_messages,
                screenshot_path,
            )

        if module.workflow_step == "contract_list":
            return hom_contract_list.run(runtime.page, runtime.config, screenshot_path)

        raise RuntimeError(f"Unsupported HOM workflow step: {module.workflow_step}")

    @staticmethod
    def _write_log_line(line: str, emit_log: Callable[[str], None], log_file) -> None:
        stripped = line.rstrip()
        if not stripped:
            return
        log_file.write(stripped + "\n")
        log_file.flush()
        emit_log(stripped)

    @staticmethod
    def update_otp_code(runtime: HomWorkflowRuntime, otp_code: str) -> None:
        runtime.config = replace(runtime.config, otp_code=otp_code)

    @staticmethod
    def _safe_page_url(runtime: HomWorkflowRuntime) -> str | None:
        try:
            return str(runtime.page.url)
        except Exception:
            return None