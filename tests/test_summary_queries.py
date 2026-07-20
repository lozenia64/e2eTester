"""screen-shaped 질의 어댑터 — run/module/suite 요약 인덱스 SELECT 및 RunDeleted 정리."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.run.contracts.query_rows import Page, RunSummaryFilter
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.sqlite_module_history_query import SqliteModuleHistoryQuery
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.contexts.suite.domain.aggregate import SuiteAggregate
from app.contexts.suite.infrastructure.sqlite_suite_summary_query import SqliteSuiteSummaryQuery
from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.run_models import FailureAnalysis, Run, RunModule
from app.core.suite_models import SuiteRun, SuiteStep
from app.domain.events import run_deleted
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from tests.eventing_helpers import make_outbox_relay, make_projection_handlers


def _run(run_id: str, *, user: str | None = "u1", name: str | None = "홍길동") -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.login",
                name="로그인",
                group="auth",
                order=0,
                status=ModuleStatus.PENDING,
            ),
        ],
        selected_module_ids=["hom.login"],
        triggered_by="manual",
        created_by_user_id=user,
        created_by_user_name=name,
    )


class _Env:
    def __init__(self, db: SqliteDatabase) -> None:
        self.db = db
        self.write_repo = SqliteRunWriteRepository(db)
        self.projections = make_projection_handlers(db, self.write_repo)
        self.sequence = 0

    async def apply(self, events) -> None:
        for event in events:
            self.sequence += 1
            await self.projections.apply(event, self.sequence)


async def _env(tmp_path: Path, name: str) -> _Env:
    db = SqliteDatabase(tmp_path / name)
    await ensure_schema(db)
    return _Env(db)


async def _finish_run(env: _Env, run_id: str, status: ModuleStatus, **run_kwargs) -> None:
    run = _run(run_id, **run_kwargs)
    aggregate = RunAggregate.for_new_run(run)
    await env.write_repo.create_run(run, events=aggregate.pull_events())
    aggregate = RunAggregate(await env.write_repo.get_run(run_id))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=status,
        message="점검 결과",
        artifacts=[f"{run_id}/hom.login/final.png"],
        current_url="https://www.hwgeneralins.com/",
        dialog_messages=[],
    )
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    events = aggregate.pull_events()
    await env.write_repo.save_run(aggregate.persistable_state(), events=events)
    await env.apply(events)


@pytest.mark.asyncio
async def test_run_summary_filters_and_paging(tmp_path: Path) -> None:
    env = await _env(tmp_path, "summary.db")

    run_a = _run("run_a")
    agg_a = RunAggregate.for_new_run(run_a)
    await env.write_repo.create_run(run_a, events=(events_a := agg_a.pull_events()))
    await env.apply(events_a)

    run_b = _run("run_b", user="u2", name="김철수")
    agg_b = RunAggregate.for_new_run(run_b)
    await env.write_repo.create_run(run_b, events=agg_b.pull_events())
    agg_b = RunAggregate(await env.write_repo.get_run("run_b"))
    agg_b.begin()
    module = agg_b.module("hom.login")
    agg_b.mark_running(module)
    agg_b.record_result(
        module,
        status=ModuleStatus.PASSED,
        message="ok",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    agg_b.finish_timing(module)
    agg_b.finalize(None)
    await env.write_repo.save_run(agg_b.persistable_state(), events=(more_b := agg_b.pull_events()))
    await env.apply(more_b)

    query = SqliteRunSummaryQuery(env.db)

    all_rows = await query.list_summaries(RunSummaryFilter(), Page(limit=10))
    assert {row.run_id for row in all_rows} == {"run_a", "run_b"}

    passed_rows = await query.list_summaries(
        RunSummaryFilter(statuses=frozenset({RunStatus.PASSED})), Page()
    )
    assert [row.run_id for row in passed_rows] == ["run_b"]
    assert passed_rows[0].module_passed == 1
    assert passed_rows[0].system_name == "HOM"

    named = await query.list_summaries(RunSummaryFilter(user_name_query="철수"), Page())
    assert [row.run_id for row in named] == ["run_b"]

    assert await query.count(RunSummaryFilter(system_code="hom")) == 2
    counts = await query.counts_by_status()
    assert counts[RunStatus.PASSED.value] == 1

    paged = await query.list_summaries(RunSummaryFilter(), Page(limit=1, offset=1))
    assert len(paged) == 1


@pytest.mark.asyncio
async def test_module_history_rows_and_ai_enrichment(tmp_path: Path) -> None:
    env = await _env(tmp_path, "modules.db")
    await _finish_run(env, "run_mod", ModuleStatus.ANOMALY)

    history = SqliteModuleHistoryQuery(env.db)
    rows = await history.list_for_system("hom")
    assert len(rows) == 1
    row = rows[0]
    assert row.module_name == "로그인"
    assert row.status == ModuleStatus.ANOMALY
    assert row.duration_ms is not None
    assert row.artifacts == ("run_mod/hom.login/final.png",)
    assert row.current_url == "https://www.hwgeneralins.com/"
    assert row.triggered_by == "manual"

    # AI 실패 분석 부착 → ai_* 컬럼 갱신(fat event 경유, blob 미접근)
    aggregate = RunAggregate(await env.write_repo.get_run("run_mod"))
    module = aggregate.module("hom.login")
    aggregate.attach_failure_analysis(
        module,
        FailureAnalysis(
            category="selector_broken",
            probable_cause="셀렉터 변경",
            retryable=False,
            user_summary="로그인 버튼 셀렉터가 깨졌습니다.",
            developer_details="",
            recommended_action="셀렉터 갱신",
        ),
    )
    await env.apply(aggregate.pull_events())
    rows = await history.list_for_runs(["run_mod"])
    assert rows[0].ai_category == "selector_broken"
    assert rows[0].ai_summary == "로그인 버튼 셀렉터가 깨졌습니다."


@pytest.mark.asyncio
async def test_run_deleted_cleans_run_scoped_projections(tmp_path: Path) -> None:
    env = await _env(tmp_path, "deleted.db")
    await _finish_run(env, "run_del", ModuleStatus.ANOMALY)

    async def _counts() -> tuple[int, int, int]:
        run_rows = await env.db.fetchone("SELECT COUNT(*) AS c FROM run_history_index")
        module_rows = await env.db.fetchone("SELECT COUNT(*) AS c FROM module_history_index")
        anomaly_rows = await env.db.fetchone("SELECT COUNT(*) AS c FROM anomaly_inbox_index")
        return run_rows["c"], module_rows["c"], anomaly_rows["c"]

    assert await _counts() == (1, 1, 1)
    await env.apply([run_deleted("run_del")])
    assert await _counts() == (0, 0, 0)
    # 일간 현황은 "그날 점검했다"는 사실이므로 보존된다.
    daily = await env.db.fetchone("SELECT COUNT(*) AS c FROM daily_system_status")
    assert daily["c"] == 1


@pytest.mark.asyncio
async def test_suite_summary_rows(tmp_path: Path) -> None:
    env = await _env(tmp_path, "suites.db")
    suite = SuiteRun(
        suite_id="suite_q",
        status=SuiteStatus.PENDING,
        steps=[SuiteStep(system_code="hom", system_name="HOM", order=0, module_total=3)],
        requested_at=datetime.now(UTC),
        selected_system_codes=["hom"],
        created_by_user_name="홍길동",
    )
    aggregate = SuiteAggregate.for_new_suite(suite)
    aggregate.begin()
    step = aggregate.start_step(0)
    aggregate.link_run(step, "run_child")
    await env.apply(aggregate.pull_events())

    query = SqliteSuiteSummaryQuery(env.db)
    rows = await query.list_summaries()
    assert len(rows) == 1
    assert rows[0].status == SuiteStatus.RUNNING
    assert rows[0].steps[0].run_id == "run_child"
    assert rows[0].created_by_user_name == "홍길동"
    assert (await query.counts_by_status())[SuiteStatus.RUNNING.value] == 1
