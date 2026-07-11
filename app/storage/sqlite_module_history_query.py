"""``ModuleHistoryQueryPort`` SQLite 어댑터 — ``module_history_index`` 단일 SELECT."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import ModuleStatus
from app.eventsourcing.support import SqliteDatabase
from app.storage.query_rows import ModuleHistoryRow

_SELECT_COLUMNS = """
    run_id, module_id, system_code, module_name, status, message, started_at, ended_at,
    duration_ms, current_url, artifacts, ai_category, ai_summary, suite_id, schedule_id,
    triggered_by, requested_at, created_by_user_id, created_by_user_name
"""


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _row_to_history(row) -> ModuleHistoryRow:
    return ModuleHistoryRow(
        run_id=row["run_id"],
        module_id=row["module_id"],
        system_code=row["system_code"],
        module_name=row["module_name"],
        status=ModuleStatus(row["status"]),
        message=row["message"],
        started_at=_parse_dt(row["started_at"]),
        ended_at=_parse_dt(row["ended_at"]),
        duration_ms=row["duration_ms"],
        current_url=row["current_url"],
        artifacts=tuple(json.loads(row["artifacts"] or "[]")),
        ai_category=row["ai_category"],
        ai_summary=row["ai_summary"],
        suite_id=row["suite_id"],
        schedule_id=row["schedule_id"],
        triggered_by=row["triggered_by"],
        requested_at=_parse_dt(row["requested_at"]),
        created_by_user_id=row["created_by_user_id"],
        created_by_user_name=row["created_by_user_name"],
    )


class SqliteModuleHistoryQuery:
    """``ModuleHistoryQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def list_for_system(
        self, system_code: str, *, limit: int | None = None
    ) -> list[ModuleHistoryRow]:
        sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM module_history_index
            WHERE system_code = ?
            ORDER BY requested_at DESC, run_id, module_id
        """
        params: tuple = (system_code,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (system_code, limit)
        rows = await self._db.fetchall(sql, params)
        return [_row_to_history(row) for row in rows]

    async def list_for_runs(self, run_ids: list[str]) -> list[ModuleHistoryRow]:
        if not run_ids:
            return []
        placeholders = ",".join("?" for _ in run_ids)
        rows = await self._db.fetchall(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM module_history_index
            WHERE run_id IN ({placeholders})
            ORDER BY requested_at DESC, run_id, module_id
            """,
            tuple(run_ids),
        )
        return [_row_to_history(row) for row in rows]

    async def list_between(
        self, since: datetime | None, until: datetime | None
    ) -> list[ModuleHistoryRow]:
        clauses: list[str] = []
        params: list = []
        if since is not None:
            clauses.append("requested_at >= ?")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("requested_at <= ?")
            params.append(until.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._db.fetchall(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM module_history_index
            {where}
            ORDER BY requested_at DESC, run_id, module_id
            """,
            tuple(params),
        )
        return [_row_to_history(row) for row in rows]
