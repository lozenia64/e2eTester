"""일간 리포트 스케줄러 - cron·비활성·대상일 계산.

run_retention.py 와 동형이다. 기본은 꺼져 있어야 한다(설계 D3).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.scheduling.daily_report_scheduler import (
    DEFAULT_DAILY_REPORT_CRON,
    DailyReportScheduler,
)


class _Service:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_for(self, date_label: str) -> bool:
        self.sent.append(date_label)
        return True


def test_from_env_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("E2E_EMAIL_DAILY_REPORT_ENABLED", raising=False)
    from app.core.settings import get_settings

    get_settings.cache_clear()
    assert DailyReportScheduler.from_env(_Service()) is None


def test_from_env_builds_when_enabled(monkeypatch):
    monkeypatch.setenv("E2E_EMAIL_DAILY_REPORT_ENABLED", "true")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    scheduler = DailyReportScheduler.from_env(_Service())
    assert scheduler is not None


def test_default_cron_is_eight_am():
    assert DEFAULT_DAILY_REPORT_CRON == "0 8 * * *"


def test_target_date_is_the_previous_day():
    """리포트는 어제를 보고한다(설계 D1)."""
    scheduler = DailyReportScheduler(report_service=_Service(), cron=DEFAULT_DAILY_REPORT_CRON)
    # KST 2026-08-21 08:00 == UTC 2026-08-20 23:00
    label = scheduler.target_date_label(datetime(2026, 8, 20, 23, 0, tzinfo=UTC))
    assert label == "2026-08-20"


@pytest.mark.asyncio
async def test_tick_sends_for_yesterday_when_cron_matches():
    service = _Service()
    scheduler = DailyReportScheduler(report_service=service, cron="0 8 * * *")
    # KST 2026-08-21 08:00 정각
    await scheduler.tick_at(datetime(2026, 8, 20, 23, 0, tzinfo=UTC))
    assert service.sent == ["2026-08-20"]


@pytest.mark.asyncio
async def test_tick_does_nothing_when_cron_does_not_match():
    service = _Service()
    scheduler = DailyReportScheduler(report_service=service, cron="0 8 * * *")
    # KST 2026-08-21 09:00 - cron 불일치
    await scheduler.tick_at(datetime(2026, 8, 21, 0, 0, tzinfo=UTC))
    assert service.sent == []
