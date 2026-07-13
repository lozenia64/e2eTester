"""``AppContainer`` local 모드 실행 배선 검증."""

from __future__ import annotations

from app.composition.container import AppContainer
from app.core.settings import E2ESettings
from app.execution.in_process_gateway import InProcessExecutionGateway
from app.execution.worker_gateway import WorkerExecutionGateway


def test_local_mode_wires_in_process_gateway(monkeypatch, tmp_path):
    monkeypatch.setenv("E2E_EXECUTION_MODE", "local")
    monkeypatch.setenv("E2E_DB_PATH", str(tmp_path / "test.db"))
    settings = E2ESettings()
    container = AppContainer.build(settings)

    gateways = container.execution_gateway._gateways
    assert any(isinstance(g, InProcessExecutionGateway) for g in gateways)
    assert not any(isinstance(g, WorkerExecutionGateway) for g in gateways)
    assert container.session_registry is None
    assert container.healing_engine is not None


def test_remote_mode_wires_worker_gateway(monkeypatch, tmp_path):
    monkeypatch.setenv("E2E_EXECUTION_MODE", "remote")
    monkeypatch.setenv("E2E_DB_PATH", str(tmp_path / "test.db"))
    settings = E2ESettings()
    container = AppContainer.build(settings)

    gateways = container.execution_gateway._gateways
    assert any(isinstance(g, WorkerExecutionGateway) for g in gateways)
    assert not any(isinstance(g, InProcessExecutionGateway) for g in gateways)
    assert container.session_registry is not None
    assert container.healing_engine is None
