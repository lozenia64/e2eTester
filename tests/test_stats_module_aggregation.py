"""사용량 통계 모듈 집계 — RunImported 프로젝션·fallback·스냅샷 backfill."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.insights.application.stats_service import StatsService
from app.contexts.run.domain.aggregate import RunAggregate
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.domain import events as domain_events
from app.domain.summary_fields import run_summary_fields
from app.eventsourcing.snapshot_rebuild import rebuild_missing_run_snapshots
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import ProjectionHandlers, _run_history_upsert
from app.storage.module_history_backfill import backfill_module_history_index
from app.storage.run_history_backfill import backfill_run_history_index
from app.storage.sqlite_module_history_query import SqliteModuleHistoryQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_stats_query import SqliteStatsQuery


class _Env:
    def __init__(self, db: SqliteDatabase) -> None:
        self.db = db
        self.write_repo = SqliteRunWriteRepository(db)
        self.projections = ProjectionHandlers(db, self.write_repo)
        self.sequence = 0

    async def apply(self, events) -> None:
        for event in events:
            self.sequence += 1
            await self.projections.apply(event, self.sequence)


class _FakeSuiteSummaryQuery:
    async def list_summaries(self, *, limit: int | None = None):
        return []

    async def counts_by_status(self) -> dict[str, int]:
        return {}


class _FakeRegistry:
    def list_systems(self) -> list[SystemDefinition]:
        return [
            SystemDefinition(
                system_code="hom",
                name="HOM",
                description="",
                modules=[
                    ModuleDefinition(
                        module_id="hom.login",
                        system_code="hom",
                        name="login",
                        description="",
                        group="auth",
                        order=0,
                        estimated_manual_seconds=90,
                    ),
                    ModuleDefinition(
                        module_id="hom.contract",
                        system_code="hom",
                        name="contract",
                        description="",
                        group="biz",
                        order=1,
                        estimated_manual_seconds=30,
                    ),
                ],
            ),
        ]


def _module_wire(module: RunModule) -> dict:
    wire = module.model_dump(mode="json")
    wire.pop("logs", None)
    return wire


def _passed_run(run_id: str) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.login",
                name="login",
                group="auth",
                order=0,
                status=ModuleStatus.PASSED,
                duration_ms=4000,
            ),
            RunModule(
                module_id="hom.contract",
                name="contract",
                group="biz",
                order=1,
                status=ModuleStatus.PASSED,
                duration_ms=6000,
            ),
        ],
        selected_module_ids=["hom.login", "hom.contract"],
    )


@pytest.mark.asyncio
async def test_run_imported_populates_module_history_index(tmp_path: Path) -> None:
    env = _Env(SqliteDatabase(tmp_path / "imported.db"))
    await ensure_schema(env.db)

    run = _passed_run("run_imported")
    event = domain_events.run_imported(
        run.run_id,
        run_summary=run_summary_fields(run),
        all_modules=[_module_wire(module) for module in run.modules],
    )
    await env.apply([event])

    rows = await SqliteModuleHistoryQuery(env.db).list_for_runs([run.run_id])
    assert len(rows) == 2
    assert {row.module_id for row in rows} == {"hom.login", "hom.contract"}
    assert all(row.duration_ms for row in rows)


@pytest.mark.asyncio
async def test_stats_aggregates_modules_and_savings_from_history(tmp_path: Path) -> None:
    env = _Env(SqliteDatabase(tmp_path / "aggregate.db"))
    await ensure_schema(env.db)

    run = _passed_run("run_stats")
    aggregate = RunAggregate.for_new_run(run)
    await env.write_repo.create_run(run, events=aggregate.pull_events())
    aggregate = RunAggregate(await env.write_repo.get_run(run.run_id))
    aggregate.begin()
    for module in run.modules:
        mod = aggregate.module(module.module_id)
        aggregate.mark_running(mod)
        aggregate.record_result(
            mod,
            status=ModuleStatus.PASSED,
            message="ok",
            artifacts=[],
            current_url=None,
            dialog_messages=[],
        )
        aggregate.finish_timing(mod)
    aggregate.finalize(None)
    events = aggregate.pull_events()
    await env.write_repo.save_run(aggregate.persistable_state(), events=events)
    await env.apply(events)

    sql, params = _run_history_upsert(run.run_id, run_summary_fields(aggregate.persistable_state()))
    await env.db.execute(sql, params)

    service = StatsService(
        stats_query=SqliteStatsQuery(env.db),
        suite_summary_query=_FakeSuiteSummaryQuery(),
        registry=_FakeRegistry(),
    )
    stats = await service.get_usage_stats()

    assert stats.total_runs == 1
    assert stats.by_system[0].modules_passed == 2
    assert stats.by_system[0].manual_seconds_saved == 120


@pytest.mark.asyncio
async def test_stats_fallback_uses_run_summary_module_passed(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "fallback.db")
    await ensure_schema(db)

    run = _passed_run("run_fallback")
    summary = run_summary_fields(run)
    summary["module_passed"] = 2
    sql, params = _run_history_upsert(run.run_id, summary)
    await db.execute(sql, params)

    service = StatsService(
        stats_query=SqliteStatsQuery(db),
        suite_summary_query=_FakeSuiteSummaryQuery(),
        registry=_FakeRegistry(),
    )
    stats = await service.get_usage_stats()

    assert stats.total_runs == 1
    assert stats.by_system[0].modules_passed == 2
    assert stats.by_system[0].manual_seconds_saved == 0


@pytest.mark.asyncio
async def test_missing_snapshot_rebuild_enables_module_backfill(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "missing_snap.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)

    run = _passed_run("run_missing_snap")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())
    await db.execute("DELETE FROM aggregate_snapshots WHERE stream_id = ?", (f"Run:{run.run_id}",))

    rebuilt = await rebuild_missing_run_snapshots(db)
    assert rebuilt == 1
    await backfill_run_history_index(db, write_repo)

    inserted = await backfill_module_history_index(db, write_repo)
    assert inserted == 2

    service = StatsService(
        stats_query=SqliteStatsQuery(db),
        suite_summary_query=_FakeSuiteSummaryQuery(),
        registry=_FakeRegistry(),
    )
    stats = await service.get_usage_stats()
    assert stats.by_system[0].modules_passed == 2
    assert stats.by_system[0].manual_seconds_saved == 120
