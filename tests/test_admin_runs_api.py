"""관리자 Run 이력 API — 페이지네이션·보드·필터."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.contexts.run.contracts.query_rows import RunSummaryFilter
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.domain.summary_fields import run_summary_fields
from app.orchestrator.queries.run_queries import RunQueries
from app.platform.eventing.handlers import _run_history_upsert
from app.platform.eventing.support import SqliteDatabase, ensure_schema

KST = ZoneInfo("Asia/Seoul")


def _run(
    run_id: str,
    status: RunStatus,
    *,
    triggered_by: str = "manual",
    requested_at: datetime | None = None,
    suite_id: str | None = None,
    schedule_id: str | None = None,
) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=requested_at or datetime.now(UTC),
        triggered_by=triggered_by,
        suite_id=suite_id,
        schedule_id=schedule_id,
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


async def _seed(db: SqliteDatabase, runs: list[Run], *, preserve_time: bool = False) -> None:
    seeded: list[Run] = []
    for index, run in enumerate(runs):
        if not preserve_time:
            run = run.model_copy(
                update={"requested_at": datetime.now(UTC) - timedelta(minutes=index)}
            )
        seeded.append(run)
        sql, params = _run_history_upsert(run.run_id, run_summary_fields(run))
        await db.execute(sql, params)
    await _seed_system_last_finished(db, seeded)


async def _seed_system_last_finished(db: SqliteDatabase, runs: list[Run]) -> None:
    terminal = {
        RunStatus.PASSED,
        RunStatus.ANOMALY,
        RunStatus.ERROR,
        RunStatus.FAILED,
    }
    for run in runs:
        if run.status not in terminal:
            continue
        moment = run.ended_at or run.requested_at
        await db.execute(
            """
            INSERT INTO system_last_finished (system_code, last_finished_at)
            VALUES (?, ?)
            ON CONFLICT(system_code) DO UPDATE SET
                last_finished_at = excluded.last_finished_at
            WHERE excluded.last_finished_at > system_last_finished.last_finished_at
            """,
            (run.system_code, moment.isoformat()),
        )


@pytest.mark.asyncio
async def test_list_run_summaries_page_offset_and_total(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "page.db")
    await ensure_schema(db)
    await _seed(db, [_run(f"run_{i}", RunStatus.PASSED) for i in range(5)])

    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )
    page = await queries.list_run_summaries_page(limit=2, offset=0)
    assert page["total"] == 5
    assert len(page["items"]) == 2

    page2 = await queries.list_run_summaries_page(limit=2, offset=2)
    assert page2["total"] == 5
    assert len(page2["items"]) == 2
    assert page["items"][0]["run_id"] != page2["items"][0]["run_id"]


@pytest.mark.asyncio
async def test_list_run_summaries_page_multi_status_filter(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "multi.db")
    await ensure_schema(db)
    await _seed(
        db,
        [
            _run("run_ok", RunStatus.PASSED),
            _run("run_anomaly", RunStatus.ANOMALY),
            _run("run_error", RunStatus.ERROR),
            _run("run_legacy", RunStatus.FAILED),
        ],
    )
    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )
    page = await queries.list_run_summaries_page(
        limit=10,
        run_statuses=frozenset({RunStatus.ANOMALY, RunStatus.ERROR, RunStatus.FAILED}),
    )
    assert page["total"] == 3
    assert {item["run_id"] for item in page["items"]} == {
        "run_anomaly",
        "run_error",
        "run_legacy",
    }


@pytest.mark.asyncio
async def test_list_run_summaries_page_triggered_by_filter(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "trigger.db")
    await ensure_schema(db)
    await _seed(
        db,
        [
            _run("run_manual", RunStatus.PASSED, triggered_by="manual"),
            _run("run_suite", RunStatus.PASSED, triggered_by="suite", suite_id="suite_1"),
            _run(
                "run_schedule",
                RunStatus.PASSED,
                triggered_by="schedule",
                schedule_id="sched_1",
            ),
        ],
    )
    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )
    suite_page = await queries.list_run_summaries_page(limit=10, triggered_by="suite")
    assert suite_page["total"] == 1
    assert suite_page["items"][0]["run_id"] == "run_suite"
    assert suite_page["items"][0]["suite_id"] == "suite_1"
    assert suite_page["items"][0].get("schedule_id") is None

    schedule_page = await queries.list_run_summaries_page(limit=10, triggered_by="schedule")
    assert schedule_page["total"] == 1
    assert schedule_page["items"][0]["run_id"] == "run_schedule"
    assert schedule_page["items"][0]["schedule_id"] == "sched_1"
    assert schedule_page["items"][0].get("suite_id") is None


@pytest.mark.asyncio
async def test_list_run_summaries_page_includes_comparison(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "comparison.db")
    await ensure_schema(db)
    await _seed(
        db,
        [
            _run("run_prev", RunStatus.PASSED),
            _run("run_new_fail", RunStatus.ANOMALY),
        ],
    )
    await db.execute(
        """
        INSERT OR REPLACE INTO run_comparison_cache
            (run_id, baseline_run_id, newly_failed, recovered, still_failing, computed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "run_new_fail",
            "run_prev",
            json.dumps(["로그인"], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            datetime.now(UTC).isoformat(),
        ),
    )
    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )
    page = await queries.list_run_summaries_page(
        limit=10, run_statuses=frozenset({RunStatus.ANOMALY})
    )
    assert page["total"] == 1
    item = page["items"][0]
    assert item["run_id"] == "run_new_fail"
    assert item["comparison"]["badges"] == ["new_failure"]
    assert item["comparison"]["newly_failed"] == ["로그인"]


