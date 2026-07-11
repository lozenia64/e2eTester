"""프로젝션 핸들러 단위·통합 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run, RunModule
from app.domain.run_aggregate import RunAggregate
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import ProjectionHandlers
from app.scheduling.scheduler import schedule_today_label
from app.storage.sqlite_anomaly_inbox_query import SqliteAnomalyInboxQuery
from app.storage.sqlite_daily_status_query import SqliteDailyStatusQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_stats_query import SqliteStatsQuery


def _sample_run(run_id: str = "run_proj") -> Run:
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
async def test_module_completed_updates_anomaly_and_daily_projections(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "proj.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = ProjectionHandlers(db, write_repo)

    run = _sample_run()
    aggregate = RunAggregate.for_new_run(run)
    created_events = aggregate.pull_events()
    await write_repo.create_run(run, events=created_events)
    sequence = 0
    for event in created_events:
        sequence += 1
        await projections.apply(event, sequence)

    aggregate = RunAggregate(await write_repo.get_run("run_proj"))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=ModuleStatus.ANOMALY,
        message="broken",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    mutation_events = aggregate.pull_events()
    await write_repo.save_run(aggregate.persistable_state(), events=mutation_events)
    for event in mutation_events:
        sequence += 1
        await projections.apply(event, sequence)

    inbox = SqliteAnomalyInboxQuery(db)
    rows = await inbox.list_page(None)
    assert len(rows) == 1
    assert rows[0].module_run_id == "run_proj::hom.login"

    daily = SqliteDailyStatusQuery(db)
    day_rows = await daily.list_for_date(schedule_today_label(), None)
    assert any(row.module_id == "hom.login" for row in day_rows)

    stats = SqliteStatsQuery(db, write_repo)
    rollups = await stats.rollup_between(None, None)
    assert rollups
    assert rollups[0].anomaly_count >= 1
