"""Run 명령 → 이벤트 store → 프로젝션 통합 테스트."""

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
from app.storage.sqlite_run_history_query import SqliteRunHistoryQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


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
    history = SqliteRunHistoryQuery(db, write_repo)
    projections = ProjectionHandlers(db, write_repo)
    outbox = SqliteOutbox(db)
    relay = OutboxRelay(
        outbox,
        projections,
        write_repo,
        EventBus(),
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
    await write_repo.save_run(aggregate.snapshot, events=aggregate.pull_events())
    assert await relay.process_once() == 1

    row = await db.fetchone(
        "SELECT status FROM run_history_index WHERE run_id = ?",
        ("run_test",),
    )
    assert row is not None
    assert row["status"] == RunStatus.RUNNING.value
