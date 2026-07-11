"""Outbox 릴레이 통합 테스트 — 프로젝션 + 실시간 WS payload."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run, RunModule
from app.domain.run_aggregate import RunAggregate
from app.events.bus import EventBus
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.relay import OutboxRelay
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import ProjectionHandlers
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.projector import RealtimeProjector
from app.storage.sqlite_run_history_query import SqliteRunHistoryQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_suite_write_repository import SqliteSuiteWriteRepository


def _sample_run(run_id: str = "run_test") -> Run:
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
async def test_run_create_projects_history_index(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    suite_write_repo = SqliteSuiteWriteRepository(db)
    history = SqliteRunHistoryQuery(db, write_repo)
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
    relay = OutboxRelay(
        outbox,
        projections,
        write_repo,
        EventBus(),
        projector,
    )

    run = _sample_run()
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())
    assert await relay.process_once() == 1

    rows = await history.list_all_runs()
    assert len(rows) == 1
    assert rows[0].run_id == "run_test"
    assert rows[0].system_code == "hom"

    aggregate = RunAggregate(await write_repo.get_run("run_test"))
    aggregate.begin()
    await write_repo.save_run(aggregate.persistable_state(), events=aggregate.pull_events())
    assert await relay.process_once() == 1

    row = await db.fetchone(
        "SELECT status FROM run_history_index WHERE run_id = ?",
        ("run_test",),
    )
    assert row is not None
    assert row["status"] == RunStatus.RUNNING.value


@pytest.mark.asyncio
async def test_relay_emits_realtime_ws_payload(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "relay.db")
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
    relay = OutboxRelay(outbox, projections, write_repo, EventBus(), projector)

    run = _sample_run("run_ws")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())

    queue = await run_realtime.subscribe("run_ws")
    assert await relay.process_once() == 1
    event = await queue.get()
    assert event.event_type == "run_created"
    assert event.run_id == "run_ws"
    assert event.payload["run_id"] == "run_ws"


@pytest.mark.asyncio
async def test_outbox_dead_letter_on_projection_failure(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "dlq.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    suite_write_repo = SqliteSuiteWriteRepository(db)

    class BrokenProjections(ProjectionHandlers):
        async def apply(self, event) -> None:
            raise RuntimeError("projection boom")

    outbox = SqliteOutbox(db)
    run_realtime = RealtimeNotificationAdapter()
    suite_realtime = SuiteRealtimeNotificationAdapter()
    projector = RealtimeProjector(
        run_realtime,
        suite_realtime,
        run_loader=write_repo.get_run,
        suite_loader=suite_write_repo.get_suite,
    )
    relay = OutboxRelay(
        outbox,
        BrokenProjections(db, write_repo),
        write_repo,
        EventBus(),
        projector,
    )

    run = _sample_run("run_dlq")
    aggregate = RunAggregate.for_new_run(run)
    events = aggregate.pull_events()
    await write_repo.create_run(run, events=events)
    assert await relay.process_once() == 0

    rows = await db.fetchall(
        "SELECT event_id, event_type, error_message FROM outbox_dead_letter",
    )
    assert len(rows) == 1
    assert rows[0]["event_id"] == events[0].event_id
    assert rows[0]["event_type"] == "RunCreated"
    assert "projection boom" in rows[0]["error_message"]

    pending = await db.fetchone(
        "SELECT 1 FROM outbox WHERE published_at IS NULL",
    )
    assert pending is None
