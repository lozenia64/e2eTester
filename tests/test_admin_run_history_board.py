"""admin_run_history_board 순수 빌더 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.contexts.insights.application.admin_run_history_board import (
    BoardRunRow,
    build_admin_run_history_board,
    build_trend_7d,
    merge_daily_status_counts,
)
from app.core.enums import RunStatus

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _row(run_id: str, status: RunStatus) -> BoardRunRow:
    return BoardRunRow(
        run_id=run_id,
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=status,
        requested_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        module_total=3,
        module_passed=2,
        module_skipped=0,
        failed_module_name="로그인" if status != RunStatus.PASSED else None,
        triggered_by="manual",
        suite_id=None,
        schedule_id=None,
        created_by_user_name="테스터",
    )


def test_merge_daily_status_counts_maps_failed_to_anomaly() -> None:
    merged = merge_daily_status_counts([("2026-07-14", "FAILED", 2), ("2026-07-14", "PASSED", 5)])
    assert merged["2026-07-14"]["anomaly"] == 2
    assert merged["2026-07-14"]["passed"] == 5


def test_build_trend_7d_fills_missing_days_with_zero() -> None:
    trend = build_trend_7d({"2026-07-14": {"passed": 3}}, now=NOW, tz=KST)
    assert len(trend) == 7
    assert trend[-1]["day"] == "2026-07-14"
    assert trend[-1]["passed"] == 3
    assert trend[0]["passed"] == 0


def test_build_admin_run_history_board_kpis() -> None:
    board = build_admin_run_history_board(
        now=NOW,
        tz=KST,
        today_start=datetime(2026, 7, 13, 15, 0, tzinfo=UTC),
        total_finished=120,
        today_status_counts={
            RunStatus.PASSED.value: 4,
            RunStatus.ANOMALY.value: 1,
            RunStatus.ERROR.value: 1,
        },
        trend_counts_raw=[],
        attention_rows=[_row("run_a", RunStatus.ANOMALY)],
        by_system_recent_rows=[_row("run_b", RunStatus.PASSED)],
        attention_open_count=9,
    )
    assert board["kpis"]["total_finished"] == 120
    assert board["kpis"]["today_finished"] == 6
    assert board["kpis"]["today_anomaly"] == 1
    assert board["kpis"]["attention_open"] == 9
    assert board["attention_runs"][0]["run_id"] == "run_a"
    assert board["by_system_recent"][0]["system_code"] == "hom"
