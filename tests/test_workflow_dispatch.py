"""공용 실행 엔진의 단계 디스패치 + 타입드 결과(StepOutcome) 단위 테스트.

브라우저 없이, 가짜 런타임/핸들러만으로 다음을 검증한다.
- 레지스트리(`build_step_registry`) 조회로 핸들러가 호출된다(if/elif 디스패치 대체).
- ``StepCompleted`` → PASSED, ``StepNeedsInput`` → WAITING_INPUT 로 매핑된다
  (과거 ``WAITING_INPUT::`` 매직 문자열 in-band 프로토콜의 부재 확인).
- 핸들러 예외는 RuntimeError → ANOMALY, 그 외 → ERROR 로 변환된다.
- 등록되지 않은 workflow_step 은 한곳(엔진)에서 RuntimeError(ANOMALY) 로 거부된다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_engine import BaseWorkflowExecutor, StepContext, StepHandler


class _FakePage:
    url = "https://example.test/page"


class _FakeRuntime:
    def __init__(self) -> None:
        self.playwright_manager = object()
        self.context = object()
        self.page = _FakePage()
        self.dialog_messages: list[str] = []
        self.executor = None
        self.closed = False


class _FakeExecutor(BaseWorkflowExecutor):
    execution_mode = "fake_workflow_step"

    def build_runtime(self, input_data, run_id, module_id):  # pragma: no cover - 미사용
        return _FakeRuntime()

    def _shutdown_browser(self, runtime):  # pragma: no cover - 미사용
        return None

    def _should_capture_module_screenshot(self, runtime, module) -> bool:
        # 가짜 페이지로 스크린샷을 찍지 않게 한다(브라우저 무의존).
        return False

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        return {
            "ok": self._step_ok,
            "needs_input": self._step_needs_input,
            "anomaly": self._step_anomaly,
            "error": self._step_error,
        }

    def _step_ok(self, ctx: StepContext) -> StepOutcome:
        # PageObject 스타일: 컨텍스트-로컬 log() 로 흘려보낸다(전역 stdout 미접촉).
        from app.runner.step_logging import log

        log("[step] ok 실행")
        ctx.log("[step] ok via ctx")
        return StepCompleted("정상 종료")

    def _step_needs_input(self, ctx: StepContext) -> StepOutcome:
        return StepNeedsInput("OTP를 입력하세요")

    def _step_anomaly(self, ctx: StepContext) -> StepOutcome:
        raise RuntimeError("사이트 이상")

    def _step_error(self, ctx: StepContext) -> StepOutcome:
        raise ValueError("플랫폼 오류")


def _module(step: str) -> ModuleDefinition:
    return ModuleDefinition(
        module_id=f"m_{step}",
        system_code="fake",
        name=step,
        description="",
        group="g",
        order=1,
        workflow_step=step,
        execution_mode="fake_workflow_step",
    )


def _run(executor: _FakeExecutor, step: str, tmp_path: Path):
    logs: list[str] = []
    return executor.execute_step(_FakeRuntime(), "run_test", _module(step), logs.append), logs


def test_registry_built_from_declarations(tmp_path):
    executor = _FakeExecutor(ArtifactManager(tmp_path))
    assert set(executor._step_handlers) == {"ok", "needs_input", "anomaly", "error"}


def test_step_completed_maps_to_passed(tmp_path):
    executor = _FakeExecutor(ArtifactManager(tmp_path))
    result, logs = _run(executor, "ok", tmp_path)
    assert result.status == ModuleStatus.PASSED
    assert result.message == "정상 종료"
    # step_logging.log(컨텍스트-로컬)와 ctx.log 둘 다 같은 싱크로 모인다(전역 stdout 미경유).
    assert any("ok 실행" in line for line in logs)
    assert any("ok via ctx" in line for line in logs)


def test_step_needs_input_maps_to_waiting_input(tmp_path):
    executor = _FakeExecutor(ArtifactManager(tmp_path))
    result, _ = _run(executor, "needs_input", tmp_path)
    assert result.status == ModuleStatus.WAITING_INPUT
    # 매직 프리픽스 없이 prompt 가 그대로 메시지로 전달된다.
    assert result.message == "OTP를 입력하세요"
    assert "WAITING_INPUT::" not in result.message


def test_runtime_error_maps_to_anomaly(tmp_path):
    executor = _FakeExecutor(ArtifactManager(tmp_path))
    result, _ = _run(executor, "anomaly", tmp_path)
    assert result.status == ModuleStatus.ANOMALY
    assert result.last_error == "사이트 이상"


def test_other_exception_maps_to_error(tmp_path):
    executor = _FakeExecutor(ArtifactManager(tmp_path))
    result, _ = _run(executor, "error", tmp_path)
    assert result.status == ModuleStatus.ERROR
    assert result.last_error == "플랫폼 오류"


def test_unregistered_step_is_rejected_centrally(tmp_path):
    executor = _FakeExecutor(ArtifactManager(tmp_path))
    result, _ = _run(executor, "nonexistent", tmp_path)
    # 미등록 단계는 엔진이 RuntimeError 로 거부 → ANOMALY 로 변환.
    assert result.status == ModuleStatus.ANOMALY
    assert "Unsupported" in result.message
