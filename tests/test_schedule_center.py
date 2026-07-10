"""예약 점검 관리 센터 순수 빌더 단위 테스트 — 브라우저/DB 없이 규칙만 검증한다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.scheduling.schedule_center import (
    ExecutionPoint,
    build_coverage,
    build_history_stats,
    classify_issues,
    cluster_warnings,
    count_today_planned,
    cron_to_label,
    expand_occurrences,
    match_occurrences,
)

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _point(
    execution_id: str = "run_1",
    status: str = "PASSED",
    requested_at: datetime = NOW,
    duration_seconds: int | None = 60,
    kind: str = "run",
) -> ExecutionPoint:
    started = requested_at
    ended = requested_at + timedelta(seconds=duration_seconds) if duration_seconds else None
    return ExecutionPoint(
        execution_id=execution_id,
        kind=kind,
        status=status,
        requested_at=requested_at,
        started_at=started,
        ended_at=ended,
    )


# --------------------------------------------------------------------------- #
# cron 한글 라벨
# --------------------------------------------------------------------------- #
def test_cron_to_label_common_patterns():
    assert cron_to_label("0 9 * * *") == "매일 09:00"
    assert cron_to_label("30 14 * * 1-5") == "평일 14:30"
    assert cron_to_label("0 9 * * 1,3,5") == "매주 월·수·금 09:00"
    assert cron_to_label("0 9 15 * *") == "매월 15일 09:00"
    assert cron_to_label("*/15 * * * *") == "15분마다"
    assert cron_to_label("0 */2 * * *") == "2시간마다"


def test_cron_to_label_falls_back_to_raw():
    assert cron_to_label("0 9 * 3 *") == "0 9 * 3 *"  # 월 제한은 미지원 → 원문
    assert cron_to_label("broken") == "broken"


# --------------------------------------------------------------------------- #
# cron 전개 + 계획 vs 실적 매칭
# --------------------------------------------------------------------------- #
def test_expand_occurrences_within_window():
    start = datetime(2026, 7, 6, 0, 0, tzinfo=UTC)  # 월요일
    end = start + timedelta(days=7)
    occurrences = expand_occurrences("0 9 * * 1-5", start, end)
    assert len(occurrences) == 5  # 평일 5회
    assert all(occ.hour == 9 for occ in occurrences)


def test_expand_occurrences_respects_cap():
    start = datetime(2026, 7, 6, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=7)
    occurrences = expand_occurrences("* * * * *", start, end, cap=50)
    assert len(occurrences) == 50


def test_match_occurrences_planned_matched_missed():
    occ_past_hit = NOW - timedelta(hours=3)
    occ_past_miss = NOW - timedelta(hours=2)
    occ_future = NOW + timedelta(hours=1)
    execution = _point("run_hit", "PASSED", occ_past_hit + timedelta(minutes=1))
    blocks = match_occurrences([occ_past_hit, occ_past_miss, occ_future], [execution], NOW)
    states = {block["at"]: block["state"] for block in blocks}
    assert states[occ_past_hit] == "PASSED"
    assert states[occ_past_miss] == "missed"
    assert states[occ_future] == "planned"


def test_match_occurrences_flags_unplanned_manual_run():
    execution = _point("run_manual", "ERROR", NOW - timedelta(minutes=90))
    blocks = match_occurrences([], [execution], NOW)
    assert len(blocks) == 1
    assert blocks[0]["state"] == "ERROR"
    assert blocks[0]["unplanned"] is True


def test_match_occurrences_active_execution_state():
    occ = NOW - timedelta(minutes=5)
    execution = _point("run_live", "RUNNING", occ + timedelta(seconds=30), duration_seconds=None)
    blocks = match_occurrences([occ], [execution], NOW)
    assert blocks[0]["state"] == "active"
    assert blocks[0]["link"] == "/runs/run_live"


def test_cluster_warnings_only_over_threshold():
    slot = datetime(2026, 7, 6, 9, 0, tzinfo=UTC)  # 월요일 09시
    pairs = [(f"sch_{i}", slot + timedelta(minutes=i)) for i in range(3)]
    pairs.append(("sch_other", slot + timedelta(hours=5)))
    warnings = cluster_warnings(pairs)
    assert len(warnings) == 1
    assert warnings[0]["schedule_count"] == 3
    assert warnings[0]["hour"] == 9


def test_build_coverage_marks_gaps():
    coverage = build_coverage(
        [("hom", "대표홈페이지(PC)"), ("mhm", "대표홈페이지(모바일)")],
        {"hom": NOW - timedelta(hours=2)},
        NOW,
    )
    by_code = {entry["system_code"]: entry for entry in coverage}
    assert by_code["hom"]["covered"] is True
    assert by_code["mhm"]["covered"] is False
    assert by_code["mhm"]["last_checked_at"] is None


# --------------------------------------------------------------------------- #
# 관제 보드 분류
# --------------------------------------------------------------------------- #
def _classify(**overrides):
    params = dict(
        enabled=True,
        paused_until=None,
        last_status=None,
        last_skipped_at=None,
        disabled_at=None,
        created_at=NOW - timedelta(days=30),
        last_run_at=None,
        recent_executions=[],
        now=NOW,
    )
    params.update(overrides)
    return classify_issues(**params)


def test_classify_healthy_schedule_has_no_issues():
    issues = _classify(
        last_status="PASSED",
        recent_executions=[_point("r1", "PASSED", NOW - timedelta(hours=1))],
    )
    assert issues == []


def test_classify_stuck_on_waiting_input():
    issues = _classify(last_status="WAITING_INPUT")
    assert {"type": "stuck"} in issues


def test_classify_failing_needs_consecutive_failures():
    one_failure = _classify(
        last_status="ERROR",
        recent_executions=[
            _point("r1", "ERROR", NOW - timedelta(hours=1)),
            _point("r2", "PASSED", NOW - timedelta(hours=2)),
        ],
    )
    assert all(issue["type"] != "failing" for issue in one_failure)

    two_failures = _classify(
        last_status="ERROR",
        recent_executions=[
            _point("r1", "ERROR", NOW - timedelta(hours=1)),
            _point("r2", "ANOMALY", NOW - timedelta(hours=2)),
            _point("r3", "PASSED", NOW - timedelta(hours=3)),
        ],
    )
    failing = [issue for issue in two_failures if issue["type"] == "failing"]
    assert failing and failing[0]["consecutive_failures"] == 2


def test_classify_failing_treats_legacy_failed_as_failure():
    issues = _classify(
        recent_executions=[
            _point("r1", "FAILED", NOW - timedelta(hours=1)),
            _point("r2", "FAILED", NOW - timedelta(hours=2)),
        ],
    )
    assert any(issue["type"] == "failing" for issue in issues)


def test_classify_missed_within_window_only():
    recent = _classify(last_skipped_at=NOW - timedelta(hours=3))
    assert any(issue["type"] == "missed" for issue in recent)
    old = _classify(last_skipped_at=NOW - timedelta(days=2))
    assert all(issue["type"] != "missed" for issue in old)


def test_classify_stale_disabled_schedule():
    issues = _classify(enabled=False, disabled_at=NOW - timedelta(days=10))
    stale = [issue for issue in issues if issue["type"] == "stale"]
    assert stale and stale[0]["disabled_days"] == 10

    fresh = _classify(enabled=False, disabled_at=NOW - timedelta(days=2))
    assert all(issue["type"] != "stale" for issue in fresh)


def test_count_today_planned():
    day_start = datetime(2026, 7, 10, 0, 0, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    assert count_today_planned("0 9 * * *", day_start, day_end) == 1
    assert count_today_planned("0 */6 * * *", day_start, day_end) == 4


# --------------------------------------------------------------------------- #
# 실행 이력 통계
# --------------------------------------------------------------------------- #
def test_build_history_stats_rates_and_streak():
    executions = [
        _point("r1", "PASSED", NOW - timedelta(hours=1), duration_seconds=120),
        _point("r2", "PASSED", NOW - timedelta(hours=2), duration_seconds=60),
        _point("r3", "ERROR", NOW - timedelta(hours=3), duration_seconds=30),
        _point("r4", "CANCELLED", NOW - timedelta(hours=4), duration_seconds=None),
    ]
    stats = build_history_stats(executions)
    assert stats["total"] == 4
    assert stats["passed"] == 2
    assert stats["error"] == 1
    assert stats["cancelled"] == 1
    # 취소 제외 3건 중 2건 성공
    assert stats["success_rate"] == 66.7
    assert stats["avg_duration_ms"] == 70000
    assert stats["current_streak"] == 2
    # dots 는 과거→최신 순
    assert [dot["execution_id"] for dot in stats["dots"]] == ["r4", "r3", "r2", "r1"]


def test_build_history_stats_active_run_skips_streak():
    executions = [
        _point("r1", "RUNNING", NOW - timedelta(minutes=5), duration_seconds=None),
        _point("r2", "PASSED", NOW - timedelta(hours=1)),
    ]
    stats = build_history_stats(executions)
    assert stats["active"] == 1
    assert stats["current_streak"] == 1  # 진행 중 건은 건너뛰고 판정
    assert stats["success_rate"] == 100.0


def test_build_history_stats_empty():
    stats = build_history_stats([])
    assert stats["total"] == 0
    assert stats["success_rate"] is None
    assert stats["dots"] == []
