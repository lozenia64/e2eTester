"""일간 집계의 날짜 파라미터화.

리포트는 어제를 보고해야 하는데(설계 D1) DailyDashboardQueries 가 오늘로
고정돼 있었다. 포트(list_for_date)는 이미 임의 날짜를 받으므로 이 한 곳만 연다.
기본값은 현행 동작이라 일간 현황·상황판은 영향받지 않아야 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.scheduling.scheduler import (
    schedule_day_start_utc,
    schedule_today_label,
    schedule_today_start_utc,
)


def test_day_start_matches_today_helper():
    """schedule_today_start_utc 는 오늘 라벨을 넣은 schedule_day_start_utc 와 같다."""
    assert schedule_day_start_utc(schedule_today_label()) == schedule_today_start_utc()


def test_day_start_is_utc_aware():
    result = schedule_day_start_utc("2026-08-20")
    assert result.tzinfo is not None
    assert result.utcoffset() == UTC.utcoffset(None)


def test_day_start_of_kst_date_is_previous_day_in_utc():
    """KST 2026-08-20 00:00 == UTC 2026-08-19 15:00 (E2E_SCHEDULE_TZ 기본 Asia/Seoul)."""
    result = schedule_day_start_utc("2026-08-20")
    assert result == datetime(2026, 8, 19, 15, 0, tzinfo=UTC)


def test_invalid_label_raises():
    with pytest.raises(ValueError):
        schedule_day_start_utc("2026/08/20")


class _RecordingStatusQuery:
    def __init__(self) -> None:
        self.dates: list[str] = []
        self.since_utcs: list[datetime] = []

    async def list_for_date(self, date_label, allowed_system_codes):
        self.dates.append(date_label)
        return []

    async def list_run_summaries_for_date(self, date_label, since_utc, allowed_system_codes):
        self.since_utcs.append(since_utc)
        return []


class _EmptyRegistry:
    def list_systems(self):
        return []


@pytest.mark.asyncio
async def test_default_queries_today():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    query = _RecordingStatusQuery()
    await DailyDashboardQueries(_EmptyRegistry(), query).get_daily_dashboard()
    assert query.dates == [schedule_today_label()]


@pytest.mark.asyncio
async def test_explicit_date_label_is_used():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    query = _RecordingStatusQuery()
    await DailyDashboardQueries(_EmptyRegistry(), query).get_daily_dashboard(
        date_label="2026-08-20"
    )
    assert query.dates == ["2026-08-20"]
    assert query.since_utcs == [schedule_day_start_utc("2026-08-20")]


@pytest.mark.asyncio
async def test_dashboard_echoes_the_requested_date():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    data = await DailyDashboardQueries(
        _EmptyRegistry(), _RecordingStatusQuery()
    ).get_daily_dashboard(date_label="2026-08-20")
    assert data["date_label"] == "2026-08-20"


_HEALING_FOR_DATE = {
    "kpi": {"month_auto_recovered": 10, "pending_patches": 1},
    "trend": [
        {"date": "2026-08-19", "auto": 3},
        {"date": "2026-08-20", "auto": 5},
    ],
}


class _RecordingDailyQueries:
    def __init__(self) -> None:
        self.date_labels: list[str | None] = []

    async def get_daily_dashboard(self, *, allowed_system_codes=None, date_label=None):
        self.date_labels.append(date_label)
        label = date_label or schedule_today_label()
        return {
            "totals": {
                "modules": 2,
                "passed": 2,
                "pass_rate": 100,
                "anomaly": 0,
                "error": 0,
            },
            "date_label": label,
            "generated_at": datetime.now(UTC),
            "attention": [],
        }


class _StubHealing:
    async def metrics(self, *, allowed_system_codes=None):
        return _HEALING_FOR_DATE


class _StubStats:
    async def get_savings_summary(self, *, from_dt, to_dt, user_id):
        from app.core.stats_models import SavingsSummary

        return SavingsSummary(
            total_seconds=0,
            my_seconds=0,
            run_count=0,
            module_count=0,
            basis_updated_at=datetime.now(UTC),
            estimated=False,
            note="",
        )


@pytest.mark.asyncio
async def test_summary_forwards_date_label_and_builds_for_requested_day():
    from app.orchestrator.queries.daily_summary_queries import DailySummaryQueries

    daily = _RecordingDailyQueries()
    result = await DailySummaryQueries(
        daily, _StubHealing(), _StubStats()
    ).get_daily_summary(
        user_id=None,
        allowed_system_codes=None,
        date_label="2026-08-20",
    )
    assert daily.date_labels == ["2026-08-20"]
    assert result["date_label"] == "2026-08-20"
    self_healed = next(card for card in result["cards"] if card["key"] == "self_healed")
    assert self_healed["value"] == 5
