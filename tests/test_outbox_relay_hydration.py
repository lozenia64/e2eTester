"""OutboxRelay EventBus 하이드레이션 — 제네릭 hydrator 레지스트리 회귀 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.hydration import RunHydrator, RunProjectionLoader
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.contexts.suite.infrastructure.hydration import SuiteHydrator
from app.contexts.suite.infrastructure.sqlite_suite_write_repository import (
    SqliteSuiteWriteRepository,
)
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.suite_models import SuiteRun, SuiteStep
from app.platform.eventing.bus import (
    EventBus,
    RunFinished,
    RunResumed,
    RunWaitingInput,
    SuiteFinished,
)
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.relay import OutboxRelay
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.projector import RealtimeProjector


def _sample_run(run_id: str = "run_hydrate") -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.login",
                name="login",
                group="auth",
                order=0,
                status=ModuleStatus.PENDING,
            ),
        ],
        selected_module_ids=["hom.login"],
        triggered_by="manual",
    )


def _sample_suite(suite_id: str = "suite_hydrate") -> SuiteRun:
    return SuiteRun(
        suite_id=suite_id,
        status=RunStatus.PENDING,
        steps=[
            SuiteStep(
                system_code="hom",
                system_name="HOM",
                order=0,
                status=RunStatus.PENDING,
            ),
        ],
        requested_at=datetime.now(UTC),
    )


class _SuiteFinishedStub:
    async def load_suite_finished_payload(self, suite_id: str):
        suite = _sample_suite(suite_id)
        run = _sample_run(f"run_for_{suite_id}")
        return suite, [run]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type,bus_type",
    [
        ("RunFinished", RunFinished),
        ("RunWaitingInput", RunWaitingInput),
        ("RunResumed", RunResumed),
    ],
)
async def test_relay_hydrates_run_events_with_logs(tmp_path, event_type, bus_type):
    db = SqliteDatabase(tmp_path / f"{event_type}.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    log_store = InMemoryRunLogStore()
    projections = ProjectionHandlers(db, loaders={"Run": RunProjectionLoader(write_repo)})
    outbox = SqliteOutbox(db)
    projector = RealtimeProjector(RealtimeNotificationAdapter(), SuiteRealtimeNotificationAdapter())
    relay = OutboxRelay(
        outbox,
        projections,
        hydrators={"Run": RunHydrator(write_repo, log_store)},
        event_bus=EventBus(),
        realtime=projector,
    )

    run = _sample_run(f"run_{event_type}")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())
    await log_store.append(run.run_id, "hom.login", "hydrated-log-line")
    await relay.process_once()

    aggregate = RunAggregate(await write_repo.get_run(run.run_id))
    aggregate.begin()
    module = aggregate.module("hom.login")
    if event_type == "RunWaitingInput":
        aggregate.mark_running(module)
        aggregate.mark_waiting_input(module, "OTP 입력", artifacts=[])
    elif event_type == "RunResumed":
        aggregate.mark_running(module)
        aggregate.mark_waiting_input(module, "OTP 입력", artifacts=[])
        aggregate.resume_after_input(module)
    else:
        aggregate.mark_running(module)
        aggregate.record_result(
            module,
            status=ModuleStatus.PASSED,
            message="ok",
            artifacts=[],
            current_url=None,
            dialog_messages=[],
        )
        aggregate.finish_timing(module)
        aggregate.finalize(None)
    await write_repo.save_run(aggregate.persistable_state(), events=aggregate.pull_events())

    received = []

    async def _capture(event) -> None:
        received.append(event)

    event_bus = EventBus()
    event_bus.subscribe(bus_type, _capture)
    relay._event_bus = event_bus  # noqa: SLF001 — 테스트에서 bus 교체

    assert await relay.process_once() >= 1
    await __import__("asyncio").sleep(0.05)
    assert len(received) == 1
    payload_run = received[0].run
    assert payload_run.run_id == run.run_id
    assert payload_run.modules[0].logs == ["hydrated-log-line"]


@pytest.mark.asyncio
async def test_relay_hydrates_suite_finished_payload(tmp_path):
    db = SqliteDatabase(tmp_path / "suite.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    suite_write_repo = SqliteSuiteWriteRepository(db)
    projections = ProjectionHandlers(db, loaders={"Run": RunProjectionLoader(write_repo)})
    outbox = SqliteOutbox(db)
    projector = RealtimeProjector(RealtimeNotificationAdapter(), SuiteRealtimeNotificationAdapter())
    stub = _SuiteFinishedStub()
    relay = OutboxRelay(
        outbox,
        projections,
        hydrators={"Suite": SuiteHydrator(stub)},
        event_bus=EventBus(),
        realtime=projector,
    )

    suite = _sample_suite()
    from app.contexts.suite.domain.aggregate import SuiteAggregate

    aggregate = SuiteAggregate.for_new_suite(suite)
    await suite_write_repo.create_suite(suite, events=aggregate.pull_events())
    aggregate = SuiteAggregate(await suite_write_repo.get_suite(suite.suite_id))
    aggregate.finalize(RunStatus.PASSED)
    await suite_write_repo.save_suite(aggregate.persistable_state(), events=aggregate.pull_events())

    received = []

    async def _capture(event: SuiteFinished) -> None:
        received.append(event)

    event_bus = EventBus()
    event_bus.subscribe(SuiteFinished, _capture)
    relay._event_bus = event_bus  # noqa: SLF001

    assert await relay.process_once() >= 1
    await __import__("asyncio").sleep(0.05)
    assert len(received) == 1
    assert received[0].suite.suite_id == suite.suite_id
    assert received[0].runs[0].run_id == f"run_for_{suite.suite_id}"
