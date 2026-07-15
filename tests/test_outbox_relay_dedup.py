"""OutboxRelay 원자적 claim — 동시 process_once 멱등성 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.contexts.run.domain.aggregate import RunAggregate
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.events.bus import EventBus, RunFinished
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.relay import OutboxRelay
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import ProjectionHandlers
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.projector import RealtimeProjector
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_suite_write_repository import SqliteSuiteWriteRepository


def _sample_run(run_id: str = "run_outbox_dedup") -> Run:
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


@pytest.mark.asyncio
async def test_concurrent_process_once_publishes_run_finished_once(tmp_path):
    db = SqliteDatabase(tmp_path / "outbox_dedup.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    suite_write_repo = SqliteSuiteWriteRepository(db)
    projections = ProjectionHandlers(db, write_repo)
    outbox = SqliteOutbox(db)
    run_realtime = RealtimeNotificationAdapter()
    suite_realtime = SuiteRealtimeNotificationAdapter()
    projector = RealtimeProjector(
        run_realtime,
        suite_realtime,
        run_loader=write_repo.get_run,
        suite_loader=suite_write_repo.get_suite,
    )

    run = _sample_run()
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())

    bootstrap_relay = OutboxRelay(outbox, projections, write_repo, EventBus(), projector)
    await bootstrap_relay.process_once()

    aggregate = RunAggregate(await write_repo.get_run(run.run_id))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_queued(module)
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=ModuleStatus.PASSED,
        message="ok",
        artifacts=["run_outbox_dedup/hom.login/final.png"],
        current_url="https://www.hwgeneralins.com/",
        dialog_messages=[],
    )
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    await write_repo.save_run(aggregate.persistable_state(), events=aggregate.pull_events())

    publish_count = 0

    async def _count_run_finished(_event: RunFinished) -> None:
        nonlocal publish_count
        publish_count += 1

    event_bus = EventBus()
    event_bus.subscribe(RunFinished, _count_run_finished)

    relays = [
        OutboxRelay(outbox, projections, write_repo, event_bus, projector) for _ in range(4)
    ]
    results = await asyncio.gather(*(relay.process_once() for relay in relays))

    assert sum(results) >= 1
    await asyncio.sleep(0.1)
    assert publish_count == 1
