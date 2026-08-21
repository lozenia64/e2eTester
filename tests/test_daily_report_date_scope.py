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

    async def list_for_date(self, date_label, allowed_system_codes):
        self.dates.append(date_label)
        return []

    async def list_run_summaries_for_date(self, date_label, since_utc, allowed_system_codes):
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


@pytest.mark.asyncio
async def test_dashboard_echoes_the_requested_date():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    data = await DailyDashboardQueries(
        _EmptyRegistry(), _RecordingStatusQuery()
    ).get_daily_dashboard(date_label="2026-08-20")
    assert data["date_label"] == "2026-08-20"
