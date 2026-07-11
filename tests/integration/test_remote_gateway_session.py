"""RemoteExecutionGateway ↔ 워커 HTTP 프로토콜 통합 테스트."""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.execution.remote_gateway import RemoteExecutionGateway
from app.runner.workflow_common import StepExecutionResult
from tests.test_local_gateway_session import _FakeExecutor, _module
from worker.http_server import create_http_app
from worker.session_server import SessionServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(host: str, port: int, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"워커 HTTP 서버가 {timeout}s 내에 준비되지 않았습니다: {host}:{port}")


@pytest.fixture
def remote_gateway(monkeypatch):
    fake = _FakeExecutor()
    stub = lambda codes, am, **kwargs: {"fake": fake}  # noqa: E731
    monkeypatch.setattr("app.systems.loader.load_workflow_executors", stub)
    import worker.session_server as ss

    monkeypatch.setattr(ss, "load_workflow_executors", stub)
    session_server = SessionServer(artifact_manager=None, system_codes=["x"])
    port = _free_port()
    app = create_http_app(session_server)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server("127.0.0.1", port)
    gateway = RemoteExecutionGateway(f"http://127.0.0.1:{port}")
    yield gateway, fake, session_server
    server.should_exit = True
    thread.join(timeout=3)


async def test_remote_open_run_close_session(remote_gateway):
    gateway, fake, _session_server = remote_gateway
    handle = await gateway.open_session("fake", {"phone": "010"}, "run-1", "m1")
    assert handle.session_id

    logs: list[str] = []

    async def on_log(line: str) -> None:
        logs.append(line)

    result = await gateway.run_step(handle, "run-1", _module(), on_log)
    assert result.status == ModuleStatus.PASSED
    assert logs == ["LOG-FROM-STEP"]
    assert fake.step_thread is not None

    await gateway.submit_input(handle, "123456")
    await gateway.close_session(handle)
    assert fake.closed is True
