"""healing 지표의 '오늘'이 일간 대시보드의 '오늘'과 같은 날인지 검증.

build_healing_metrics 는 UTC 로 버킷을 만들고, 일간 대시보드는 스케줄 타임존
(기본 Asia/Seoul)으로 날짜를 정한다. KST 00:00~09:00 구간에는 UTC 가 아직 전날이라
자동 복구 건수가 어긋난다 — 사람들이 실제로 대시보드를 보는 아침 시간대다.
"""

from datetime import UTC, datetime

from app.contexts.healing.metrics import build_healing_metrics
from app.contexts.healing.models import HealingAction, HealingEvent
from app.core.schedule_time import schedule_day_label

# KST 2026-08-19 08:00 == UTC 2026-08-18 23:00
KST_MORNING_UTC = datetime(2026, 8, 18, 23, 0, tzinfo=UTC)


def _event(created_at: datetime, event_id: str = "e1") -> HealingEvent:
    return HealingEvent(
        event_id=event_id,
        run_id="run-1",
        module_id="login",
        system_code="HOM",
        broken_selector="#old",
        healed_selector="#new",
        action=HealingAction.AUTO_HEALED,
        retry_succeeded=True,
        created_at=created_at,
    )


def test_utc_default_buckets_by_utc_date():
    """기본 동작(기존 호출자)은 UTC 로 유지된다."""
    metrics = build_healing_metrics(
        [_event(KST_MORNING_UTC)], [], now=KST_MORNING_UTC, trend_days=3
    )
    days = [row["date"] for row in metrics["trend"]]
    assert "2026-08-18" in days


def test_schedule_timezone_buckets_by_kst_date():
    """day_label 을 넘기면 KST 기준 오늘(08-19)에 집계된다."""
    metrics = build_healing_metrics(
        [_event(KST_MORNING_UTC)],
        [],
        now=KST_MORNING_UTC,
        trend_days=3,
        day_label=schedule_day_label,
    )
    today = {row["date"]: row for row in metrics["trend"]}
    assert "2026-08-19" in today, list(today)
    assert today["2026-08-19"]["auto"] == 1


def test_kst_today_bucket_matches_dashboard_date_label():
    """healing 의 오늘 == 일간 대시보드의 date_label."""
    dashboard_today = schedule_day_label(KST_MORNING_UTC)
    metrics = build_healing_metrics(
        [_event(KST_MORNING_UTC)],
        [],
        now=KST_MORNING_UTC,
        trend_days=3,
        day_label=schedule_day_label,
    )
    bucket = next(row for row in metrics["trend"] if row["date"] == dashboard_today)
    assert bucket["auto"] == 1


# KST 2026-09-01 08:30 == UTC 2026-08-31 23:30 — UTC 로는 아직 8월, KST 로는 이미 9월.
KST_MONTH_BOUNDARY_UTC = datetime(2026, 8, 31, 23, 30, tzinfo=UTC)
# KST 2026-09-01 00:00 == UTC 2026-08-31 15:00 — savings 카드가 쓰는
# schedule_month_start_utc() 와 같은 정의의 '이번 달(9월, KST)' 시작점을 고정 시각으로 재현한다.
KST_SEPTEMBER_START_UTC = datetime(2026, 8, 31, 15, 0, tzinfo=UTC)


def test_month_kpi_uses_utc_by_default():
    """month_start 를 생략하면(기존 호출자) UTC 월 경계를 그대로 쓴다 — 하위 호환."""
    events = [
        _event(KST_MONTH_BOUNDARY_UTC, event_id="e-boundary"),
        # UTC 로는 같은 8월이지만, KST 로는 지난달(8월) 안에 머무는 시각.
        _event(datetime(2026, 8, 15, 12, 0, tzinfo=UTC), event_id="e-mid-august"),
    ]
    metrics = build_healing_metrics(events, [], now=KST_MONTH_BOUNDARY_UTC)
    # UTC 월 시작(8/1 00:00)을 쓰므로 두 이벤트 모두 '이번 달'(UTC 8월)로 뭉뚱그려진다.
    assert metrics["kpi"]["month_events"] == 2
    assert metrics["kpi"]["month_auto_recovered"] == 2


def test_month_kpi_uses_schedule_timezone_when_month_start_provided():
    """month_start 를 스케줄 타임존(KST) 기준으로 넘기면 KST 월 경계로 정확히 나뉜다.

    savings 카드(``StatsService.get_savings_summary`` → ``schedule_month_start_utc()``)와
    같은 '이번 달' 정의를 healing 의 ``month_auto_recovered`` 도 따라야, 같은 화면의
    두 카드가 KST 아침 시간대에 서로 다른 달을 가리키는 불일치가 사라진다.
    """
    events = [
        _event(KST_MONTH_BOUNDARY_UTC, event_id="e-boundary"),
        _event(datetime(2026, 8, 15, 12, 0, tzinfo=UTC), event_id="e-mid-august"),
    ]
    metrics = build_healing_metrics(
        events, [], now=KST_MONTH_BOUNDARY_UTC, month_start=KST_SEPTEMBER_START_UTC
    )
    # KST 월 시작(9/1 00:00 KST)을 쓰므로, 8/15 이벤트는 '지난 달(8월, KST)'로 빠지고
    # 경계 시각의 이벤트만 '이번 달(9월, KST)'로 집계된다.
    assert metrics["kpi"]["month_events"] == 1
    assert metrics["kpi"]["month_auto_recovered"] == 1
