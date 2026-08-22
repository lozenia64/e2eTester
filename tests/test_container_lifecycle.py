"""AppContainer build/start/stop 라이프사이클 스모크 테스트."""

from __future__ import annotations

import pytest

from app.composition import container as container_mod
from app.composition.container import AppContainer
from app.contexts.healing.composition import compose_healing as real_compose_healing
from app.contexts.insights.composition import InsightsRepositories
from app.contexts.run.composition import RunRepositories
from app.contexts.suite.composition import SuiteRepositories
from app.core.settings import E2ESettings
from app.execution.composition import (
    compose_execution_gateway as real_compose_execution_gateway,
)
from app.execution.composition import (
    compose_execution_runtime as real_compose_execution_runtime,
)
from app.orchestrator.queries import RunQueries
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
@pytest.mark.spec("SPEC-PLATFORM-001", "AC-002")
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
    assert callable(container.suite.services.suite_service.load_suite_finished_payload)

    await container.stop()


def test_wire_persistence_builds_repos_atomically(tmp_path) -> None:
    """wire_persistence 직후 저장소는 즉시, 서비스는 아직 None."""
    settings = E2ESettings(
        E2E_DB_PATH=str(tmp_path / "atomic.db"),
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="",
    )
    container = AppContainer(settings=settings)
    container.wire_persistence()

    assert isinstance(container.run.repos, RunRepositories)
    assert isinstance(container.run.run_queries, RunQueries)
    assert container.run.services is None

    assert isinstance(container.suite.repos, SuiteRepositories)
    assert container.suite.services is None

    assert isinstance(container.insights.repos, InsightsRepositories)
    assert container.insights.stats_service is None
    assert container.insights.insights_service is None
    assert container.insights.ops_service is None
    assert container.insights.daily_queries is None
    assert container.insights.admin_dashboard_queries is None

    assert container.preset.preset_repository is not None
    assert container.preset.preset_service is None

    assert container.scheduling.schedule_repository is not None
    assert container.scheduling.scheduler is None
    assert container.scheduling.retention_scheduler is None
    assert container.scheduling.daily_report_scheduler is None


def test_wire_orchestration_and_read_models_fill_late_fields(tmp_path) -> None:
    """wire_orchestration/wire_read_models 이후 순환 의존 필드가 모두 채워진다."""
    settings = E2ESettings(
        E2E_DB_PATH=str(tmp_path / "late.db"),
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="",
    )
    container = AppContainer(settings=settings)
    container.wire_persistence()
    container.wire_realtime()
    container.wire_execution()
    container.wire_orchestration()
    container.wire_read_models()

    assert container.run.services is not None
    assert container.suite.services is not None
    assert container.preset.preset_service is not None
    assert container.scheduling.scheduler is not None
    assert container.insights.daily_queries is not None
    assert container.insights.admin_dashboard_queries is not None
    assert container.insights.stats_service is not None
    assert container.insights.insights_service is not None
    assert container.insights.ops_service is not None


def test_wire_read_models_wires_daily_report_scheduler_when_email_config_available(
    tmp_path, monkeypatch
) -> None:
    settings = E2ESettings(
        E2E_DB_PATH=str(tmp_path / "daily-report.db"),
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="",
    )
    container = AppContainer(settings=settings)
    container.wire_persistence()
    container.wire_realtime()
    container.wire_execution()
    container.wire_orchestration()

    fake_config = object()
    fake_scheduler = object()
    captured: dict[str, object] = {}

    class _FakeEmailConfig:
        @classmethod
        def from_env(cls, system_codes):
            captured["system_codes"] = list(system_codes)
            return fake_config

    class _FakeDailyReportEmailService:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    def _compose_daily_report_scheduler(service):
        captured["scheduler_service"] = service
        return fake_scheduler

    monkeypatch.setattr(container_mod, "EmailNotificationConfig", _FakeEmailConfig, raising=False)
    monkeypatch.setattr(
        container_mod,
        "DailyReportEmailService",
        _FakeDailyReportEmailService,
        raising=False,
    )
    monkeypatch.setattr(
        container_mod,
        "resolve_daily_report_recipients",
        # (수신자, 오류 목록) — 형제 리졸버와 같은 계약
        lambda *_args, **_kwargs: (("qa@example.com",), []),
        raising=False,
    )
    monkeypatch.setattr(
        container_mod,
        "load_dotenv_file",
        lambda *_args, **_kwargs: {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "qa@example.com"},
        raising=False,
    )
    monkeypatch.setattr(
        container_mod,
        "compose_daily_report_scheduler",
        _compose_daily_report_scheduler,
        raising=False,
    )

    container.wire_read_models()

    assert captured["summary_queries"] is container.insights.daily_summary_queries
    assert captured["config"] is fake_config
    assert captured["recipients"] == ("qa@example.com",)
    assert captured["dedup_store"]._db is container.es_db
    assert container.scheduling.daily_report_scheduler is fake_scheduler
