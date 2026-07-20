"""``RunSummaryQueryPort`` SQLite 어댑터 — ``run_history_index`` 단일 SELECT.

blob(``runs``) 테이블을 절대 만지지 않는다. 필터·정렬·페이지는 전부 SQL 로 수행한다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.contexts.run.contracts.query_rows import (
    Page,
    RunComparisonRow,
    RunSummaryFilter,
    RunSummaryRow,
)
from app.core.enums import RunStatus
from app.platform.eventing.support import SqliteDatabase

_TERMINAL_FOR_BASELINE = (
    RunStatus.PASSED.value,
    RunStatus.ANOMALY.value,
    RunStatus.ERROR.value,
    RunStatus.FAILED.value,
)

_LIST_BY_PROJECTION_SQL = """
    SELECT {select_cols}
    FROM system_last_finished s
    INNER JOIN run_history_index r ON r.run_id = (
        SELECT r2.run_id
        FROM run_history_index r2
        WHERE r2.system_code = s.system_code
          AND COALESCE(r2.ended_at, r2.requested_at) = s.last_finished_at
        ORDER BY r2.requested_at DESC
        LIMIT 1
    )
    ORDER BY r.system_code
"""

_FALLBACK_LATEST_PER_SYSTEM_SQL = """
    SELECT {select_cols}
    FROM run_history_index r
    WHERE r.run_id = (
        SELECT r2.run_id
        FROM run_history_index r2
        WHERE r2.system_code = r.system_code
          AND r2.status IN ({terminal})
        ORDER BY COALESCE(r2.ended_at, r2.requested_at) DESC, r2.requested_at DESC
        LIMIT 1
    )
    ORDER BY r.system_code
"""

_SELECT_COLUMNS = """
    run_id, system_code, system_name, status, requested_at, started_at, ended_at,
    schedule_id, suite_id, created_by_user_id, created_by_user_name, triggered_by,
    awaiting_input_module_id, awaiting_input_prompt, module_total, module_defined_total,
    module_skipped, module_passed, current_module_name, failed_module_name
"""

_SELECT_COLUMNS_R = """
    r.run_id, r.system_code, r.system_name, r.status, r.requested_at, r.started_at, r.ended_at,
    r.schedule_id, r.suite_id, r.created_by_user_id, r.created_by_user_name, r.triggered_by,
    r.awaiting_input_module_id, r.awaiting_input_prompt, r.module_total, r.module_defined_total,
    r.module_skipped, r.module_passed, r.current_module_name, r.failed_module_name
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
    if query.system_codes is not None:
        placeholders = ",".join("?" for _ in query.system_codes)
        clauses.append(f"system_code IN ({placeholders})")
        params.extend(sorted(query.system_codes))
    elif query.system_code is not None:
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
    if query.triggered_by == "schedule":
        clauses.append("(triggered_by = 'schedule' OR schedule_id IS NOT NULL)")
    elif query.triggered_by == "suite":
        clauses.append("(triggered_by = 'suite' OR suite_id IS NOT NULL)")
    elif query.triggered_by == "manual":
        clauses.append("(triggered_by = 'manual' OR triggered_by IS NULL OR triggered_by = '')")
    if query.run_id_query:
        clauses.append("run_id LIKE ?")
        params.append(f"{query.run_id_query.strip()}%")
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

    async def counts_by_status_filtered(self, query: RunSummaryFilter) -> dict[str, int]:
        where, params = _where(query)
        rows = await self._db.fetchall(
            f"SELECT status, COUNT(*) AS cnt FROM run_history_index{where} GROUP BY status",
            tuple(params),
        )
        return {row["status"]: int(row["cnt"]) for row in rows}

    async def daily_status_counts(
        self, query: RunSummaryFilter, *, tz: ZoneInfo | None = None
    ) -> list[tuple[str, str, int]]:
        """(day_key, status, count) — ``tz`` 가 있으면 해당 TZ 의 달력 일자로 귀속."""
        where, params = _where(query)
        rows = await self._db.fetchall(
            f"""
            SELECT requested_at, status
            FROM run_history_index
            {where}
            """,
            tuple(params),
        )
        buckets: dict[tuple[str, str], int] = {}
        for row in rows:
            moment = _parse_dt(row["requested_at"])
            if moment is None:
                continue
            if tz is not None:
                day_key = moment.astimezone(tz).strftime("%Y-%m-%d")
            else:
                day_key = str(row["requested_at"])[:10]
            key = (day_key, row["status"])
            buckets[key] = buckets.get(key, 0) + 1
        return [(day, status, count) for (day, status), count in sorted(buckets.items())]

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

    async def list_summaries_for_last_finished_by_system(self) -> list[RunSummaryRow]:
        count_row = await self._db.fetchone("SELECT COUNT(*) AS cnt FROM system_last_finished")
        if not count_row or int(count_row["cnt"]) == 0:
            return await self._fallback_latest_terminal_per_system()
        sql = _LIST_BY_PROJECTION_SQL.format(select_cols=_SELECT_COLUMNS_R)
        rows = await self._db.fetchall(sql)
        if rows:
            return [_row_to_summary(row) for row in rows]
        return await self._fallback_latest_terminal_per_system()

    async def _fallback_latest_terminal_per_system(self) -> list[RunSummaryRow]:
        terminal_ph = ",".join("?" for _ in _TERMINAL_FOR_BASELINE)
        sql = _FALLBACK_LATEST_PER_SYSTEM_SQL.format(
            select_cols=_SELECT_COLUMNS,
            terminal=terminal_ph,
        )
        rows = await self._db.fetchall(sql, _TERMINAL_FOR_BASELINE)
        return [_row_to_summary(row) for row in rows]

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

    async def list_comparisons(self, run_ids: list[str]) -> dict[str, RunComparisonRow]:
        if not run_ids:
            return {}
        placeholders = ",".join("?" for _ in run_ids)
        rows = await self._db.fetchall(
            f"""
            SELECT run_id, baseline_run_id, newly_failed, recovered, still_failing
            FROM run_comparison_cache
            WHERE run_id IN ({placeholders})
            """,
            tuple(run_ids),
        )
        return {
            row["run_id"]: RunComparisonRow(
                run_id=row["run_id"],
                baseline_run_id=row["baseline_run_id"],
                newly_failed=tuple(json.loads(row["newly_failed"] or "[]")),
                recovered=tuple(json.loads(row["recovered"] or "[]")),
                still_failing=tuple(json.loads(row["still_failing"] or "[]")),
            )
            for row in rows
        }
