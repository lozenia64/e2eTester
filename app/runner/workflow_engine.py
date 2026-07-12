from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.contexts.healing.models import HealingAttempt
from app.contexts.healing.page_proxy import HealedPage
from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition
from app.platform.artifact_manager import ArtifactManager
from app.runner.screenshot import capture_screenshot
from app.runner.step_logging import pop_sink, push_sink
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_common import StepExecutionResult, write_log_line

if TYPE_CHECKING:
    from app.automation.ports import AutomationPort
    from app.contexts.healing.engine import SelfHealingEngine


@runtime_checkable
class WorkflowRuntime(Protocol):
    """모든 시스템 런타임이 만족해야 하는 최소 계약.

    공용 실행 엔진(`BaseWorkflowExecutor`)이 시스템에 무관하게 의존하는 속성만 선언한다.
    각 시스템의 구체 런타임 dataclass 는 이 외에 시스템 전용 필드(config, base_url 등)를
    자유롭게 추가한다.

    **인프라 관심사는 여기 없다.** 실행 스레드 풀은 게이트웨이 세션(`LocalExecutionGateway`)이
    소유하며, 더 이상 런타임에 ``executor`` 로 매달리지 않는다(도메인 런타임은 자기 브라우저
    상태만 안다).
    """

    playwright_manager: object
    context: object
    page: object
    dialog_messages: list[str]
    closed: bool


@dataclass(frozen=True)
class StepContext:
    """단계 핸들러에 넘기는 실행 **능력(capability) 인터페이스**.

    핸들러가 전역(stdout)·런타임 내부를 직접 들쑤시지 않고, 필요한 능력을 이 컨텍스트에서만
    꺼내 쓰도록 한다:

    - ``page`` / ``dialog_messages`` : 모든 런타임이 만족하는 ``WorkflowRuntime`` 계약을 통해
      노출되는 공통 능력(핸들러가 ``ctx.runtime`` 을 구체 타입으로 캐스팅하지 않아도 된다).
    - ``log``                        : 단계 로그 한 줄을 흘려보내는 **명시적 로깅 능력**.
      과거에는 단계가 ``print()`` 하면 엔진이 **프로세스 전역** stdout 을 가로채는 암묵적
      계약이었고, 이는 동시 실행 스텝 스레드 사이에서 경합했다. 이제 엔진이 스텝별 로그 싱크를
      ``StepContext.log`` 로 주입하고, PageObject 는 ``print()`` 대신 컨텍스트-로컬
      ``app.runner.step_logging.log`` 를 호출한다(둘 다 같은 싱크로 모인다, 전역 stdout 미접촉).
    - ``artifact_dir``               : 다운로드 등 파일 산출물이 필요한 단계만 사용.

    ``runtime`` 은 시스템 전용 상태(config 등)가 필요한 핸들러를 위해 그대로 노출하되, 공통
    능력은 위 접근자로 쓰는 것을 권장한다. ``log`` 는 엔진이 **필수 주입**한다(기본값 없음 —
    싱크 없는 로그 유실을 타입 수준에서 막는다).
    """

    runtime: WorkflowRuntime
    module: ModuleDefinition
    artifact_dir: Path
    log: Callable[[str], None]

    @property
    def page(self) -> object:
        return self.runtime.page

    @property
    def dialog_messages(self) -> list[str]:
        return self.runtime.dialog_messages


