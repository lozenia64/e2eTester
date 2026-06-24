from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.env_utils import DEFAULT_ENV_FILE_PATH, env_flag, load_dotenv_file, resolve_env_value
from app.core.status_labels import RUN_DAILY_PURGE_STATUSES
from app.scheduling.cron import parse_cron
from app.scheduling.scheduler import _resolve_timezone

DEFAULT_RETENTION_CRON = "0 3 * * *"
DEFAULT_RETENTION_TICK_SECONDS = 60


@dataclass(frozen=True)
class RunRetentionResult:
    deleted_run_ids: list[str]


class RunRetentionService:
    """점검실패·취소 Run 을 정상·이상징후와 분리해 주기적으로 삭제한다."""

    def __init__(self, run_service) -> None:
        self._run_service = run_service

    async def purge_eligible_runs(self, *, requested_before: datetime) -> RunRetentionResult:
        deleted = await self._run_service.purge_runs(
            statuses=RUN_DAILY_PURGE_STATUSES,
            requested_before=requested_before,
        )
        return RunRetentionResult(deleted_run_ids=deleted)


class RunRetentionScheduler:
    """매일 cron 시각에 당일 00:00(기준 타임존) 이전의 점검실패·취소 Run 을 삭제한다."""

    def __init__(
        self,
        retention_service: RunRetentionService,
        cron: str = DEFAULT_RETENTION_CRON,
        tick_seconds: int = DEFAULT_RETENTION_TICK_SECONDS,
        timezone: ZoneInfo | None = None,
        timezone_name: str | None = None,
    ) -> None:
        self._retention_service = retention_service
        self._cron_expr = cron
        self._cron = parse_cron(cron)
        self._tick_seconds = tick_seconds
        if timezone is not None and timezone_name is not None:
            self._timezone = timezone
            self._timezone_name = timezone_name
        else:
            self._timezone, self._timezone_name = _resolve_timezone()
        self._running = False
        self._last_purge_local_date: datetime.date | None = None

    @classmethod
    def from_env(cls, retention_service: RunRetentionService) -> RunRetentionScheduler | None:
        dotenv_values = load_dotenv_file(DEFAULT_ENV_FILE_PATH)
        if not env_flag("E2E_RUN_RETENTION_ENABLED", dotenv_values, default=True):
            return None
        cron = (resolve_env_value("E2E_RUN_RETENTION_CRON", dotenv_values) or "").strip()
        if not cron:
            cron = DEFAULT_RETENTION_CRON
        parse_cron(cron)
        return cls(retention_service=retention_service, cron=cron)

    async def run_forever(self) -> None:
        self._running = True
        print(
            f"[run-retention] 시작 (tz={self._timezone_name}, cron={self._cron_expr!r}, "
            f"tick={self._tick_seconds}s)"
        )
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                print(f"[run-retention] tick 오류: {exc}")
            try:
                await asyncio.sleep(self._tick_seconds)
            except asyncio.CancelledError:
                break
        print("[run-retention] 종료")

    def stop(self) -> None:
        self._running = False

    async def purge_now(self) -> RunRetentionResult:
        """오늘 자정(기준 타임존) 이전 Run 을 즉시 정리한다."""
        return await self._retention_service.purge_eligible_runs(
            requested_before=self._today_start_utc(),
        )

    async def _tick(self) -> None:
        now_local = datetime.now(self._timezone).replace(second=0, microsecond=0)
        if not self._cron.matches(now_local):
            return
        if self._last_purge_local_date == now_local.date():
            return
        result = await self.purge_now()
        self._last_purge_local_date = now_local.date()
        if result.deleted_run_ids:
            print(
                f"[run-retention] {len(result.deleted_run_ids)}건 삭제 "
                f"(기준: {self._timezone_name} 오늘 00:00 이전, 점검실패·취소)"
            )
        else:
            print("[run-retention] 삭제 대상 없음")

    def _today_start_utc(self) -> datetime:
        now_local = datetime.now(self._timezone)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start_local.astimezone(UTC)
