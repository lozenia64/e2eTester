"""일간 리포트 메일 스케줄러 - cron 시각에 어제 리포트를 보낸다.

``run_retention.py`` 의 RunRetentionScheduler 와 동형이다: parse_cron + 틱 루프 +
from_env(설정이 꺼져 있으면 None).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.contexts.scheduling.cron import parse_cron
from app.contexts.scheduling.scheduler import _resolve_timezone
from app.core.logging import get_logger
from app.core.schedule_time import schedule_day_label
from app.core.settings import get_settings

if TYPE_CHECKING:
    from app.notifications.daily_report_email import DailyReportEmailService

logger = get_logger(__name__)

DEFAULT_DAILY_REPORT_CRON = "0 8 * * *"
TICK_SECONDS = 30


class DailyReportScheduler:
    def __init__(
        self,
        *,
        report_service: DailyReportEmailService,
        cron: str = DEFAULT_DAILY_REPORT_CRON,
        tick_seconds: int = TICK_SECONDS,
    ) -> None:
        self._service = report_service
        self._cron_expr = cron
        self._cron = parse_cron(cron)
        self._tick_seconds = tick_seconds
        self._running = False
        _tz, self._timezone_name = _resolve_timezone()

    @classmethod
    def from_env(cls, report_service: DailyReportEmailService) -> DailyReportScheduler | None:
        settings = get_settings()
        if not settings.daily_report_enabled:
            return None
        cron = (settings.daily_report_cron or "").strip() or DEFAULT_DAILY_REPORT_CRON
        parse_cron(cron)
        return cls(report_service=report_service, cron=cron)

    def target_date_label(self, now_utc: datetime) -> str:
        """리포트가 보고할 날짜 - 스케줄 타임존 기준 전날(설계 D1)."""
        return schedule_day_label(now_utc - timedelta(days=1))

    async def tick_at(self, now_utc: datetime) -> None:
        tz, _name = _resolve_timezone()
        now_local = now_utc.astimezone(tz)
        if not self._cron.matches(now_local):
            return
        await self._service.send_for(self.target_date_label(now_utc))

    async def run_forever(self) -> None:
        self._running = True
        logger.info(
            "일간 리포트 스케줄러 시작",
            log_event="daily_report.started",
            timezone=self._timezone_name,
            cron=self._cron_expr,
            tick_seconds=self._tick_seconds,
        )
        while self._running:
            try:
                await self.tick_at(datetime.now(UTC))
            except Exception as exc:
                logger.exception(
                    "일간 리포트 tick 오류",
                    log_event="daily_report.tick_error",
                    error=str(exc),
                )
            try:
                await asyncio.sleep(self._tick_seconds)
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