# workflow_step → 단계 핸들러. 핸들러는 컨텍스트를 받아 타입드 결과를 돌려준다(문자열·매직
# 프리픽스 없음). 새 단계 = 레지스트리에 한 줄 등록(거대한 if/elif 디스패치 폐기, OCP).
StepHandler = Callable[[StepContext], StepOutcome]


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
    - `execution_mode`     : manifest 의 `execution_mode` 와 매칭되는 식별자
    - `build_runtime`      : 브라우저/페이지 기동 (시스템 전용)
    - `build_step_registry`: workflow_step → 단계 핸들러 매핑 (시스템 전용; if/elif 대체)
    - `_shutdown_browser`  : 브라우저 종료 호출 (시그니처가 시스템마다 다름)

    단계 디스패치는 더 이상 각 실행기의 ``_run_step`` if/elif 체인이 아니라, 실행기가
    선언하는 ``build_step_registry`` (workflow_step → 핸들러) 매핑을 이 골격이 조회·호출한다.
    "지원하지 않는 단계" 오류도 여기 한곳에서 던진다(실행기마다 복제하던 ``raise`` 제거).
    핸들러는 매직 문자열이 아니라 ``StepOutcome`` (``StepCompleted``/``StepNeedsInput``)을
    돌려주므로, 일시정지 신호가 반환값에 밀입국하지 않는다.
    """

    execution_mode: str

    def __init__(self, artifact_manager: ArtifactManager) -> None:
        self._artifact_manager = artifact_manager
        # workflow_step → 핸들러 레지스트리. 핸들러는 인스턴스 상태가 아니라 호출 시점의
        # StepContext 만 참조하므로, 생성자에서 한 번 구성해 둔다.
        self._step_handlers: Mapping[str, StepHandler] = dict(self.build_step_registry())
        # 자가 치유 엔진(선택 협력자). 컴포지션 루트가 로더를 통해 attach_healing 으로
        # 주입한다 — 미주입이면 치유 없이 기존과 동일하게 동작한다.
        self._healing: SelfHealingEngine | None = None
        # Automation BC 포트(선택). 등록된 Flow 가 있으면 레지스트리보다 우선한다.
        self._automation: AutomationPort | None = None

    def attach_healing(self, engine: SelfHealingEngine | None) -> None:
        """자가 치유 엔진을 부착한다(로더/게이트웨이가 생성 직후 호출)."""
        self._healing = engine

    def attach_automation(self, port: AutomationPort | None) -> None:
        """Automation BC 포트를 부착한다(로더가 생성 직후 호출)."""
        self._automation = port

    @staticmethod
    def _resolve_headless(input_data: dict[str, str]) -> bool:
        browser_mode = (input_data.get("browser_mode") or "headed").strip().lower()
        return browser_mode not in {"headed", "visible", "ui", "false", "0", "no"}

    def _should_capture_module_screenshot(
        self,
        runtime: WorkflowRuntime,
        module: ModuleDefinition,
    ) -> bool:
        """모듈 종료 스크린샷 캡처 여부. 시스템별로 오버라이드한다."""
        return True

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

        # 자가 치유: 이 모듈 실행 동안만 유효한 셀렉터 오버라이드(깨진 → 대체)와 시도 기록.
        # runtime.page 를 프록시로 잠시 교체해, 스텝이 ctx.page/runtime.page 어느 쪽을 쓰든
        # 재시도 시 오버라이드가 적용되게 한다(오버라이드가 비면 사실상 pass-through).
        selector_overrides: dict[str, str] = {}
        healing_attempts: list[HealingAttempt] = []
        real_page = runtime.page
        if self._healing is not None:
            runtime.page = HealedPage(real_page, selector_overrides)

        # 단계 실행 → 모듈 종료 스크린샷까지 컨텍스트-로컬 로그 싱크 안에서 처리해, 캡처 과정의
        # 로그도 execution.log / WebSocket 으로 함께 흘려보낸다. 전역 stdout 은 건드리지 않는다:
        # ``ctx.log`` 와 PageObject 의 ``step_logging.log`` 가 모두 이 싱크로 모인다(스레드 격리).
        try:
            with log_path.open("w", encoding="utf-8") as log_file:

                def sink(line: str) -> None:
                    write_log_line(line, emit_log, log_file)

                context = StepContext(
                    runtime=runtime, module=module, artifact_dir=artifact_dir, log=sink
                )
                token = push_sink(sink)
                try:
                    try:
                        # 매직 문자열 파싱이 아니라 타입드 결과 매칭으로 제어 전이를 만든다.
                        match self._dispatch_with_healing(
                            context, selector_overrides, healing_attempts, sink
                        ):
                            case StepNeedsInput(prompt=prompt):
                                status = ModuleStatus.WAITING_INPUT
                                message = prompt
                            case StepCompleted(message=completed_message):
                                status = ModuleStatus.PASSED
                                message = completed_message
                    except RuntimeError as exc:
                        status = ModuleStatus.ANOMALY
                        message = str(exc)
                        last_error = str(exc)
                        sink(f"[error] {exc}")
                    except Exception as exc:
                        status = ModuleStatus.ERROR
                        message = str(exc)
                        last_error = str(exc)
                        sink(f"[error] {exc}")

                    # 모듈 종료(성공/실패 공통) 시 공용 스크린샷.
                    # 입력 대기(WAITING_INPUT)는 모듈 종료가 아니라 일시정지이므로 건너뛴다.
                    if (
                        status is not ModuleStatus.WAITING_INPUT
                        and self._should_capture_module_screenshot(runtime, module)
                    ):
                        capture_screenshot(real_page, screenshot_path)
                finally:
                    pop_sink(token)
        finally:
            runtime.page = real_page

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
            healing_events=healing_attempts,
        )

    def _dispatch_step(self, context: StepContext) -> StepOutcome:
        """workflow_step 을 Automation BC 또는 레지스트리로 디스패치한다."""
        automation = self._automation
        if automation is not None:
            from app.automation.ports import AutomationContext

            auto_ctx = AutomationContext(
                runtime=context.runtime,
                page=context.page,
                artifact_dir=context.artifact_dir,
                log=context.log,
                dialog_messages=context.dialog_messages,
            )
            outcome = automation.run_step(context.module.workflow_step, auto_ctx)
            if outcome is not None:
                return outcome
        handler = self._step_handlers.get(context.module.workflow_step)
        if handler is None:
            raise RuntimeError(
                f"Unsupported {self.execution_mode} workflow step: {context.module.workflow_step}"
            )
        return handler(context)

    def _dispatch_with_healing(
        self,
        context: StepContext,
        overrides: dict[str, str],
        attempts: list[HealingAttempt],
        log: Callable[[str], None],
    ) -> StepOutcome:
        """스텝 실패 시 자가 치유(대체 셀렉터 탐색 → 1회 재시도)를 끼워 넣는 디스패치.

        치유 엔진이 없거나(미주입) 치유 대상이 아니면 원래 예외를 그대로 던져 기존
        상태 전이(ANOMALY/ERROR)와 완전히 동일하게 동작한다. 치유 자체의 오류는 절대
        원래 실패를 가리지 않는다(엔진 예외는 삼키고 원 예외를 다시 던진다).
        """
        try:
            return self._dispatch_step(context)
        except Exception as exc:
            engine = self._healing
            if engine is None:
                raise
            attempt: HealingAttempt | None = None
            try:
                attempt = engine.try_heal(
                    page=context.runtime.page,
                    module=context.module,
                    error=exc,
                    overrides=overrides,
                    log=log,
                )
            except Exception as heal_exc:  # 치유 실패가 점검 결과를 더 망치지 않게 격리.
                log(f"[heal] 자가 치유 시도 중 오류(무시): {heal_exc}")
            if attempt is None:
                raise
            attempts.append(attempt)
            if not attempt.auto_applied:
                raise
            log("[heal] 대체 셀렉터로 단계를 1회 재시도합니다.")
            try:
                outcome = self._dispatch_step(context)
            except Exception:
                attempt.retry_succeeded = False
                log("[heal] 재시도도 실패했습니다 — 원래 실패로 기록합니다.")
                raise
            attempt.retry_succeeded = True
            log("[heal] 재시도 성공 — 점검을 계속합니다(런타임 한정 복구, 코드 반영은 승인 대기).")
            return outcome

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
    def build_runtime(
        self, input_data: dict[str, str], run_id: str, module_id: str
    ) -> WorkflowRuntime: ...

    @abstractmethod
    def build_step_registry(self) -> Mapping[str, StepHandler]:
        """workflow_step → 단계 핸들러 매핑을 돌려준다(if/elif 디스패치 대체).

        핸들러는 ``StepContext`` 를 받아 ``StepOutcome`` 을 돌려준다. ``StepContext.artifact_dir``
        은 해당 모듈의 아티팩트 디렉터리(`artifacts/{run_id}/{module_id}`)이며, 다운로드 등
        파일 산출물이 필요한 단계만 사용한다. 스크린샷은 공용 엔진이 책임지므로 핸들러에
        스크린샷 경로를 넘기지 않는다. 서브클래스는 ``super().build_step_registry()`` 와 병합해
        부모가 제공하는 단계(예: ``main_access``)를 물려받거나 덮어쓸 수 있다.
        """
        ...

    @abstractmethod
    def _shutdown_browser(self, runtime: WorkflowRuntime) -> None: ...
