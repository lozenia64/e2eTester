"""RunQueries.list_run_summaries scope(today/before_today) 필터 단위 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.enums import RunStatus
from app.core.run_models import Run, RunModule
from app.orchestrator.queries import RunQueries
from app.storage.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.storage.run_log_store import InMemoryRunLogStore
from app.storage.run_repository import InMemoryRunRepository


def _run(
    run_id: str,
    *,
    status: RunStatus,
    requested_at: datetime,
) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=requested_at,
        modules=[
            RunModule(
                module_id="hom.login",
                name="login",
                group="auth",
                order=0,
                status=status,
            ),
        ],
        selected_module_ids=["hom.login"],
    )


def _queries() -> tuple[RunQueries, InMemoryRunRepository]:
    repo = InMemoryRunRepository()
    queries = RunQueries(InMemoryRunSummaryQuery(repo), repo, InMemoryRunLogStore())
    return queries, repo


def test_list_run_summaries_scope_today_and_before_today():
    asyncio.run(_assert_scope_filters())


async def _assert_scope_filters() -> None:
    queries, repo = _queries()
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=1)
    today_afternoon = today_start + timedelta(hours=10)

    runs = [
        _run("run_yesterday_passed", status=RunStatus.PASSED, requested_at=yesterday),
        _run("run_today_passed", status=RunStatus.PASSED, requested_at=today_afternoon),
        _run("run_yesterday_waiting", status=RunStatus.WAITING_INPUT, requested_at=yesterday),
    ]
    for run in runs:
        await repo.save_run(run)

    today_ids = {item["run_id"] for item in await queries.list_run_summaries(scope="today")}
    assert today_ids == {"run_today_passed", "run_yesterday_waiting"}

    before_ids = {item["run_id"] for item in await queries.list_run_summaries(scope="before_today")}
    assert before_ids == {"run_yesterday_passed"}

    all_ids = {item["run_id"] for item in await queries.list_run_summaries()}
    assert all_ids == {"run_today_passed", "run_yesterday_passed", "run_yesterday_waiting"}


def test_scope_today_always_includes_active_runs_even_at_limit():
    asyncio.run(_assert_active_runs_not_dropped_at_limit())


async def _assert_active_runs_not_dropped_at_limit() -> None:
    queries, repo = _queries()
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=1)

    runs = [
        _run("run_yesterday_waiting", status=RunStatus.WAITING_INPUT, requested_at=yesterday),
    ]
    for index in range(5):
        runs.append(
            _run(
                f"run_today_{index}",
                status=RunStatus.PASSED,
                requested_at=today_start + timedelta(hours=index + 1),
            )
        )
    for run in runs:
        await repo.save_run(run)

    today_ids = {
        item["run_id"] for item in await queries.list_run_summaries(scope="today", limit=3)
    }
    assert "run_yesterday_waiting" in today_ids
    assert len(today_ids) == 3
