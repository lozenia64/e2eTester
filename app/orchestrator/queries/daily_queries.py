"""일간 점검 현황 질의 핸들러 — ``daily_system_status`` 프로젝션 소비.

과거 ``RunService.get_daily_dashboard`` 는 모듈 소요시간을 얻으려고 상태 행마다 Run blob
을 다시 읽었다(``_load_daily_module_durations``). 이제 프로젝션이 ``duration_ms`` 를 직접
들고 있으므로 blob 접근이 없다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.contexts.insights.application.daily_dashboard import build_daily_dashboard_from_projection
from app.contexts.scheduling.scheduler import schedule_today_label, schedule_today_start_utc

if TYPE_CHECKING:
    from app.registry.loader import ModuleRegistry
    from app.storage.ports import DailyStatusQueryPort


class DailyDashboardQueries:
    """일간 점검 현황 대시보드 질의 핸들러(읽기 전용)."""

    def __init__(
        self,
        registry: ModuleRegistry,
        daily_status_query: DailyStatusQueryPort,
    ) -> None:
        self._registry = registry
        self._daily_status_query = daily_status_query

    async def get_daily_dashboard(
        self,
        *,
        allowed_system_codes: list[str] | None = None,
    ) -> dict:
        """접근 가능한 시스템의 KST 오늘 시스템·모듈별 점검 상태 집계(PII 없음)."""
        systems = self._registry.list_systems()
        if allowed_system_codes is not None:
            allowed = set(allowed_system_codes)
            systems = [s for s in systems if s.system_code in allowed]

        today_start_utc = schedule_today_start_utc()
        date_label = schedule_today_label()
        status_rows = await self._daily_status_query.list_for_date(date_label, allowed_system_codes)
        run_summaries = await self._daily_status_query.list_run_summaries_for_date(
            date_label, today_start_utc, allowed_system_codes
        )
        duration_by_module_run = {
            (row.last_run_id, row.module_id): row.duration_ms
            for row in status_rows
            if row.last_run_id
        }
        return build_daily_dashboard_from_projection(
            systems,
            status_rows,
            run_summaries,
            duration_by_module_run=duration_by_module_run,
            generated_at=datetime.now(UTC),
            date_label=date_label,
        )
