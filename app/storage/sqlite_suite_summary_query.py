"""``SuiteSummaryQueryPort`` SQLite 어댑터 — ``suite_history_index`` 단일 SELECT."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import SuiteStatus
from app.platform.eventing.support import SqliteDatabase
from app.storage.query_rows import SuiteStepRow, SuiteSummaryRow

_SELECT_COLUMNS = """
    suite_id, status, requested_at, started_at, ended_at, current_step_index,
    active_run_id, awaiting_input_run_id, awaiting_input_prompt, browser_mode,
    selected_system_codes, triggered_by, schedule_id, created_by_user_id,
    created_by_user_name, step_total, steps
"""


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _row_to_summary(row) -> SuiteSummaryRow:
    steps = tuple(
        SuiteStepRow(
            system_code=step["system_code"],
            system_name=step["system_name"],
            order=step["order"],
            run_id=step.get("run_id"),
            status=SuiteStatus(step["status"]),
            module_total=step.get("module_total", 0),
        )
        for step in json.loads(row["steps"] or "[]")
    )
    return SuiteSummaryRow(
        suite_id=row["suite_id"],
        status=SuiteStatus(row["status"]),
        requested_at=_parse_dt(row["requested_at"]),
        started_at=_parse_dt(row["started_at"]),
        ended_at=_parse_dt(row["ended_at"]),
        current_step_index=row["current_step_index"] or 0,
        active_run_id=row["active_run_id"],
        awaiting_input_run_id=row["awaiting_input_run_id"],
        awaiting_input_prompt=row["awaiting_input_prompt"],
        browser_mode=row["browser_mode"],
        selected_system_codes=tuple(json.loads(row["selected_system_codes"] or "[]")),
        triggered_by=row["triggered_by"] or "manual",
        schedule_id=row["schedule_id"],
        created_by_user_id=row["created_by_user_id"],
        created_by_user_name=row["created_by_user_name"],
        step_total=row["step_total"] or 0,
        steps=steps,
    )


def _where(
    *,
    requested_before: datetime | None,
    requested_since: datetime | None,
    statuses: frozenset[SuiteStatus] | None,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if statuses is not None:
        placeholders = ",".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(sorted(status.value for status in statuses))
    if requested_since is not None:
        clauses.append("requested_at >= ?")
        params.append(requested_since.isoformat())
    if requested_before is not None:
        clauses.append("requested_at < ?")
        params.append(requested_before.isoformat())
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


class SqliteSuiteSummaryQuery:
    """``SuiteSummaryQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def list_summaries(
        self,
        *,
        limit: int | None = None,
        requested_before: datetime | None = None,
        requested_since: datetime | None = None,
        statuses: frozenset[SuiteStatus] | None = None,
    ) -> list[SuiteSummaryRow]:
        where_sql, params = _where(
            requested_before=requested_before,
            requested_since=requested_since,
            statuses=statuses,
        )
        sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM suite_history_index
            {where_sql}
            ORDER BY requested_at DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params = [*params, limit]
        rows = await self._db.fetchall(sql, tuple(params))
        return [_row_to_summary(row) for row in rows]

    async def counts_by_status(self) -> dict[str, int]:
        rows = await self._db.fetchall(
            "SELECT status, COUNT(*) AS cnt FROM suite_history_index GROUP BY status"
        )
        return {row["status"]: int(row["cnt"]) for row in rows}
