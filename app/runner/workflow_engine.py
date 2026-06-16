from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.screenshot import capture_screenshot
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

    모듈 종료 시 스크린샷 캡처도 이 골격이 시스템 무관하게 책임진다. 각 단계 함수는
    스크린샷을 직접 찍지 않으며, `execute_step` 이 단계 종료(성공·실패 공통) 직후
    `runtime.page` 로 `final.png` 를 남긴다(`app/runner/screenshot.py`). 사용자 입력
    대기(`WAITING_INPUT`)는 모듈 종료가 아니므로 캡처하지 않는다.

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
        artifact_dir = self._artifact_manager.module_dir(run_id, module.module_id)
        dialog_index = len(runtime.dialog_messages)

        status = ModuleStatus.PASSED
        message = ""
        last_error: str | None = None

        # 단계 실행 → 모듈 종료 시 스크린샷까지 모두 로그 리다이렉트 안에서 처리해
        # 캡처 과정의 로그도 execution.log / WebSocket 으로 함께 흘려보낸다.
        with log_path.open("w", encoding="utf-8") as log_file:
            tee = LineWriter(lambda line: write_log_line(line, emit_log, log_file))
            with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                try:
                    raw_message = self._run_step(runtime, module, artifact_dir)
                    if isinstance(raw_message, str) and raw_message.startswith(WAITING_INPUT_PREFIX):
                        status = ModuleStatus.WAITING_INPUT
                        message = raw_message.split("::", 1)[1]
                    else:
                        status = ModuleStatus.PASSED
                        message = raw_message
                except Exception as exc:
                    status = ModuleStatus.FAILED
                    message = str(exc)
                    last_error = str(exc)
                    print(f"[error] {exc}")

                # 모듈 종료(성공/실패 공통) 시 공용 스크린샷.
                # 입력 대기(WAITING_INPUT)는 모듈 종료가 아니라 일시정지이므로 건너뛴다.
                if status is not ModuleStatus.WAITING_INPUT:
                    capture_screenshot(runtime.page, screenshot_path)
                tee.flush()

        artifacts = [self._artifact_manager.relative_path(log_path)]
        if screenshot_path.exists():
            artifacts.append(self._artifact_manager.relative_path(screenshot_path))

        return StepExecutionResult(
            status=status,
            message=message,
            artifacts=artifacts,
            current_url=self._safe_page_url(runtime),
            dialog_messages=runtime.dialog_messages[dialog_index:],
            last_error=last_error,
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
    def _run_step(self, runtime: WorkflowRuntime, module: ModuleDefinition, artifact_dir: Path) -> str:
        """workflow_step 을 실제 단계 함수로 디스패치한다.

        `artifact_dir` 은 해당 모듈의 아티팩트 디렉터리(`artifacts/{run_id}/{module_id}`)이며,
        다운로드 등 파일 산출물이 필요한 단계만 사용한다. 스크린샷은 공용 엔진이 책임지므로
        단계 함수에 스크린샷 경로를 넘기지 않는다.
        """
        ...

    @abstractmethod
    def _shutdown_browser(self, runtime: WorkflowRuntime) -> None:
        ...
