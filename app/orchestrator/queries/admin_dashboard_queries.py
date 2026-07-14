"""관리자 대시보드 질의 핸들러 — 7×3 커버리지 매트릭스."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.contexts.insights.application.admin_coverage_dashboard import (
    CoverageRunRow,
    build_admin_coverage_dashboard,
    coverage_window_start_utc,
)
from app.core.settings import get_settings
from app.storage.query_rows import Page, RunSummaryFilter

if TYPE_CHECKING:
    from app.registry.loader import ModuleRegistry
    from app.storage.ports import RunSummaryQueryPort
    from app.storage.query_rows import RunSummaryRow

_PAGE_SIZE = 500


def _schedule_tz() -> ZoneInfo:
    name = (get_settings().schedule_tz or "").strip() or "Asia/Seoul"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


class AdminDashboardQueries:
    """관리자 관제 대시보드 질의(읽기 전용)."""

    def __init__(
        self,
        registry: ModuleRegistry,
        summary_query: RunSummaryQueryPort,
    ) -> None:
        self._registry = registry
        self._summary_query = summary_query

    async def _list_summaries_since(self, since: datetime) -> list[RunSummaryRow]:
        filt = RunSummaryFilter(requested_since=since)
        rows: list[RunSummaryRow] = []
        offset = 0
        while True:
            page_rows = await self._summary_query.list_summaries(
                filt,
                Page(limit=_PAGE_SIZE, offset=offset),
            )
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(page_rows) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        return rows

    async def get_coverage_dashboard(self) -> dict[str, Any]:
        tz = _schedule_tz()
        now = datetime.now(UTC)
        since = coverage_window_start_utc(now, tz)
        rows = await self._list_summaries_since(since)
        run_rows = [
            CoverageRunRow(
                run_id=row.run_id,
                system_code=row.system_code,
                status=row.status,
                requested_at=row.requested_at,
            )
            for row in rows
        ]
        systems = self._registry.list_systems()
        return build_admin_coverage_dashboard(systems, run_rows, now=now, tz=tz)
