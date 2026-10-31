"""Outbox 릴레이 통합 테스트 — 프로젝션 + 실시간 WS payload."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.run.contracts.query_rows import Page, RunSummaryFilter
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.hydration import RunHydrator, RunProjectionLoader
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.platform.eventing.bus import EventBus
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.relay import OutboxRelay
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.projector import RealtimeProjector
from tests.eventing_helpers import make_outbox_relay, make_projection_handlers


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
    history = SqliteRunSummaryQuery(db)
    projections = make_projection_handlers(db, write_repo)
    outbox = SqliteOutbox(db)
    run_realtime = RealtimeNotificationAdapter()
    suite_realtime = SuiteRealtimeNotificationAdapter()
    projector = RealtimeProjector(run_realtime, suite_realtime)
    relay = make_outbox_relay(outbox, projections, write_repo, EventBus(), projector)

    run = _sample_run()
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())
    assert await relay.process_once() == 1

    rows = await history.list_summaries(RunSummaryFilter(), Page(limit=10))
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
    projections = make_projection_handlers(db, write_repo)
    outbox = SqliteOutbox(db)
    run_realtime = RealtimeNotificationAdapter()
    suite_realtime = SuiteRealtimeNotificationAdapter()
    projector = RealtimeProjector(run_realtime, suite_realtime)
    relay = make_outbox_relay(outbox, projections, write_repo, EventBus(), projector)

    run = _sample_run("run_ws")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())

    queue = await run_realtime.subscribe("run_ws")
    assert await relay.process_once() == 1
    event = await queue.get()
    assert event.event_type == "run_created"
    assert event.run_id == "run_ws"
    assert event.payload["run_id"] == "run_ws"
    # RunView 계약(스키마 고정): run_* WS payload 는 fat event 요약만으로 조립된다.
    assert event.payload["system_code"] == "hom"
    assert event.payload["status_label"]
    assert event.payload["modules"] == []  # run_* 이벤트는 모듈 목록을 싣지 않는다


@pytest.mark.asyncio
async def test_projector_module_and_run_events_are_blob_free(tmp_path: Path) -> None:
    """실시간 프로젝터가 blob/로그 스토어 없이 module_*·run_* WS payload 를 만든다."""
    db = SqliteDatabase(tmp_path / "blobfree.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = make_projection_handlers(db, write_repo)
    outbox = SqliteOutbox(db)
    run_realtime = RealtimeNotificationAdapter()
    projector = RealtimeProjector(run_realtime, SuiteRealtimeNotificationAdapter())
    relay = make_outbox_relay(outbox, projections, write_repo, EventBus(), projector)

    run = _sample_run("run_bf")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())
    await relay.process_once()

    queue = await run_realtime.subscribe("run_bf")

    aggregate = RunAggregate(await write_repo.get_run("run_bf"))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_queued(module)
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=ModuleStatus.PASSED,
        message="ok",
        artifacts=["run_bf/hom.login/final.png"],
        current_url="https://www.hwgeneralins.com/",
        dialog_messages=[],
    )
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    await write_repo.save_run(aggregate.persistable_state(), events=aggregate.pull_events())
    assert await relay.process_once() >= 1

    events = []
    while not queue.empty():
        events.append(await queue.get())
    by_type = {event.event_type: event for event in events}

    # module_* 이벤트는 임베드된 module 와이어 dict + run_status 로 조립된다(ModuleView 계약).
    finished = by_type["module_finished"]
    assert finished.payload["module"]["module_id"] == "hom.login"
    assert finished.payload["module"]["status"] == ModuleStatus.PASSED.value
    assert "logs" not in finished.payload["module"]  # 로그는 이벤트에 싣지 않는다
    assert finished.payload["run_status"]
    # run_finished 는 run_summary 로 조립된다(RunView 계약).
    assert by_type["run_finished"].payload["status"] == RunStatus.PASSED.value


@pytest.mark.asyncio
async def test_outbox_dead_letter_on_projection_failure(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "dlq.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)

    class BrokenProjections(ProjectionHandlers):
        async def apply(self, event, sequence_id) -> None:
            raise RuntimeError("projection boom")

    outbox = SqliteOutbox(db)
    run_realtime = RealtimeNotificationAdapter()
    suite_realtime = SuiteRealtimeNotificationAdapter()
    projector = RealtimeProjector(run_realtime, suite_realtime)
    relay = OutboxRelay(
        outbox,
        BrokenProjections(db, loaders={"Run": RunProjectionLoader(write_repo)}),
        hydrators={"Run": RunHydrator(write_repo)},
        event_bus=EventBus(),
        realtime=projector,
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
