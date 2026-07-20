"""레거시 ``runs`` blob → 프로젝션 인덱스 backfill."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.insights.application.stats_service import StatsService
from app.contexts.insights.infrastructure.sqlite_stats_query import SqliteStatsQuery
from app.contexts.run.contracts.records import RunRecord
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.backfill.legacy_runs_projection_backfill import (
    backfill_from_legacy_runs,
)
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.domain.summary_fields import run_summary_fields
from app.platform.eventing.handlers import _run_history_upsert
from app.platform.eventing.support import SqliteDatabase, ensure_schema


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
                duration_ms=1000,
            ),
            RunModule(
                module_id="hom.contract",
                name="contract",
                group="biz",
                order=1,
                status=ModuleStatus.PASSED,
                duration_ms=2000,
            ),
        ],
        selected_module_ids=["hom.login", "hom.contract"],
    )


@pytest.mark.asyncio
async def test_legacy_blob_backfill_populates_module_stats(tmp_path: Path) -> None:
    """thin-event 스냅샷 + 레거시 blob → 통과 모듈·절감 시간 집계."""
    db = SqliteDatabase(tmp_path / "legacy.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)

    run = _passed_run("run_thin")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
        """
    )
    await db.execute(
        "INSERT INTO runs (id, data) VALUES (?, ?)",
        (run.run_id, RunRecord.serialize(run)),
    )

    summary = run_summary_fields(run)
    summary["module_passed"] = None
    sql, params = _run_history_upsert(run.run_id, summary)
    await db.execute(sql, params)

    report = await backfill_from_legacy_runs(db, write_repo)
    assert report.module_rows == 2
    assert report.run_rows == 1

    stats = await StatsService(
        stats_query=SqliteStatsQuery(db),
        suite_summary_query=_FakeSuiteSummaryQuery(),
        registry=_FakeRegistry(),
    ).get_usage_stats()

    assert stats.by_system[0].modules_passed == 2
    assert stats.by_system[0].manual_seconds_saved == 120
