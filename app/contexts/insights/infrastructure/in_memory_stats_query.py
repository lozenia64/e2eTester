"""In-memory ``StatsQueryPort`` for unit tests — 저장된 Run 에서 행을 도출한다."""

from __future__ import annotations

from datetime import datetime

from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES
from app.storage.in_memory_run_summary_query import _row_from_run
from app.storage.query_rows import ModuleHistoryRow, RunSummaryRow, StatsRollupRow


class InMemoryStatsQuery:
    def __init__(self, run_repo) -> None:
        self._run_repo = run_repo

    async def rollup_between(
        self,
        from_day: str | None,
        to_day: str | None,
        *,
        system_codes: list[str] | None = None,
    ) -> list[StatsRollupRow]:
        del from_day, to_day, system_codes
        return []

    async def _usage_runs(self, from_dt: datetime | None, to_dt: datetime | None):
        runs = [
            run
            for run in await self._run_repo.list_all_runs()
            if run.status in ADMIN_VISIBLE_RUN_STATUSES
        ]
        if from_dt is not None:
            runs = [r for r in runs if r.requested_at >= from_dt]
        if to_dt is not None:
            runs = [r for r in runs if r.requested_at <= to_dt]
        return runs

    async def list_usage_run_rows(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[RunSummaryRow]:
        return [_row_from_run(run) for run in await self._usage_runs(from_dt, to_dt)]

    async def list_usage_module_rows(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[ModuleHistoryRow]:
        rows: list[ModuleHistoryRow] = []
        for run in await self._usage_runs(from_dt, to_dt):
            for module in run.modules:
                rows.append(
                    ModuleHistoryRow(
                        run_id=run.run_id,
                        module_id=module.module_id,
                        system_code=run.system_code,
                        module_name=module.name,
                        status=module.status,
                        message=module.message,
                        started_at=module.started_at,
                        ended_at=module.ended_at,
                        duration_ms=module.duration_ms,
                        current_url=module.current_url,
                        artifacts=tuple(module.artifacts),
                        ai_category=module.failure_analysis.category
                        if module.failure_analysis
                        else None,
                        ai_summary=module.failure_analysis.user_summary
                        if module.failure_analysis
                        else None,
                        ai_action=module.failure_analysis.recommended_action
                        if module.failure_analysis
                        else None,
                        suite_id=run.suite_id,
                        schedule_id=run.schedule_id,
                        triggered_by=run.triggered_by,
                        requested_at=run.requested_at,
                        created_by_user_id=run.created_by_user_id,
                        created_by_user_name=run.created_by_user_name,
                    )
                )
        return rows
