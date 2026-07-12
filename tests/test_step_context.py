"""StepContext(단계 실행 능력 인터페이스) 단위 테스트.

브라우저 없이, 단계 핸들러가 전역(stdout)·런타임 내부를 직접 들쑤시지 않고 컨텍스트의
능력(``page``/``dialog_messages``/``log``)만으로 동작함을 검증한다. 엔진이 로그 싱크를
주입하면 ``ctx.log`` 한 줄이 파일과 WebSocket 싱크 양쪽으로 흐르는지도 확인한다.

이 테스트 자체가 #3 의 '테스트 seam 부재' 가 해소됐다는 증거다 — 공용 실행 엔진
(``workflow_engine``)이 이제 playwright 없이 import·실행된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.system_models import ModuleDefinition
from app.platform.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepOutcome
from app.runner.workflow_engine import BaseWorkflowExecutor, StepContext


@dataclass
class _FakeRuntime:
    page: object
    dialog_messages: list[str] = field(default_factory=list)
    playwright_manager: object = None
    context: object = None
    closed: bool = False


def _module(step: str = "s") -> ModuleDefinition:
    return ModuleDefinition(
        module_id="m1",
        system_code="x",
        name="n",
        description="d",
        group="g",
        order=0,
        workflow_step=step,
        execution_mode="fake",
    )


def test_context_exposes_common_capabilities_without_runtime_cast():
    runtime = _FakeRuntime(page="PAGE", dialog_messages=["d1"])
    ctx = StepContext(
        runtime=runtime, module=_module(), artifact_dir=Path("."), log=lambda _line: None
    )
    assert ctx.page == "PAGE"
    assert ctx.dialog_messages == ["d1"]


def test_log_is_required_injected_sink_not_global_stdout():
    # log 는 엔진이 **필수 주입**한다(기본값 없음). 전역 stdout 대신 주입된 싱크로만 흐른다.
    captured: list[str] = []
    ctx = StepContext(
        runtime=_FakeRuntime(page=None),
        module=_module(),
        artifact_dir=Path("."),
        log=captured.append,
    )
    ctx.log("hello-sink")
    assert captured == ["hello-sink"]


def test_no_executor_capability_leaks_into_runtime_protocol():
    # 인프라(스레드 풀)는 더 이상 런타임 계약에 없다 — 게이트웨이 세션이 소유한다.
    from app.runner.workflow_engine import WorkflowRuntime

    assert "executor" not in getattr(WorkflowRuntime, "__annotations__", {})


class _LoggingExecutor(BaseWorkflowExecutor):
    execution_mode = "fake"

    def build_runtime(self, input_data, run_id, module_id):  # pragma: no cover - 미사용
        raise NotImplementedError

    def _shutdown_browser(self, runtime):  # pragma: no cover - 미사용
        raise NotImplementedError

    def _should_capture_module_screenshot(self, runtime, module) -> bool:
        return False  # 스크린샷(=playwright) 경로 회피

    def build_step_registry(self):
        def handler(ctx: StepContext) -> StepOutcome:
            ctx.log("STEP-LOG-LINE")
            return StepCompleted("done")

        return {"s": handler}


def test_engine_injects_log_sink_so_ctx_log_reaches_file_and_websocket(tmp_path):
    executor = _LoggingExecutor(ArtifactManager(tmp_path))
    emitted: list[str] = []
    result = executor.execute_step(_FakeRuntime(page=None), "run1", _module("s"), emitted.append)

    # ctx.log 한 줄이 WebSocket 싱크(emit)와 execution.log 파일 양쪽으로 흐른다.
    assert "STEP-LOG-LINE" in emitted
    log_text = (tmp_path / "run1" / "m1" / "execution.log").read_text(encoding="utf-8")
    assert "STEP-LOG-LINE" in log_text
    assert result.status.value == "PASSED"
