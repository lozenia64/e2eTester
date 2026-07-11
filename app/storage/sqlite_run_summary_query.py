"""``RunSummaryQueryPort`` SQLite 어댑터 — ``run_history_index`` 단일 SELECT.

blob(``runs``) 테이블을 절대 만지지 않는다. 필터·정렬·페이지는 전부 SQL 로 수행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import RunStatus
from app.eventsourcing.support import SqliteDatabase
from app.storage.query_rows import Page, RunSummaryFilter, RunSummaryRow

_TERMINAL_FOR_BASELINE = (
    RunStatus.PASSED.value,
    RunStatus.ANOMALY.value,
    RunStatus.ERROR.value,
    RunStatus.FAILED.value,
)

_SELECT_COLUMNS = """
    run_id, system_code, system_name, status, requested_at, started_at, ended_at,
    schedule_id, suite_id, created_by_user_id, created_by_user_name, triggered_by,
    awaiting_input_module_id, awaiting_input_prompt, module_total, module_defined_total,
    module_skipped, module_passed, current_module_name, failed_module_name
"""


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _row_to_summary(row) -> RunSummaryRow:
    return RunSummaryRow(
        run_id=row["run_id"],
        system_code=row["system_code"],
        system_name=row["system_name"],
        status=RunStatus(row["status"]),
        requested_at=_parse_dt(row["requested_at"]),
        started_at=_parse_dt(row["started_at"]),
        ended_at=_parse_dt(row["ended_at"]),
        schedule_id=row["schedule_id"],
        suite_id=row["suite_id"],
        created_by_user_id=row["created_by_user_id"],
        created_by_user_name=row["created_by_user_name"],
        triggered_by=row["triggered_by"] or "manual",
        awaiting_input_module_id=row["awaiting_input_module_id"],
        awaiting_input_prompt=row["awaiting_input_prompt"],
        module_total=row["module_total"] or 0,
        module_defined_total=row["module_defined_total"] or 0,
        module_skipped=row["module_skipped"] or 0,
        module_passed=row["module_passed"] or 0,
        current_module_name=row["current_module_name"],
        failed_module_name=row["failed_module_name"],
    )


def _where(query: RunSummaryFilter) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if query.system_code is not None:
        clauses.append("system_code = ?")
        params.append(query.system_code)
    if query.statuses is not None:
        placeholders = ",".join("?" for _ in query.statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(sorted(status.value for status in query.statuses))
    if query.user_id is not None:
        clauses.append("created_by_user_id = ?")
        params.append(query.user_id)
    if query.user_name_query:
        clauses.append("created_by_user_name LIKE ?")
        params.append(f"%{query.user_name_query.strip()}%")
    if query.schedule_id is not None:
        clauses.append("schedule_id = ?")
        params.append(query.schedule_id)
    if query.suite_id is not None:
        clauses.append("suite_id = ?")
        params.append(query.suite_id)
    if query.requested_since is not None:
        clauses.append("requested_at >= ?")
        params.append(query.requested_since.isoformat())
    if query.requested_before is not None:
        clauses.append("requested_at < ?")
        params.append(query.requested_before.isoformat())
    if query.schedule_tagged_only:
        clauses.append("schedule_id IS NOT NULL")
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


class SqliteRunSummaryQuery:
    """``RunSummaryQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def list_summaries(self, query: RunSummaryFilter, page: Page) -> list[RunSummaryRow]:
        where, params = _where(query)
        rows = await self._db.fetchall(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM run_history_index
            {where}
            ORDER BY requested_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page.limit, page.offset),
        )
        return [_row_to_summary(row) for row in rows]

    async def count(self, query: RunSummaryFilter) -> int:
        where, params = _where(query)
        row = await self._db.fetchone(
            f"SELECT COUNT(*) AS cnt FROM run_history_index{where}",
            tuple(params),
        )
        return int(row["cnt"]) if row else 0

    async def counts_by_status(self) -> dict[str, int]:
        rows = await self._db.fetchall(
            "SELECT status, COUNT(*) AS cnt FROM run_history_index GROUP BY status"
        )
        return {row["status"]: int(row["cnt"]) for row in rows}

    async def list_run_ids(self, query: RunSummaryFilter) -> list[str]:
        where, params = _where(query)
        rows = await self._db.fetchall(
            f"""
            SELECT run_id FROM run_history_index
            {where}
            ORDER BY requested_at DESC
            """,
            tuple(params),
        )
        return [row["run_id"] for row in rows]

    async def last_finished_at_by_system(self) -> dict[str, datetime]:
        rows = await self._db.fetchall(
            "SELECT system_code, last_finished_at FROM system_last_finished"
        )
        result: dict[str, datetime] = {}
        for row in rows:
            moment = _parse_dt(row["last_finished_at"])
            if moment is not None:
                result[row["system_code"]] = moment
        return result

    async def find_previous_finished_run_id(
        self, system_code: str, before: datetime, exclude_run_id: str
    ) -> str | None:
        placeholders = ",".join("?" for _ in _TERMINAL_FOR_BASELINE)
        row = await self._db.fetchone(
            f"""
            SELECT run_id FROM run_history_index
            WHERE system_code = ?
              AND status IN ({placeholders})
              AND requested_at < ?
              AND run_id != ?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (system_code, *_TERMINAL_FOR_BASELINE, before.isoformat(), exclude_run_id),
        )
        return row["run_id"] if row else None
