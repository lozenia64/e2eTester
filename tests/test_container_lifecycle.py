"""AppContainer build/start/stop 라이프사이클 스모크 테스트."""

from __future__ import annotations

import pytest

from app.composition import container as container_mod
from app.composition.container import AppContainer
from app.contexts.healing.composition import compose_healing as real_compose_healing
from app.core.settings import E2ESettings
from app.execution.composition import (
    compose_execution_gateway as real_compose_execution_gateway,
)
from app.execution.composition import (
    compose_execution_runtime as real_compose_execution_runtime,
)
from app.platform.eventing.bus import RunFinished
from app.registry.loader import ModuleRegistry


def test_wire_execution_initialization_order_7_8_9(tmp_path, monkeypatch) -> None:
    """계획 순서 7(runtime) → 8(healing) → 9(gateway) 가 wire_execution 에서 보존된다."""
    order: list[str] = []

    def tracked_runtime(registry, settings):
        order.append("runtime")
        return real_compose_execution_runtime(registry, settings)

    def tracked_healing(db_path, registry):
        order.append("healing")
        return real_compose_healing(db_path, registry)

    def tracked_gateway(settings, session_registry):
        order.append("gateway")
        return real_compose_execution_gateway(settings, session_registry)

    monkeypatch.setattr(container_mod, "compose_execution_runtime", tracked_runtime)
    monkeypatch.setattr(container_mod, "compose_healing", tracked_healing)
    monkeypatch.setattr(container_mod, "compose_execution_gateway", tracked_gateway)

    settings = E2ESettings(
        E2E_DB_PATH=str(tmp_path / "order.db"),
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="",
    )
    container = AppContainer(settings=settings)
    container.registry = ModuleRegistry()
    container.db_path = settings.db_path

    container.wire_execution()

    assert order == ["runtime", "healing", "gateway"]


@pytest.mark.asyncio
async def test_container_build_start_stop_lifecycle(tmp_path) -> None:
    settings = E2ESettings(
        E2E_DB_PATH=str(tmp_path / "test.db"),
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="",
    )
    container = AppContainer.build(settings)

    await container.start()

    assert container.eventing.event_bus.handler_count(RunFinished) >= 1
    assert container.execution.run_queue.worker_count > 0
    assert container.outbox_relay is not None
    assert callable(container.suite.suite_service.load_suite_finished_payload)

    await container.stop()
