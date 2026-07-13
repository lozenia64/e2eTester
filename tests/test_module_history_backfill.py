"""``module_history_index`` 스냅샷 backfill — 사용량 통계 모듈 집계 회귀."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.insights.application.stats_service import StatsService
from app.contexts.run.domain.aggregate import RunAggregate
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.domain.summary_fields import module_history_fields, run_summary_fields
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import _module_history_upsert, _run_history_upsert
from app.storage.module_history_backfill import backfill_module_history_index
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_stats_query import SqliteStatsQuery


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
                        estimated_manual_seconds=120,
                    ),
                    ModuleDefinition(
                        module_id="hom.contract",
                        system_code="hom",
                        name="contract",
                        description="",
                        group="biz",
                        order=1,
                        estimated_manual_seconds=60,
                    ),
                ],
            ),
        ]


def _two_module_run(run_id: str) -> Run:
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


def _passed_run(run_id: str) -> Run:
    module_id = "hom.login"
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id=module_id,
                name="login",
                group="auth",
                order=0,
                status=ModuleStatus.PASSED,
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                duration_ms=5000,
            ),
        ],
        selected_module_ids=[module_id],
        created_by_user_id="u1",
        created_by_user_name="테스터",
    )


@pytest.mark.asyncio
async def test_backfill_populates_module_history_for_stats(tmp_path: Path) -> None:
    """run_history 만 있는 Run → backfill 후 통과 모듈·절감 시간이 집계된다."""
    db = SqliteDatabase(tmp_path / "stats_gap.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)

    run = _passed_run("run_gap")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())

    # run_history_index 만 수동 채움(마이그레이션/backfill 직후 상황 재현)
    sql, params = _run_history_upsert(run.run_id, run_summary_fields(run))
    await db.execute(sql, params)

    before = await db.fetchone("SELECT COUNT(*) AS c FROM module_history_index")
    assert before["c"] == 0

    inserted = await backfill_module_history_index(db, write_repo)
    assert inserted == 1

    stats_query = SqliteStatsQuery(db)
    service = StatsService(
        stats_query=stats_query,
        suite_summary_query=_FakeSuiteSummaryQuery(),
        registry=_FakeRegistry(),
    )
    stats = await service.get_usage_stats()

    assert stats.total_runs == 1
    assert stats.by_system[0].modules_passed == 1
    assert stats.by_system[0].manual_seconds_saved == 120


@pytest.mark.asyncio
async def test_backfill_fills_partial_module_gap_without_overwriting(tmp_path: Path) -> None:
    """이미 일부 모듈 행이 있어도 누락 모듈만 추가한다(ai_* 보존)."""
    db = SqliteDatabase(tmp_path / "partial_gap.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)

    run = _two_module_run("run_partial")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())

    summary = run_summary_fields(run)
    login = run.modules[0]
    sql, params = _module_history_upsert(run.run_id, summary, module_history_fields(run, login))
    await db.execute(sql, params)
    await db.execute(
        """
        UPDATE module_history_index
        SET ai_category = 'test', ai_summary = 'keep', ai_action = 'keep'
        WHERE run_id = ? AND module_id = ?
        """,
        (run.run_id, login.module_id),
    )

    inserted = await backfill_module_history_index(db, write_repo)
    assert inserted == 1

    rows = await db.fetchall(
        "SELECT module_id, ai_category FROM module_history_index WHERE run_id = ? ORDER BY module_id",
        (run.run_id,),
    )
    assert [row["module_id"] for row in rows] == ["hom.contract", "hom.login"]
    login_row = next(row for row in rows if row["module_id"] == "hom.login")
    assert login_row["ai_category"] == "test"
