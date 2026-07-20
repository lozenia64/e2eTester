"""RunQueries.list_run_summaries / SuiteService.list_suite_summaries scope 필터 단위 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
from app.contexts.run.infrastructure.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.contexts.suite.application.service import SuiteService
from app.contexts.suite.domain.aggregate import SuiteAggregate
from app.contexts.suite.infrastructure.sqlite_suite_summary_query import SqliteSuiteSummaryQuery
from app.contexts.suite.infrastructure.sqlite_suite_write_repository import (
    SqliteSuiteWriteRepository,
)
from app.core.enums import RunStatus, SuiteStatus
from app.core.run_models import Run, RunModule
from app.core.suite_models import SuiteRun, SuiteStep
from app.orchestrator.queries import RunQueries
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from tests.eventing_helpers import suite_events_as_envelopes


class _SuiteEnv:
    def __init__(self, db: SqliteDatabase) -> None:
        self.db = db
        self.write_repo = SqliteSuiteWriteRepository(db)
        self.projections = ProjectionHandlers(db, SqliteRunWriteRepository(db))
        self.sequence = 0

    async def apply(self, suite_id: str, events) -> None:
        for event in suite_events_as_envelopes(suite_id, events):
            self.sequence += 1
            await self.projections.apply(event, self.sequence)


async def _suite_env(tmp_path: Path, name: str) -> _SuiteEnv:
    db = SqliteDatabase(tmp_path / name)
    await ensure_schema(db)
    return _SuiteEnv(db)


async def _persist_suite(
    env: _SuiteEnv,
    suite_id: str,
    *,
    requested_at: datetime,
    status: SuiteStatus,
) -> None:
    suite = SuiteRun(
        suite_id=suite_id,
        status=SuiteStatus.PENDING,
        steps=[SuiteStep(system_code="hom", system_name="HOM", order=0)],
        requested_at=requested_at,
        selected_system_codes=["hom"],
    )
    aggregate = SuiteAggregate.for_new_suite(suite)
    await env.write_repo.create_suite(suite, events=(created := aggregate.pull_events()))
    await env.apply(suite_id, created)

    aggregate = SuiteAggregate(await env.write_repo.get_suite(suite_id))
    aggregate.begin()
    step = aggregate.start_step(0)
    aggregate.link_run(step, f"run_{suite_id}")
    if status == SuiteStatus.PASSED:
        aggregate.record_step_result(step, SuiteStatus.PASSED, step_index=0)
        aggregate.finalize(SuiteStatus.PASSED)
    events = aggregate.pull_events()
    await env.write_repo.save_suite(aggregate.persistable_state(), events=events)
    await env.apply(suite_id, events)


def _suite_service(query: SqliteSuiteSummaryQuery) -> SuiteService:
    service = SuiteService.__new__(SuiteService)
    service._summary_query = query
    return service


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


def test_list_suite_summaries_scope_today_and_before_today(tmp_path: Path):
    asyncio.run(_assert_suite_scope_filters(tmp_path))


async def _assert_suite_scope_filters(tmp_path: Path) -> None:
    env = await _suite_env(tmp_path, "suite_scope.db")
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=1)
    today_afternoon = today_start + timedelta(hours=10)

    await _persist_suite(
        env,
        "suite_yesterday_passed",
        requested_at=yesterday,
        status=SuiteStatus.PASSED,
    )
    await _persist_suite(
        env,
        "suite_today_passed",
        requested_at=today_afternoon,
        status=SuiteStatus.PASSED,
    )
    await _persist_suite(
        env,
        "suite_yesterday_running",
        requested_at=yesterday,
        status=SuiteStatus.RUNNING,
    )

    service = _suite_service(SqliteSuiteSummaryQuery(env.db))

    today_ids = {item["suite_id"] for item in await service.list_suite_summaries(scope="today")}
    assert today_ids == {"suite_today_passed", "suite_yesterday_running"}

    before_ids = {
        item["suite_id"] for item in await service.list_suite_summaries(scope="before_today")
    }
    assert before_ids == {"suite_yesterday_passed"}

    all_ids = {item["suite_id"] for item in await service.list_suite_summaries()}
    assert all_ids == {"suite_today_passed", "suite_yesterday_passed", "suite_yesterday_running"}
