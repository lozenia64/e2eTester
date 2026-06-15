from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_common import LineWriter, StepExecutionResult, write_log_line
from app.systems.access_common import browser, main_access


@dataclass
class AccessRuntime:
    base_url: str
    mobile: bool
    playwright_manager: object
    context: object
    page: object
    dialog_messages: list[str]
    executor: ThreadPoolExecutor | None = None
    closed: bool = False


class AccessWorkflowExecutor:
    """메인화면 접속만 점검하는 단순 시스템들의 공용 실행기.

    각 시스템 executor 가 ``execution_mode``·``base_url``·모바일 여부를 주입한다.
    로그인/인증/OTP 단계가 없으므로 절대 ``WAITING_INPUT`` 으로 멈추지 않는다.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        *,
        execution_mode: str,
        system_code: str,
        base_url: str,
        mobile: bool,
    ) -> None:
        self._artifact_manager = artifact_manager
        self.execution_mode = execution_mode
        self._system_code = system_code
        self._base_url = browser.normalize_base_url(base_url, base_url)
        self._mobile = mobile

    @staticmethod
    def _resolve_headless(input_data: dict[str, str]) -> bool:
        browser_mode = (input_data.get("browser_mode") or "headed").strip().lower()
        return browser_mode not in {"headed", "visible", "ui", "false", "0", "no"}

    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> AccessRuntime:
        headless = self._resolve_headless(input_data)
        slow_mo = 250 if not headless else 0
        base_url = browser.normalize_base_url(input_data.get("base_url"), self._base_url)
        user_data_dir = browser.resolve_user_data_dir(f"{self._system_code}-chrome-profile")

        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        context = browser.launch_persistent_browser_context(playwright, headless, slow_mo, user_data_dir)
        page = context.pages[0] if context.pages else context.new_page()
        if self._mobile:
            browser.apply_mobile_device_mode(playwright, page)
        browser.grant_browser_permissions(context, base_url)
        page.set_default_timeout(browser.MAX_TIMEOUT_MS)
        page.set_default_navigation_timeout(browser.MAX_TIMEOUT_MS)
        dialog_messages = browser.add_dialog_logger(page)
        return AccessRuntime(
            base_url=base_url,
            mobile=self._mobile,
            playwright_manager=playwright_manager,
            context=context,
            page=page,
            dialog_messages=dialog_messages,
        )

    def execute_step(
        self,
        runtime: AccessRuntime,
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

    def close_runtime(self, runtime: AccessRuntime) -> None:
        if runtime.closed:
            return
        try:
            browser.shutdown_browser(runtime.page, runtime.context)
        finally:
            runtime.playwright_manager.__exit__(None, None, None)
            runtime.closed = True

    def _run_step(self, runtime: AccessRuntime, module: ModuleDefinition, screenshot_path: Path) -> str:
        if module.workflow_step == "main_access":
            message = main_access.run(runtime.page, runtime.base_url)
            browser.save_screenshot(runtime.page, screenshot_path)
            return message
        raise RuntimeError(f"Unsupported {self._system_code} workflow step: {module.workflow_step}")

    @staticmethod
    def update_otp_code(runtime: AccessRuntime, otp_code: str) -> None:
        # 접속 점검 시스템은 OTP 대기가 없으므로 호출될 일이 없다(인터페이스 호환용).
        return None

    @staticmethod
    def _safe_page_url(runtime: AccessRuntime) -> str | None:
        try:
            return str(runtime.page.url)
        except Exception:
            return None


def create_access_executor(
    artifact_manager: ArtifactManager,
    *,
    execution_mode: str,
    system_code: str,
    base_url: str,
    mobile: bool = False,
) -> AccessWorkflowExecutor:
    return AccessWorkflowExecutor(
        artifact_manager,
        execution_mode=execution_mode,
        system_code=system_code,
        base_url=base_url,
        mobile=mobile,
    )
