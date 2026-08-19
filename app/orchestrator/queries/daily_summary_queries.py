"""KPI 요약 질의 핸들러 — 일간·치유·사용량을 조립한다(읽기 전용).

DailyDashboardQueries 에 합치지 않는 이유: 일간 쿼리가 3방향 fan-out 을 하게 되어
매트릭스·패널 등 KPI 와 무관한 경로까지 치유·통계 스토어에 의존하게 된다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.contexts.insights.application.daily_summary import build_daily_summary
from app.contexts.scheduling.scheduler import schedule_month_start_utc, schedule_today_label

if TYPE_CHECKING:
    from app.contexts.healing.service import HealingService
    from app.contexts.insights.application.stats_service import StatsService
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries


class DailySummaryQueries:
    def __init__(
        self,
        daily_queries: DailyDashboardQueries,
        healing_service: HealingService,
        stats_service: StatsService,
    ) -> None:
        self._daily_queries = daily_queries
        self._healing = healing_service
        self._stats = stats_service

    async def get_daily_summary(
        self,
        *,
        user_id: str | None,
        allowed_system_codes: list[str] | None,
    ) -> dict[str, Any]:
        dashboard = await self._daily_queries.get_daily_dashboard(
            allowed_system_codes=allowed_system_codes
        )
        healing_metrics = await self._healing.metrics(allowed_system_codes=allowed_system_codes)
        savings = await self._stats.get_savings_summary(
            from_dt=schedule_month_start_utc(),
            to_dt=datetime.now(UTC),
            user_id=user_id,
        )
        summary = build_daily_summary(
            dashboard["totals"],
            healing_metrics,
            savings,
            today_label=schedule_today_label(),
        )
        # 프래그먼트가 히어로 문장·메타에 쓰는 원본도 함께 넘긴다.
        summary["totals"] = dashboard["totals"]
        summary["date_label"] = dashboard["date_label"]
        summary["generated_at"] = dashboard["generated_at"]
        summary["attention"] = dashboard["attention"]
        return summary
