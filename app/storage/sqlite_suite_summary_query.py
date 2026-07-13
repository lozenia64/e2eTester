"""``SuiteSummaryQueryPort`` SQLite 어댑터 — ``suite_history_index`` 단일 SELECT."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import SuiteStatus
from app.eventsourcing.support import SqliteDatabase
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


class SqliteSuiteSummaryQuery:
    """``SuiteSummaryQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def list_summaries(self, *, limit: int | None = None) -> list[SuiteSummaryRow]:
        sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM suite_history_index
            ORDER BY requested_at DESC
        """
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        rows = await self._db.fetchall(sql, params)
        return [_row_to_summary(row) for row in rows]

    async def counts_by_status(self) -> dict[str, int]:
        rows = await self._db.fetchall(
            "SELECT status, COUNT(*) AS cnt FROM suite_history_index GROUP BY status"
        )
        return {row["status"]: int(row["cnt"]) for row in rows}
