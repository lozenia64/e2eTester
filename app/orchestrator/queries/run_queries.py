"""Run 읽기 전용 질의 핸들러 — 프로젝션 단일 SELECT 소비.

과거 ``RunService.list_run_summaries`` 는 전 상태 Run blob 을 메모리에 올려 파이썬으로
필터·정렬·페이지했다. 이 핸들러는 ``RunSummaryQueryPort``(``run_history_index``)만 소비해
같은 화면 계약(요약 dict 목록)을 만든다 — 필터·정렬·페이지는 SQL 이 수행한다.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from app.core.enums import RunStatus
from app.domain.run_aggregate import RunAggregate
from app.orchestrator.run_summary import summarize_row
from app.scheduling.scheduler import schedule_today_start_utc
from app.storage.query_rows import Page, RunSummaryFilter, RunSummaryRow

if TYPE_CHECKING:
    from datetime import datetime

    from app.core.models import Run
    from app.orchestrator.run_actor import ActorContext
    from app.storage.ports import (
        RunLogStorePort,
        RunSummaryQueryPort,
        RunWriteRepositoryPort,
    )

ACTIVE_RUN_STATUSES = frozenset({RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT})

# "전체 스캔" 성격의 보드/캘린더 프리페치 상한 — 예약 태깅 Run 은 보존 정책상 이보다
# 훨씬 적게 유지되지만, 무제한 SELECT 는 계약상 두지 않는다.
_SCHEDULE_TAGGED_FETCH_LIMIT = 5000


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
