"""``stats_rollup`` / ``run_history_index`` 통계 읽기 어댑터."""

from __future__ import annotations

from datetime import datetime

from app.core.models import Run
from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES
from app.eventsourcing.support import SqliteDatabase
from app.storage.query_rows import StatsRollupRow
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


class SqliteStatsQuery:
    """``StatsQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase, write_repo: SqliteRunWriteRepository) -> None:
        self._db = db
        self._write_repo = write_repo

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

    async def list_usage_runs(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[Run]:
        clauses = [f"status IN ({','.join('?' for _ in ADMIN_VISIBLE_RUN_STATUSES)})"]
        params: list[object] = [status.value for status in ADMIN_VISIBLE_RUN_STATUSES]
        if from_dt is not None:
            clauses.append("requested_at >= ?")
            params.append(from_dt.isoformat())
        if to_dt is not None:
            clauses.append("requested_at <= ?")
            params.append(to_dt.isoformat())
        where = " AND ".join(clauses)
        rows = await self._db.fetchall(
            f"""
            SELECT run_id FROM run_history_index
            WHERE {where}
            ORDER BY requested_at DESC
            """,
            tuple(params),
        )
        runs: list[Run] = []
        for row in rows:
            try:
                runs.append(await self._write_repo.get_run(row["run_id"]))
            except KeyError:
                continue
        return runs
