"""Run 읽기 전용 질의 핸들러 — 프로젝션 단일 SELECT 소비.

과거 ``RunService.list_run_summaries`` 는 전 상태 Run blob 을 메모리에 올려 파이썬으로
필터·정렬·페이지했다. 이 핸들러는 ``RunSummaryQueryPort``(``run_history_index``)만 소비해
같은 화면 계약(요약 dict 목록)을 만든다 — 필터·정렬·페이지는 SQL 이 수행한다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.contexts.insights.application.admin_performance import performance_periods
from app.contexts.insights.application.admin_run_history_board import (
    build_admin_run_history_board,
    build_system_map,
)
from app.contexts.insights.application.admin_run_history_heatmap import (
    HeatmapRunRow,
    build_user_system_heatmap,
)
from app.contexts.run.contracts.query_rows import Page, RunSummaryFilter, RunSummaryRow
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.views.comparison import attach_comparison
from app.contexts.run.views.summary import summarize_row
from app.contexts.scheduling.scheduler import schedule_today_start_utc
from app.core.enums import RunStatus
from app.core.settings import get_settings
from app.core.status_labels import ADMIN_DASHBOARD_RUN_STATUSES, ADMIN_VISIBLE_RUN_STATUSES

if TYPE_CHECKING:
    from datetime import datetime

    from app.contexts.run.contracts.ports import (
        RunLogStorePort,
        RunSummaryQueryPort,
        RunWriteRepositoryPort,
    )
    from app.contexts.run.views.actor import ActorContext
    from app.core.run_models import Run

ACTIVE_RUN_STATUSES = frozenset({RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT})

# "전체 스캔" 성격의 보드/캘린더 프리페치 상한 — 예약 태깅 Run 은 보존 정책상 이보다
# 훨씬 적게 유지되지만, 무제한 SELECT 는 계약상 두지 않는다.
_SCHEDULE_TAGGED_FETCH_LIMIT = 5000


def _schedule_tz() -> ZoneInfo:
    name = (get_settings().schedule_tz or "").strip() or "Asia/Seoul"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _resolve_statuses(
    run_status: RunStatus | None,
    run_statuses: frozenset[RunStatus] | None,
) -> frozenset[RunStatus] | None:
    statuses = run_statuses
    if run_status is not None:
        statuses = frozenset({run_status}) if statuses is None else statuses & {run_status}
    return statuses


def _build_filter(
    *,
    system_code: str | None = None,
    system_codes: frozenset[str] | None = None,
    user_id: str | None = None,
    user_name_query: str | None = None,
    statuses: frozenset[RunStatus] | None = None,
    requested_since: datetime | None = None,
    requested_before: datetime | None = None,
    triggered_by: str | None = None,
    run_id_query: str | None = None,
) -> RunSummaryFilter:
    return RunSummaryFilter(
        system_code=system_code,
        system_codes=system_codes,
        statuses=statuses,
        user_id=user_id,
        user_name_query=user_name_query,
        requested_since=requested_since,
        requested_before=requested_before,
        triggered_by=triggered_by,
        run_id_query=run_id_query,
    )


def _intersect(statuses: frozenset[RunStatus] | None, other: frozenset[RunStatus]):
    return other if statuses is None else statuses & other


def _subtract(statuses: frozenset[RunStatus] | None, other: frozenset[RunStatus]):
    base = frozenset(RunStatus) if statuses is None else statuses
    return base - other


class RunQueries:
    """Run 목록/상세 질의 핸들러(읽기 전용)."""

    def __init__(
        self,
        summary_query: RunSummaryQueryPort,
        write_repo: RunWriteRepositoryPort,
        log_store: RunLogStorePort,
    ) -> None:
        self._summary = summary_query
        self._write_repo = write_repo
        self._log_store = log_store

    async def get_run_detail(self, run_id: str) -> Run:
        """단건 상세 — 애그리거트 스냅샷 + 로그 하이드레이션(합법적 단일 로드 경로)."""
        run = await self._write_repo.get_run(run_id)
        logs_by_module = await self._log_store.get_all(run_id)
        RunAggregate(run).hydrate_logs(logs_by_module)
        return run

    async def list_run_summaries(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
        system_code: str | None = None,
        user_name_query: str | None = None,
        actor_context: ActorContext | None = None,
        run_status: RunStatus | None = None,
        run_statuses: frozenset[RunStatus] | None = None,
        scope: Literal["today", "before_today"] | None = None,
    ) -> list[dict]:
        statuses = run_statuses
        if run_status is not None:
            statuses = frozenset({run_status}) if statuses is None else statuses & {run_status}
        base = RunSummaryFilter(
            system_code=system_code,
            statuses=statuses,
            user_id=user_id,
            user_name_query=user_name_query,
        )
        rows = await self._rows_for_scope(base, statuses, scope, limit)
        return [summarize_row(row, actor_context=actor_context) for row in rows]

    async def list_run_summaries_page(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
        system_code: str | None = None,
        system_codes: frozenset[str] | None = None,
        user_name_query: str | None = None,
        actor_context: ActorContext | None = None,
        run_status: RunStatus | None = None,
        run_statuses: frozenset[RunStatus] | None = None,
        requested_since: datetime | None = None,
        requested_before: datetime | None = None,
        triggered_by: str | None = None,
        run_id_query: str | None = None,
    ) -> dict[str, Any]:
        statuses = _resolve_statuses(run_status, run_statuses)
        filt = _build_filter(
            system_code=system_code,
            system_codes=system_codes,
            user_id=user_id,
            user_name_query=user_name_query,
            statuses=statuses,
            requested_since=requested_since,
            requested_before=requested_before,
            triggered_by=triggered_by,
            run_id_query=run_id_query,
        )
        rows = await self._summary.list_summaries(filt, Page(limit=limit, offset=offset))
        total = await self._summary.count(filt)
        comparisons = await self._summary.list_comparisons([row.run_id for row in rows])
        items = [
            attach_comparison(
                summarize_row(row, actor_context=actor_context),
                comparisons.get(row.run_id),
            )
            for row in rows
        ]
        return {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    async def get_admin_run_history_heatmap(
        self,
        *,
        systems: list[tuple[str, str]],
    ) -> dict[str, Any]:
        tz = _schedule_tz()
        now = datetime.now(UTC)
        terminal = frozenset(ADMIN_DASHBOARD_RUN_STATUSES)
        trend_local_start = now.astimezone(tz).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=6)
        trend_since = trend_local_start.astimezone(UTC)
        rows = await self._summary.list_summaries(
            RunSummaryFilter(statuses=terminal, requested_since=trend_since),
            Page(limit=3000),
        )
        heatmap_rows = [
            HeatmapRunRow(
                system_code=row.system_code,
                system_name=row.system_name,
                status=row.status,
                requested_at=row.requested_at,
                created_by_user_id=row.created_by_user_id,
                created_by_user_name=row.created_by_user_name,
            )
            for row in rows
        ]
        payload = build_user_system_heatmap(heatmap_rows, systems)
        payload["generated_at"] = now.isoformat()
        payload["timezone"] = str(tz)
        return payload

    async def get_admin_run_history_board(
        self,
        *,
        actor_context: ActorContext | None = None,
    ) -> dict[str, Any]:
        """이번 달 시스템 지도 보드. ``actor_context`` 는 라우트 호환용으로만 받는다."""
        del actor_context
        tz = _schedule_tz()
        now = datetime.now(UTC)
        # SQLite 는 ISO 문자열 비교라 KST 월초를 UTC 로 맞춰야 경계가 어긋나지 않는다.
        period_from = performance_periods(now)[0].astimezone(UTC)
        counts = await self._summary.counts_by_system_status(
            RunSummaryFilter(
                statuses=ADMIN_VISIBLE_RUN_STATUSES,
                requested_since=period_from,
                requested_before=now,
            )
        )
        return build_admin_run_history_board(
            now=now,
            tz=tz,
            today_start=schedule_today_start_utc(),
            system_map=build_system_map(counts, period_from=period_from, period_to=now),
        )

    async def _rows_for_scope(
        self,
        base: RunSummaryFilter,
        statuses: frozenset[RunStatus] | None,
        scope: Literal["today", "before_today"] | None,
        limit: int,
    ) -> list[RunSummaryRow]:
        if scope == "today":
            # 진행 중 Run 은 날짜와 무관하게 먼저, 남는 자리를 오늘 종료된 Run 으로 채운다.
            today_start = schedule_today_start_utc()
            active_statuses = _intersect(statuses, ACTIVE_RUN_STATUSES)
            active_rows: list[RunSummaryRow] = []
            if active_statuses:
                active_rows = await self._summary.list_summaries(
                    replace(base, statuses=active_statuses), Page(limit=limit)
                )
            remaining = max(0, limit - len(active_rows))
            finished_rows: list[RunSummaryRow] = []
            finished_statuses = _subtract(statuses, ACTIVE_RUN_STATUSES)
            if remaining and finished_statuses:
                finished_rows = await self._summary.list_summaries(
                    replace(
                        base,
                        statuses=finished_statuses,
                        requested_since=today_start,
                    ),
                    Page(limit=remaining),
                )
            return active_rows + finished_rows

        if scope == "before_today":
            finished_statuses = _subtract(statuses, ACTIVE_RUN_STATUSES)
            if not finished_statuses:
                return []
            return await self._summary.list_summaries(
                replace(
                    base,
                    statuses=finished_statuses,
                    requested_before=schedule_today_start_utc(),
                ),
                Page(limit=limit),
            )

        return await self._summary.list_summaries(base, Page(limit=limit))

    # --- 예약 관리 센터용 이력 질의 -----------------------------------------

    async def list_schedule_runs(self, schedule_id: str, limit: int = 30) -> list[RunSummaryRow]:
        return await self._summary.list_summaries(
            RunSummaryFilter(schedule_id=schedule_id), Page(limit=limit)
        )

    async def list_schedule_tagged_runs(self) -> list[RunSummaryRow]:
        return await self._summary.list_summaries(
            RunSummaryFilter(schedule_tagged_only=True),
            Page(limit=_SCHEDULE_TAGGED_FETCH_LIMIT),
        )

    async def last_finished_at_by_system(self) -> dict[str, datetime]:
        return await self._summary.last_finished_at_by_system()
