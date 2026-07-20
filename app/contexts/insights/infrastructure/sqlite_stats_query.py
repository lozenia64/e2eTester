"""``stats_rollup`` / run·module 이력 인덱스 통계 읽기 어댑터(blob 미접근)."""

from __future__ import annotations

from datetime import datetime

from app.contexts.insights.contracts.query_rows import StatsRollupRow
from app.contexts.run.contracts.query_rows import ModuleHistoryRow, RunSummaryRow
from app.contexts.run.infrastructure.sqlite_module_history_query import (
    _SELECT_COLUMNS as _MODULE_COLUMNS,
)
from app.contexts.run.infrastructure.sqlite_module_history_query import _row_to_history
from app.contexts.run.infrastructure.sqlite_run_summary_query import _SELECT_COLUMNS as _RUN_COLUMNS
from app.contexts.run.infrastructure.sqlite_run_summary_query import _row_to_summary
from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES
from app.platform.eventing.support import SqliteDatabase


class SqliteStatsQuery:
    """``StatsQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def rollup_between(
        self,
        from_day: str | None,
        to_day: str | None,
        *,
        system_codes: list[str] | None = None,
    ) -> list[StatsRollupRow]:
        clauses = ["1=1"]
        params: list[object] = []
        if from_day is not None:
            clauses.append("day_key >= ?")
            params.append(from_day)
        if to_day is not None:
            clauses.append("day_key <= ?")
            params.append(to_day)
        if system_codes is not None:
            if not system_codes:
                return []
            placeholders = ",".join("?" for _ in system_codes)
            clauses.append(f"system_code IN ({placeholders})")
            params.extend(system_codes)
        where = " AND ".join(clauses)
        rows = await self._db.fetchall(
            f"""
            SELECT day_key, system_code, passed_count, anomaly_count,
                   error_count, cancelled_count
            FROM stats_rollup
            WHERE {where}
            ORDER BY day_key DESC, system_code
            """,
            tuple(params),
        )
        return [
            StatsRollupRow(
                day_key=row["day_key"],
                system_code=row["system_code"],
                passed_count=row["passed_count"],
                anomaly_count=row["anomaly_count"],
                error_count=row["error_count"],
                cancelled_count=row["cancelled_count"],
            )
            for row in rows
        ]

    @staticmethod
    def _period_where(from_dt: datetime | None, to_dt: datetime | None) -> tuple[str, list]:
        clauses = [f"status IN ({','.join('?' for _ in ADMIN_VISIBLE_RUN_STATUSES)})"]
        params: list[object] = [status.value for status in ADMIN_VISIBLE_RUN_STATUSES]
        if from_dt is not None:
            clauses.append("requested_at >= ?")
            params.append(from_dt.isoformat())
        if to_dt is not None:
            clauses.append("requested_at <= ?")
            params.append(to_dt.isoformat())
        return " AND ".join(clauses), params

    async def list_usage_run_rows(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[RunSummaryRow]:
        where, params = self._period_where(from_dt, to_dt)
        rows = await self._db.fetchall(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM run_history_index
            WHERE {where}
            ORDER BY requested_at DESC
            """,
            tuple(params),
        )
        return [_row_to_summary(row) for row in rows]

    async def list_usage_module_rows(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[ModuleHistoryRow]:
        # 모듈 이력 행은 종료된 모듈만 존재한다 — 통과/실패/소요 집계에 충분하며,
        # Run 상태 필터는 run_history_index 조인으로 동일 기준을 적용한다.
        clauses = [
            "m.requested_at IS NOT NULL",
            f"r.status IN ({','.join('?' for _ in ADMIN_VISIBLE_RUN_STATUSES)})",
        ]
        params: list[object] = [status.value for status in ADMIN_VISIBLE_RUN_STATUSES]
        if from_dt is not None:
            clauses.append("m.requested_at >= ?")
            params.append(from_dt.isoformat())
        if to_dt is not None:
            clauses.append("m.requested_at <= ?")
            params.append(to_dt.isoformat())
        where = " AND ".join(clauses)
        columns = ", ".join(f"m.{col.strip()}" for col in _MODULE_COLUMNS.split(","))
        rows = await self._db.fetchall(
            f"""
            SELECT {columns}
            FROM module_history_index m
            JOIN run_history_index r ON r.run_id = m.run_id
            WHERE {where}
            """,
            tuple(params),
        )
        return [_row_to_history(row) for row in rows]
