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
