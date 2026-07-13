"""``SessionServer`` 의 **명시적 세션 = 워커 경계** 단위 테스트(브라우저 없음).

in-process 브라우저 호스트 SSOT 는 ``app.execution.session_server.SessionServer`` 이다.
가짜 실행기로 빠르게(HTTP 없이) 검증한다: ①실행 스레드 풀을 세션이 소유(런타임 몽키패치 없음)
②build/step/submit/close 가 같은 단일 세션 스레드에서 실행 ③스레드↔이벤트 루프 로그 브리지
④종료 시 세션 풀 정리 ⑤storage_state 복원 배선 ⑥capture_storage_state 가 세션 스레드에서 실행.

async def 테스트는 pytest-asyncio(asyncio_mode="auto")가 코루틴으로 실행한다.
"""

from __future__ import annotations

import threading

import pytest

from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition
from app.execution import session_server as ss
from app.execution.results import StepExecutionResult


class _FakeContext:
    def __init__(self) -> None:
        self.thread = threading.get_ident()

    def storage_state(self) -> dict:
        # storage_state 는 세션 스레드에서만 호출 가능해야 한다(스레드 어피니티 검증용).
        return {"called_on_thread": threading.get_ident()}


class _FakePage:
    def __init__(self) -> None:
        self.context = _FakeContext()


class _FakeRuntime:
    def __init__(self) -> None:
        self.build_thread = threading.get_ident()
        self.closed = False
        self.otp: str | None = None
        self.page = _FakePage()


class _FakeExecutor:
    """playwright 없는 가짜 워크플로 실행기(세션 호스트 계약만 만족)."""

    def __init__(self) -> None:
        self.step_thread: int | None = None
        self.closed = False
        self.restored_storage_state: str | None = None

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
def server(monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(ss, "load_workflow_executors", lambda codes, am, **kw: {"fake": fake})
    srv = ss.SessionServer(artifact_manager=None, system_codes=["x"])
    return srv, fake


async def test_session_owns_thread_pool_not_runtime(server):
    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    session = srv._sessions[session_id]
    # 스레드 풀은 세션이 명시적으로 소유한다 — 런타임에 executor 가 매달리지 않는다.
    assert session.executor is not None
    assert not hasattr(session.runtime, "executor")
    await srv.close_session(session_id)


async def test_steps_run_on_single_session_thread_and_bridge_logs(server):
    srv, fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    runtime = srv._sessions[session_id].runtime

    result, logs = await srv.run_step(session_id, "run1", _module())

    assert result.status == ModuleStatus.PASSED
    assert "LOG-FROM-STEP" in logs  # 스레드 → 이벤트 루프 로그 브리지(내부 큐 드레인)
    # build_runtime 과 execute_step 은 같은 단일 세션 스레드에서 돈다(메인 스레드가 아님).
    assert fake.step_thread == runtime.build_thread
    assert fake.step_thread != threading.get_ident()
    await srv.close_session(session_id)


async def test_submit_input_then_close_shuts_down_session_pool(server):
    srv, fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    session = srv._sessions[session_id]
    pool = session.executor

    await srv.submit_input(session_id, "123456")
    assert session.runtime.otp == "123456"

    await srv.close_session(session_id)
    assert fake.closed is True
    assert session_id not in srv._sessions  # 세션 제거
    assert pool._shutdown is True  # 세션이 소유한 풀이 정리됨


async def test_close_session_is_idempotent(server):
    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    await srv.close_session(session_id)
    # 이미 닫힌(혹은 알 수 없는) 세션 재종료는 조용히 무시된다.
    await srv.close_session(session_id)


async def test_open_session_threads_storage_state_into_build_runtime(server):
    srv, fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1", '{"cookies": []}')
    # 체크포인트 복원 storage_state 가 build_runtime 까지 전달된다(WP-C2 복원 배선).
    assert fake.restored_storage_state == '{"cookies": []}'
    await srv.close_session(session_id)


async def test_capture_storage_state_runs_on_session_thread(server):
    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    runtime = srv._sessions[session_id].runtime

    state = await srv.capture_storage_state(session_id)

    # storage_state 는 세션 전용 스레드에서 직렬화돼야 한다(Playwright 스레드 어피니티).
    assert str(runtime.build_thread) in state
    assert str(threading.get_ident()) not in state
    await srv.close_session(session_id)


async def test_capture_storage_state_unknown_session_returns_none(server):
    srv, _fake = server
    assert await srv.capture_storage_state("nope") is None
