from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Callable

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.runner import screenshot
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_common import LineWriter, StepExecutionResult, write_log_line

WAITING_INPUT_MARKER = "WAITING_INPUT::"


class BaseWorkflowExecutor:
    """모든 시스템 실행기의 공통 골격(템플릿 메서드).

    한 모듈을 실행할 때 모든 시스템이 동일하게 수행해야 하는 일을 한 곳에서 책임진다:

    - 모듈별 로그 파일 생성 및 stdout/stderr 캡처
    - **모듈 종료 시점(성공/실패/입력대기 모두)** 의 스크린샷 공통 촬영
    - 아티팩트(로그·스크린샷) 수집 및 ``StepExecutionResult`` 생성
    - 예외 처리 및 오류 로그 기록

    개별 step 모듈은 더 이상 스크린샷을 직접 찍지 않는다. 스크린샷은 이 클래스가
    ``_run_step`` 종료 직후(반환이든 예외든) 단 한 번 공통으로 촬영한다.

    서브클래스는 시스템별 부분만 구현한다:

    - ``_run_step(runtime, module, module_dir)``: 실제 자동화 단계 디스패치(문자열 반환)
    - ``_page(runtime)``: Playwright page 객체
    - ``_dialog_messages(runtime)``: 다이얼로그 메시지 리스트

    그리고 시스템마다 런타임 타입이 다르므로 ``build_runtime`` / ``close_runtime`` /
    (필요 시) ``update_otp_code`` 를 각자 정의한다.
    """

    execution_mode: str = ""

    def __init__(self, artifact_manager: ArtifactManager) -> None:
        self._artifact_manager = artifact_manager

    @staticmethod
    def _resolve_headless(input_data: dict[str, str]) -> bool:
        browser_mode = (input_data.get("browser_mode") or "headed").strip().lower()
        return browser_mode not in {"headed", "visible", "ui", "false", "0", "no"}

    def execute_step(
        self,
        runtime,
        run_id: str,
        module: ModuleDefinition,
        emit_log: Callable[[str], None],
    ) -> StepExecutionResult:
        log_path = self._artifact_manager.log_path(run_id, module.module_id)
        screenshot_path = self._artifact_manager.screenshot_path(run_id, module.module_id)
        module_dir = self._artifact_manager.module_dir(run_id, module.module_id)
        dialog_index = len(self._dialog_messages(runtime))
        writer = LineWriter(emit_log)

        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                tee = LineWriter(lambda line: write_log_line(line, emit_log, log_file))
                with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                    try:
                        message = self._run_step(runtime, module, module_dir)
                    finally:
                        # 성공/실패와 무관하게 모듈 종료 시점 화면을 공통 촬영한다.
                        self._capture_final_screenshot(runtime, screenshot_path)
            return self._build_success_result(message, runtime, screenshot_path, log_path, dialog_index)
        except Exception as exc:
            writer.flush()
            self._append_error_log(log_path, emit_log, exc)
            return self._build_failure_result(exc, runtime, screenshot_path, log_path, dialog_index)

    # ----- 서브클래스가 구현하는 훅 -----
    def _run_step(self, runtime, module: ModuleDefinition, module_dir: Path) -> str:
        raise NotImplementedError

    def _page(self, runtime):
        raise NotImplementedError

    def _dialog_messages(self, runtime) -> list[str]:
        raise NotImplementedError

    @staticmethod
    def update_otp_code(runtime, otp_code: str) -> None:
        # 기본값: OTP 대기가 없는 시스템(접속 점검 등)을 위한 no-op. 필요한 시스템이 재정의한다.
        return None

    # ----- 공통 헬퍼 -----
    def _capture_final_screenshot(self, runtime, screenshot_path: Path) -> None:
        try:
            screenshot.capture_screenshot(self._page(runtime), screenshot_path)
        except Exception as exc:
            print(f"[warn] 모듈 종료 스크린샷 캡처 실패: {exc}")

    def _collect_artifacts(self, screenshot_path: Path, log_path: Path) -> list[str]:
        artifacts = [self._artifact_manager.relative_path(log_path)]
        if screenshot_path.exists():
            artifacts.append(self._artifact_manager.relative_path(screenshot_path))
        return artifacts

    def _build_success_result(
        self,
        message: str,
        runtime,
        screenshot_path: Path,
        log_path: Path,
        dialog_index: int,
    ) -> StepExecutionResult:
        artifacts = self._collect_artifacts(screenshot_path, log_path)
        dialog_messages = self._dialog_messages(runtime)[dialog_index:]
        screenshot_artifact = screenshot_path if screenshot_path.exists() else None
        if isinstance(message, str) and message.startswith(WAITING_INPUT_MARKER):
            return StepExecutionResult(
                status=ModuleStatus.WAITING_INPUT,
                message=message.split("::", 1)[1],
                artifacts=artifacts,
                current_url=self._safe_page_url(runtime),
                dialog_messages=dialog_messages,
                screenshot_path=screenshot_artifact,
            )
        return StepExecutionResult(
            status=ModuleStatus.PASSED,
            message=message,
            artifacts=artifacts,
            current_url=self._safe_page_url(runtime),
            dialog_messages=dialog_messages,
            screenshot_path=screenshot_artifact,
        )

    def _build_failure_result(
        self,
        exc: Exception,
        runtime,
        screenshot_path: Path,
        log_path: Path,
        dialog_index: int,
    ) -> StepExecutionResult:
        artifacts = self._collect_artifacts(screenshot_path, log_path)
        return StepExecutionResult(
            status=ModuleStatus.FAILED,
            message=str(exc),
            artifacts=artifacts,
            current_url=self._safe_page_url(runtime),
            dialog_messages=self._dialog_messages(runtime)[dialog_index:],
            last_error=str(exc),
            screenshot_path=screenshot_path if screenshot_path.exists() else None,
        )

    @staticmethod
    def _append_error_log(log_path: Path, emit_log: Callable[[str], None], exc: Exception) -> None:
        if not log_path.exists():
            log_path.write_text("", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[error] {exc}\n")
        emit_log(f"[error] {exc}")

    def _safe_page_url(self, runtime) -> str | None:
        try:
            return str(self._page(runtime).url)
        except Exception:
            return None