@pytest.mark.asyncio
async def test_daily_status_counts_uses_kst_day_key(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "tz.db")
    await ensure_schema(db)
    # UTC 2026-07-13 20:00 = KST 2026-07-14 05:00
    kst_next_day = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)
    utc_same_day = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    await _seed(
        db,
        [
            _run("run_kst_14", RunStatus.PASSED, requested_at=kst_next_day),
            _run("run_kst_13", RunStatus.ANOMALY, requested_at=utc_same_day),
        ],
        preserve_time=True,
    )
    query = SqliteRunSummaryQuery(db)
    raw = await query.daily_status_counts(RunSummaryFilter(), tz=KST)
    by_day: dict[str, dict[str, int]] = {}
    for day, status, count in raw:
        by_day.setdefault(day, {})[status] = count
    assert by_day["2026-07-14"]["PASSED"] == 1
    assert by_day["2026-07-13"]["ANOMALY"] == 1


@pytest.mark.asyncio
async def test_get_admin_run_history_board_system_map_counts_this_month(tmp_path: Path) -> None:
    from app.contexts.insights.application.admin_performance import performance_periods

    db = SqliteDatabase(tmp_path / "board.db")
    await ensure_schema(db)
    month_start = performance_periods(datetime.now(UTC))[0].astimezone(UTC)
    inside = month_start + timedelta(minutes=1)
    await _seed(
        db,
        [
            _run("run_ok", RunStatus.PASSED, requested_at=inside),
            *[_run(f"run_bad_{i}", RunStatus.ANOMALY, requested_at=inside) for i in range(6)],
            _run("run_err", RunStatus.ERROR, requested_at=inside),
            _run("run_prev", RunStatus.PASSED, requested_at=month_start - timedelta(minutes=1)),
        ],
        preserve_time=True,
    )

    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )
    board = await queries.get_admin_run_history_board()
    assert "kpis" not in board
    assert board["system_map"]["systems"] == [
        {"system_code": "hom", "system_name": "HOM", "runs": 7, "anomaly": 6}
    ]
    assert board["system_map"]["top_anomaly"] == "hom"


async def _seed_history_only(db: SqliteDatabase, runs: list[Run]) -> None:
    for index, run in enumerate(runs):
        run = run.model_copy(update={"requested_at": datetime.now(UTC) - timedelta(minutes=index)})
        sql, params = _run_history_upsert(run.run_id, run_summary_fields(run))
        await db.execute(sql, params)


@pytest.mark.asyncio
async def test_list_run_summaries_page_run_id_prefix(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "runid.db")
    await ensure_schema(db)
    await _seed(
        db,
        [
            _run("hom_alpha_1", RunStatus.PASSED),
            _run("hom_beta_1", RunStatus.PASSED),
            _run("mhm_alpha_1", RunStatus.PASSED),
        ],
    )
    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=SqliteRunWriteRepository(db),
        log_store=InMemoryRunLogStore(),
    )
    page = await queries.list_run_summaries_page(limit=10, run_id_query="hom_alpha")
    assert page["total"] == 1
    assert page["items"][0]["run_id"] == "hom_alpha_1"


@pytest.mark.asyncio
async def test_counts_by_system_status_groups_by_code_with_latest_name(tmp_path: Path) -> None:
    from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES

    db = SqliteDatabase(tmp_path / "by_system.db")
    await ensure_schema(db)
    since = datetime(2026, 10, 1, tzinfo=UTC)

    def at(run: Run, day: int, name: str = "HOM", code: str = "hom") -> Run:
        return run.model_copy(
            update={
                "requested_at": datetime(2026, 10, day, tzinfo=UTC),
                "system_name": name,
                "system_code": code,
            }
        )

    await _seed(
        db,
        [
            at(_run("r1", RunStatus.PASSED), 2, name="구 홈"),
            at(_run("r2", RunStatus.PASSED), 5, name="대표홈페이지"),
            at(_run("r3", RunStatus.ANOMALY), 3, name="구 홈"),
            at(_run("r4", RunStatus.PASSED), 4, name="모바일홈", code="mhm"),
            at(_run("r5", RunStatus.ERROR), 6, name="대표홈페이지"),
            _run("r6", RunStatus.PASSED).model_copy(
                update={"requested_at": datetime(2026, 9, 30, tzinfo=UTC)}
            ),
        ],
        preserve_time=True,
    )

    rows = await SqliteRunSummaryQuery(db).counts_by_system_status(
        RunSummaryFilter(statuses=ADMIN_VISIBLE_RUN_STATUSES, requested_since=since)
    )
    assert rows == [
        ("hom", "대표홈페이지", "ANOMALY", 1),
        ("hom", "대표홈페이지", "PASSED", 2),
        ("mhm", "모바일홈", "PASSED", 1),
    ]
