"""In-memory ``StatsQueryPort`` for unit tests."""

from __future__ import annotations

from datetime import datetime

from app.core.models import Run
from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES
from app.storage.query_rows import StatsRollupRow


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

    async def list_usage_runs(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[Run]:
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
