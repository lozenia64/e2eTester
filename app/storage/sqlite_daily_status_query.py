"""``daily_system_status`` / ``run_history_index`` 일간 현황 읽기 어댑터."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.eventsourcing.support import SqliteDatabase
from app.storage.query_rows import DailyRunSummaryRow, DailyStatusRow


def _parse_dt(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class SqliteDailyStatusQuery:
    """``DailyStatusQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def list_for_date(
        self,
        date_label: str,
        allowed_system_codes: list[str] | None,
    ) -> list[DailyStatusRow]:
        if allowed_system_codes is not None:
            if not allowed_system_codes:
                return []
            placeholders = ",".join("?" for _ in allowed_system_codes)
            rows = await self._db.fetchall(
                f"""
                SELECT day_key, system_code, module_id, last_status,
                       last_run_id, duration_ms, updated_at
                FROM daily_system_status
                WHERE day_key = ? AND system_code IN ({placeholders})
                """,
                (date_label, *allowed_system_codes),
            )
        else:
            rows = await self._db.fetchall(
                """
                SELECT day_key, system_code, module_id, last_status,
                       last_run_id, duration_ms, updated_at
                FROM daily_system_status
                WHERE day_key = ?
                """,
                (date_label,),
            )
        return [
            DailyStatusRow(
                day_key=row["day_key"],
                system_code=row["system_code"],
                module_id=row["module_id"],
                last_status=ModuleStatus(row["last_status"]),
                last_run_id=row["last_run_id"],
                duration_ms=row["duration_ms"],
                updated_at=_parse_dt(row["updated_at"]),
            )
            for row in rows
        ]

    async def list_run_summaries_for_date(
        self,
        date_label: str,
        since_utc: datetime,
        allowed_system_codes: list[str] | None,
    ) -> list[DailyRunSummaryRow]:
        del date_label  # KST day label; filter uses since_utc boundary from caller
        since_iso = since_utc.isoformat()
        if allowed_system_codes is not None:
            if not allowed_system_codes:
                return []
            placeholders = ",".join("?" for _ in allowed_system_codes)
            rows = await self._db.fetchall(
                f"""
                SELECT run_id, system_code, status, requested_at, triggered_by
                FROM run_history_index
                WHERE requested_at >= ? AND system_code IN ({placeholders})
                ORDER BY requested_at DESC
                """,
                (since_iso, *allowed_system_codes),
            )
        else:
            rows = await self._db.fetchall(
                """
                SELECT run_id, system_code, status, requested_at, triggered_by
                FROM run_history_index
                WHERE requested_at >= ?
                ORDER BY requested_at DESC
                """,
                (since_iso,),
            )
        return [
            DailyRunSummaryRow(
                run_id=row["run_id"],
                system_code=row["system_code"],
                status=RunStatus(row["status"]),
                requested_at=_parse_dt(row["requested_at"]),
                triggered_by=row["triggered_by"] or "manual",
            )
            for row in rows
        ]
