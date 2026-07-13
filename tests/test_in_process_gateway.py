"""``InProcessExecutionGateway`` — SessionServer 위임·on_log fan-out."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition
from app.execution import session_server as ss
from app.execution.in_process_gateway import InProcessExecutionGateway
from app.execution.results import StepExecutionResult
from tests.test_session_server import _FakeExecutor, _module


@pytest.fixture
def gateway(monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(ss, "load_workflow_executors", lambda codes, am, **kw: {"fake": fake})
    server = ss.SessionServer(artifact_manager=None, system_codes=["x"])
    return InProcessExecutionGateway(server), fake


async def test_supports_registered_execution_mode(gateway):
    gw, _fake = gateway
    assert gw.supports("fake") is True
    assert gw.supports("unknown") is False


async def test_open_session_returns_handle(gateway):
    gw, _fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    assert handle.execution_mode == "fake"
    assert handle.session_id


async def test_run_step_forwards_logs_to_on_log(gateway):
    gw, _fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    on_log = AsyncMock()
    result = await gw.run_step(handle, "run1", _module(), on_log)
    assert result.status == ModuleStatus.PASSED
    on_log.assert_awaited_once_with("LOG-FROM-STEP")


async def test_submit_input_and_close_session(gateway):
    gw, fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    await gw.submit_input(handle, "999999")
    assert gw._session_server._sessions[handle.session_id].runtime.otp == "999999"
    await gw.close_session(handle)
    assert fake.closed is True
    assert handle.session_id not in gw._session_server._sessions


async def test_capture_storage_state_on_session_thread(gateway):
    gw, _fake = gateway
    handle = await gw.open_session("fake", {}, "run1", "m1")
    runtime = gw._session_server._sessions[handle.session_id].runtime
    state = await gw.capture_storage_state(handle)
    assert str(runtime.build_thread) in state
    assert str(threading.get_ident()) not in state
    await gw.close_session(handle)
