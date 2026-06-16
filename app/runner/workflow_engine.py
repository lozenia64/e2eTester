from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_common import LineWriter, StepExecutionResult, write_log_line

# 단계 모듈이 OTP 등 사용자 입력 대기로 Run 을 일시정지시킬 때 쓰는 in-band 표식.
# (반환 문자열이 이 프리픽스로 시작하면 WAITING_INPUT 으로 해석한다.)
WAITING_INPUT_PREFIX = "WAITING_INPUT::"


@runtime_checkable
class WorkflowRuntime(Protocol):
    """모든 시스템 런타임이 만족해야 하는 최소 계약.

    공용 실행 엔진(`BaseWorkflowExecutor`)이 시스템에 무관하게 의존하는 속성만 선언한다.
    각 시스템의 구체 런타임 dataclass 는 이 외에 시스템 전용 필드(config, base_url 등)를
    자유롭게 추가한다.
    """

    playwright_manager: object
    context: object
    page: object
    dialog_messages: list[str]
    executor: object | None
    closed: bool


class BaseWorkflowExecutor(ABC):
    """Playwright 기반 시스템 실행기의 공용 골격.

    시스템과 무관한 실행 메커니즘 — 로그 캡처(stdout/stderr tee),
    아티팩트 수집, 예외→`StepExecutionResult` 변환, OTP 일시정지 해석,
    브라우저 종료 보호 — 을 한곳에서 소유한다.

    시스템별 차이는 추상 메서드로만 표현한다.
    - `execution_mode` : manifest 의 `execution_mode` 와 매칭되는 식별자
    - `build_runtime`   : 브라우저/페이지 기동 (시스템 전용)
    - `_run_step`       : workflow_step → 실제 단계 함수 디스패치 (시스템 전용)
    - `_shutdown_browser`: 브라우저 종료 호출 (시그니처가 시스템마다 다름)
    """

    execution_mode: str

    def __init__(self, artifact_manager: ArtifactManager) -> None:
        self._artifact_manager = artifact_manager

    @staticmethod
    def _resolve_headless(input_data: dict[str, str]) -> bool:
        browser_mode = (input_data.get("browser_mode") or "headed").strip().lower()
        return browser_mode not in {"headed", "visible", "ui", "false", "0", "no"}

    def execute_step(
        self,
        runtime: WorkflowRuntime,
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
            if isinstance(message, str) and message.startswith(WAITING_INPUT_PREFIX):
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

    def close_runtime(self, runtime: WorkflowRuntime) -> None:
        if runtime.closed:
            return
        try:
            self._shutdown_browser(runtime)
        finally:
            runtime.playwright_manager.__exit__(None, None, None)
            runtime.closed = True

    def update_otp_code(self, runtime: WorkflowRuntime, otp_code: str) -> None:
        """OTP 코드를 런타임에 반영한다.

        OTP 대기가 없는 시스템(접속 점검 등)은 기본 no-op 이며, 인증 단계가 있는
        시스템(HOM/MHM)이 오버라이드한다.
        """
        return None

    @staticmethod
    def _safe_page_url(runtime: WorkflowRuntime) -> str | None:
        try:
            return str(runtime.page.url)
        except Exception:
            return None

    @abstractmethod
    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> WorkflowRuntime:
        ...

    @abstractmethod
    def _run_step(self, runtime: WorkflowRuntime, module: ModuleDefinition, screenshot_path: Path) -> str:
        ...

    @abstractmethod
    def _shutdown_browser(self, runtime: WorkflowRuntime) -> None:
        ...
