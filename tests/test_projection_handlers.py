"""프로젝션 핸들러 단위·통합 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.insights.infrastructure.sqlite_anomaly_inbox_query import SqliteAnomalyInboxQuery
from app.contexts.insights.infrastructure.sqlite_daily_status_query import SqliteDailyStatusQuery
from app.contexts.insights.infrastructure.sqlite_stats_query import SqliteStatsQuery
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.contexts.scheduling.scheduler import schedule_today_label
from app.contexts.suite.domain.aggregate import SuiteAggregate
from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.run_models import Run, RunModule
from app.core.suite_models import SuiteRun, SuiteStep
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from tests.eventing_helpers import (
    make_outbox_relay,
    make_projection_handlers,
    run_events_as_envelopes,
    suite_events_as_envelopes,
)


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
    projections = make_projection_handlers(db, write_repo)

    run = _sample_run()
    aggregate = RunAggregate.for_new_run(run)
    created_events = aggregate.pull_events()
    await write_repo.create_run(run, events=created_events)
    sequence = 0
    for event in run_events_as_envelopes("run_proj", created_events):
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
    for event in run_events_as_envelopes("run_proj", mutation_events):
        sequence += 1
        await projections.apply(event, sequence)

    inbox = SqliteAnomalyInboxQuery(db)
    rows = await inbox.list_page(None)
    assert len(rows) == 1
    assert rows[0].module_run_id == "run_proj::hom.login"

    daily = SqliteDailyStatusQuery(db)
    day_rows = await daily.list_for_date(schedule_today_label(), None)
    assert any(row.module_id == "hom.login" for row in day_rows)

    stats = SqliteStatsQuery(db)
    rollups = await stats.rollup_between(None, None)
    assert rollups
    assert rollups[0].anomaly_count >= 1

    # fat event 경로: 요약 인덱스가 blob 재수화 없이 화면형 컬럼까지 채운다.
    history_row = await db.fetchone(
        """
        SELECT system_name, module_total, module_passed, failed_module_name, status
        FROM run_history_index WHERE run_id = ?
        """,
        ("run_proj",),
    )
    assert history_row is not None
    assert history_row["system_name"] == "HOM"
    assert history_row["module_total"] == 1
    assert history_row["module_passed"] == 0
    assert history_row["failed_module_name"] == "login"
    assert history_row["status"] == RunStatus.ANOMALY.value

    # 일간 현황 프로젝션이 duration_ms 를 이벤트 payload 에서 직접 얻는다(blob 재읽기 제거).
    daily_row = await db.fetchone(
        "SELECT duration_ms FROM daily_system_status WHERE module_id = ?",
        ("hom.login",),
    )
    assert daily_row is not None
    assert daily_row["duration_ms"] is not None


@pytest.mark.asyncio
async def test_module_recovery_updates_daily_projection_recovered_flag(tmp_path: Path) -> None:
    """재시도 끝에 통과한 모듈은 daily_system_status 프로젝션에도 recovered=True 로 반영된다.

    자동 복구 가시성(설계 §3.4)은 세 화면(Run 상세·일간 현황·완료 메일)에 함께 노출되어야
    하고, 일간 현황은 이 프로젝션을 읽어 채운다 — 프로젝션이 신호를 안 들고 있으면 화면에
    영영 뜨지 않는다.
    """
    from app.core.enums import FailureSignal, RecoveryTier

    db = SqliteDatabase(tmp_path / "proj_recovered.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = make_projection_handlers(db, write_repo)

    run = _sample_run("run_proj_recovered")
    aggregate = RunAggregate.for_new_run(run)
    created_events = aggregate.pull_events()
    await write_repo.create_run(run, events=created_events)
    sequence = 0
    for event in run_events_as_envelopes("run_proj_recovered", created_events):
        sequence += 1
        await projections.apply(event, sequence)

    aggregate = RunAggregate(await write_repo.get_run("run_proj_recovered"))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_running(module)
    aggregate.record_retry(
        module, tier=RecoveryTier.RETRY_IN_PLACE, failure_signal=FailureSignal.TIMEOUT
    )
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=ModuleStatus.PASSED,
        message="통과",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    aggregate.record_recovered(module)
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    mutation_events = aggregate.pull_events()
    await write_repo.save_run(aggregate.persistable_state(), events=mutation_events)
    for event in run_events_as_envelopes("run_proj_recovered", mutation_events):
        sequence += 1
        await projections.apply(event, sequence)

    daily = SqliteDailyStatusQuery(db)
    day_rows = await daily.list_for_date(schedule_today_label(), None)
    row = next(r for r in day_rows if r.module_id == "hom.login")
    assert row.recovered is True


@pytest.mark.asyncio
async def test_module_without_retry_leaves_daily_projection_recovered_false(
    tmp_path: Path,
) -> None:
    """재시도 없이 바로 통과한 모듈은 recovered=False 로 남는다."""
    db = SqliteDatabase(tmp_path / "proj_clean.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = make_projection_handlers(db, write_repo)

    run = _sample_run("run_proj_clean")
    aggregate = RunAggregate.for_new_run(run)
    created_events = aggregate.pull_events()
    await write_repo.create_run(run, events=created_events)
    sequence = 0
    for event in run_events_as_envelopes("run_proj_clean", created_events):
        sequence += 1
        await projections.apply(event, sequence)

    aggregate = RunAggregate(await write_repo.get_run("run_proj_clean"))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=ModuleStatus.PASSED,
        message="통과",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    aggregate.record_recovered(module)  # retry_count == 0 이므로 no-op
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    mutation_events = aggregate.pull_events()
    await write_repo.save_run(aggregate.persistable_state(), events=mutation_events)
    for event in run_events_as_envelopes("run_proj_clean", mutation_events):
        sequence += 1
        await projections.apply(event, sequence)

    daily = SqliteDailyStatusQuery(db)
    day_rows = await daily.list_for_date(schedule_today_label(), None)
    row = next(r for r in day_rows if r.module_id == "hom.login")
    assert row.recovered is False


@pytest.mark.asyncio
async def test_suite_events_project_suite_history_index(tmp_path: Path) -> None:
    """Suite fat event 가 suite_history_index 를 blob 재수화 없이 채운다."""
    db = SqliteDatabase(tmp_path / "suite_proj.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = make_projection_handlers(db, write_repo)

    suite = SuiteRun(
        suite_id="suite_proj",
        status=SuiteStatus.PENDING,
        steps=[
            SuiteStep(system_code="hom", system_name="HOM", order=0, module_total=3),
            SuiteStep(system_code="mhm", system_name="MHM", order=1, module_total=2),
        ],
        requested_at=datetime.now(UTC),
        selected_system_codes=["hom", "mhm"],
        triggered_by="manual",
    )
    aggregate = SuiteAggregate.for_new_suite(suite)
    aggregate.begin()
    step = aggregate.start_step(0)
    aggregate.link_run(step, "run_child_1")

    sequence = 0
    for event in suite_events_as_envelopes("suite_proj", aggregate.pull_events()):
        sequence += 1
        await projections.apply(event, sequence)

    row = await db.fetchone(
        """
        SELECT status, step_total, active_run_id, selected_system_codes, steps
        FROM suite_history_index WHERE suite_id = ?
        """,
        ("suite_proj",),
    )
    assert row is not None
    assert row["status"] == SuiteStatus.RUNNING.value
    assert row["step_total"] == 2
    assert row["active_run_id"] == "run_child_1"
    assert "hom" in row["selected_system_codes"]
    steps = __import__("json").loads(row["steps"])
    assert steps[0]["run_id"] == "run_child_1"
    assert steps[0]["status"] == SuiteStatus.RUNNING.value
