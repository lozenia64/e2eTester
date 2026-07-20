"""관리자 대시보드 Run 목록 상태 집합 — 사용량 통계와 분리 검증."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.status_labels import ADMIN_DASHBOARD_RUN_STATUSES, ADMIN_VISIBLE_RUN_STATUSES
from app.domain.summary_fields import run_summary_fields
from app.orchestrator.queries.run_queries import RunQueries
from app.platform.eventing.handlers import _run_history_upsert
from app.platform.eventing.support import SqliteDatabase, ensure_schema


def _run(run_id: str, status: RunStatus) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.login",
                name="로그인",
                group="auth",
                order=0,
                status=ModuleStatus.PASSED if status == RunStatus.PASSED else ModuleStatus.ANOMALY,
            ),
        ],
        selected_module_ids=["hom.login"],
        created_by_user_name="테스터",
    )


async def _seed_history(db: SqliteDatabase, runs: list[Run]) -> None:
    for index, run in enumerate(runs):
        # requested_at 순서를 고정해 필터 결과 검증이 안정적이게 한다.
        run = run.model_copy(update={"requested_at": datetime.now(UTC) - timedelta(minutes=index)})
        sql, params = _run_history_upsert(run.run_id, run_summary_fields(run))
        await db.execute(sql, params)


@pytest.mark.parametrize(
    ("status",),
    [
        (RunStatus.ERROR,),
        (RunStatus.CANCELLED,),
    ],
)
def test_admin_dashboard_includes_error_and_cancelled(status: RunStatus) -> None:
    assert status in ADMIN_DASHBOARD_RUN_STATUSES
    assert status not in ADMIN_VISIBLE_RUN_STATUSES


def test_admin_visible_excludes_error_and_cancelled() -> None:
    assert RunStatus.PASSED in ADMIN_VISIBLE_RUN_STATUSES
    assert RunStatus.ANOMALY in ADMIN_VISIBLE_RUN_STATUSES
    assert RunStatus.ERROR not in ADMIN_VISIBLE_RUN_STATUSES
    assert RunStatus.CANCELLED not in ADMIN_VISIBLE_RUN_STATUSES


@pytest.mark.asyncio
async def test_dashboard_status_sets_filter_run_history(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "admin_runs.db")
    await ensure_schema(db)
    runs = [
        _run("run_passed", RunStatus.PASSED),
        _run("run_anomaly", RunStatus.ANOMALY),
        _run("run_error", RunStatus.ERROR),
        _run("run_cancelled", RunStatus.CANCELLED),
    ]
    await _seed_history(db, runs)

    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )

    dashboard_rows = await queries.list_run_summaries(
        limit=100, run_statuses=ADMIN_DASHBOARD_RUN_STATUSES
    )
    visible_rows = await queries.list_run_summaries(
        limit=100, run_statuses=ADMIN_VISIBLE_RUN_STATUSES
    )

    assert {row["run_id"] for row in dashboard_rows} == {
        "run_passed",
        "run_anomaly",
        "run_error",
        "run_cancelled",
    }
    assert {row["run_id"] for row in visible_rows} == {"run_passed", "run_anomaly"}

    error_only = await queries.list_run_summaries(
        limit=100, run_statuses=frozenset({RunStatus.ERROR})
    )
    assert [row["run_id"] for row in error_only] == ["run_error"]
