"""LocalExecutionGateway 의 **명시적 세션 = 워커 경계** 단위 테스트.

브라우저 없이(가짜 실행기 주입), 실행 스레드 풀이 도메인 런타임에 몽키패치되지 않고
게이트웨이 세션이 소유함을 검증한다. 또한 build/step/submit/close 가 같은 단일 세션
스레드에서 돌고, 스레드↔이벤트 루프 로그 브리지가 동작하며, 종료 시 세션 풀이 정리됨을 본다.

async def 테스트는 pytest-asyncio(asyncio_mode="auto")가 코루틴으로 실행한다.
"""

from __future__ import annotations

import threading

import pytest

from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition
from app.execution import local_gateway as lg
from app.execution.results import StepExecutionResult


class _FakeRuntime:
    def __init__(self) -> None:
        self.build_thread = threading.get_ident()
        self.closed = False
        self.otp: str | None = None


class _FakeExecutor:
    """playwright 없는 가짜 워크플로 실행기(게이트웨이 계약만 만족)."""

    def __init__(self) -> None:
        self.step_thread: int | None = None
        self.closed = False

    def build_runtime(self, input_data, run_id, module_id, storage_state=None) -> _FakeRuntime:
        self.restored_storage_state = storage_state
        return _FakeRuntime()

    def execute_step(self, runtime, run_id, module, emit_log) -> StepExecutionResult:
        self.step_thread = threading.get_ident()
        emit_log("LOG-FROM-STEP")
        return StepExecutionResult(
            status=ModuleStatus.PASSED,
            message="ok",
            artifacts=[],
            current_url=None,
            dialog_messages=[],
        )

    def update_otp_code(self, runtime, value) -> None:
        runtime.otp = value

    def close_runtime(self, runtime) -> None:
        self.closed = True
        runtime.closed = True


def _module() -> ModuleDefinition:
    return ModuleDefinition(
        module_id="m1",
        system_code="x",
        name="n",
        description="d",
        group="g",
        order=0,
        workflow_step="s",
        execution_mode="fake",
    )


@pytest.fixture
def gateway(monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(lg, "load_workflow_executors", lambda codes, am: {"fake": fake})
    gw = lg.LocalExecutionGateway(artifact_manager=None, system_codes=["x"])
    return gw, fake


async def test_session_owns_thread_pool_not_runtime(gateway):
    gw, _fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    session = gw._sessions[handle.session_id]
    # 스레드 풀은 세션이 명시적으로 소유한다 — 런타임에 executor 가 매달리지 않는다.
    assert session.executor is not None
    assert not hasattr(session.runtime, "executor")
    await gw.close_session(handle)


async def test_steps_run_on_single_session_thread_and_bridge_logs(gateway):
    gw, fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    runtime = gw._sessions[handle.session_id].runtime

    logs: list[str] = []

    async def on_log(line: str) -> None:
        logs.append(line)

    result = await gw.run_step(handle, "run1", _module(), on_log)

    assert result.status == ModuleStatus.PASSED
    assert "LOG-FROM-STEP" in logs  # 스레드 → 이벤트 루프 로그 브리지
    # build_runtime 과 execute_step 은 같은 단일 세션 스레드에서 돈다(메인 스레드가 아님).
    assert fake.step_thread == runtime.build_thread
    assert fake.step_thread != threading.get_ident()
    await gw.close_session(handle)


async def test_submit_input_then_close_shuts_down_session_pool(gateway):
    gw, fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    session = gw._sessions[handle.session_id]
    pool = session.executor

    await gw.submit_input(handle, "123456")
    assert session.runtime.otp == "123456"

    await gw.close_session(handle)
    assert fake.closed is True
    assert handle.session_id not in gw._sessions  # 세션 제거
    assert pool._shutdown is True  # 세션이 소유한 풀이 정리됨


async def test_close_session_is_idempotent(gateway):
    gw, _fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    await gw.close_session(handle)
    # 이미 닫힌(혹은 알 수 없는) 세션 재종료는 조용히 무시된다.
    await gw.close_session(handle)
