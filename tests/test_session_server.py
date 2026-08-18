"""워커 ``SessionServer`` 의 **명시적 세션 = 워커 경계** 단위 테스트(브라우저 없음).

실행 평면 분리(Model B) 이후 in-process 브라우저 호스트는 워커의 ``SessionServer`` 하나뿐이다
(구 ``LocalExecutionGateway`` 는 폐기). 이 테스트는 그 프로덕션 호스트가 다음 불변식을 지키는지
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
from app.execution.results import StepExecutionResult
from worker import session_server as ss


class _FakeContext:
    def __init__(self) -> None:
        self.thread = threading.get_ident()

    def storage_state(self) -> dict:
        # storage_state 는 세션 스레드에서만 호출 가능해야 한다(스레드 어피니티 검증용).
        return {"called_on_thread": threading.get_ident()}


class _FakePage:
    def __init__(self) -> None:
        self.context = _FakeContext()
        self.goto_calls: list[str] = []
        self.load_states: list[str] = []

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_calls.append(url)

    def wait_for_load_state(self, state: str = "load", **_kwargs) -> None:
        self.load_states.append(state)


class _FakeRuntime:
    def __init__(self) -> None:
        self.build_thread = threading.get_ident()
        self.closed = False
        self.otp: str | None = None
        self.page = _FakePage()
        self.dialog_messages: list[str] = []


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


# --- 복구 등급 되감기 --------------------------------------------------------


async def test_recover_tier_one_navigates_to_entry_url(server):
    """tier 1 은 다이얼로그 기록을 끊고 진입 URL 로 재이동한다."""
    from app.core.enums import RecoveryTier

    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    runtime = srv._require_session(session_id).runtime  # noqa: SLF001
    runtime.dialog_messages.append("이전 모듈의 팝업")

    recovered = await srv.recover(
        session_id, RecoveryTier.RESET_TO_MODULE_ENTRY, "https://example.com/entry"
    )

    assert recovered is True
    assert runtime.page.goto_calls == ["https://example.com/entry"]
    assert runtime.dialog_messages == []


@pytest.mark.spec("SPEC-RUN-006", "AC-005")
async def test_recover_tier_one_without_entry_url_is_noop(server):
    from app.core.enums import RecoveryTier

    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    runtime = srv._require_session(session_id).runtime  # noqa: SLF001

    recovered = await srv.recover(session_id, RecoveryTier.RESET_TO_MODULE_ENTRY, None)

    assert recovered is False
    assert runtime.page.goto_calls == []


async def test_recover_tier_two_rebuilds_runtime(server):
    """tier 2 는 런타임을 폐기하고 같은 session_id 로 다시 만든다."""
    from app.core.enums import RecoveryTier

    srv, fake = server
    session_id = await srv.open_session("fake", {"id": "u1"}, "run1", "m1")
    first_runtime = srv._require_session(session_id).runtime  # noqa: SLF001

    recovered = await srv.recover(session_id, RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert recovered is True
    assert fake.closed is True  # 옛 런타임은 닫혔다
    assert srv._require_session(session_id).runtime is not first_runtime  # noqa: SLF001
    assert srv.get_session_run_id(session_id) == "run1"  # 세션 식별자는 유지된다


async def test_recover_tier_two_keeps_old_runtime_if_rebuild_fails(server):
    """두 번째 build_runtime 실패 시 옛 런타임을 닫지 않아 제자리 재시도가 가능하다."""
    from app.core.enums import RecoveryTier

    srv, fake = server
    session_id = await srv.open_session("fake", {"id": "u1"}, "run1", "m1")
    first_runtime = srv._require_session(session_id).runtime  # noqa: SLF001

    def _fail_rebuild(*_args, **_kwargs):
        raise RuntimeError("rebuild failed")

    fake.build_runtime = _fail_rebuild

    recovered = await srv.recover(session_id, RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert recovered is False
    assert srv._require_session(session_id).runtime is first_runtime  # noqa: SLF001
    assert first_runtime.closed is False
    assert srv.get_session_run_id(session_id) == "run1"


async def test_recover_unknown_session_returns_false(server):
    from app.core.enums import RecoveryTier

    srv, _fake = server

    recovered = await srv.recover("없는세션", RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert recovered is False


async def test_recover_tier_zero_is_rejected(server):
    """tier 0 은 되감기가 없으므로 워커까지 오면 안 된다."""
    from app.core.enums import RecoveryTier

    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")

    assert await srv.recover(session_id, RecoveryTier.RETRY_IN_PLACE, None) is False
