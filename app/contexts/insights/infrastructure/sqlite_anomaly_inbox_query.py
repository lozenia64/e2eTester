"""``anomaly_inbox_index`` 프로젝션 읽기 어댑터."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus
from app.platform.eventing.support import SqliteDatabase
from app.storage.query_rows import AnomalyInboxRow


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class SqliteAnomalyInboxQuery:
    """``AnomalyInboxQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def list_page(
        self,
        allowed_system_codes: list[str] | None,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[AnomalyInboxRow]:
        if allowed_system_codes is not None:
            if not allowed_system_codes:
                return []
            placeholders = ",".join("?" for _ in allowed_system_codes)
            rows = await self._db.fetchall(
                f"""
                SELECT module_run_id, run_id, module_id, system_code, status,
                       ended_at, created_by_user_id
                FROM anomaly_inbox_index
                WHERE system_code IN ({placeholders})
                ORDER BY ended_at DESC, module_run_id DESC
                LIMIT ? OFFSET ?
                """,
                (*allowed_system_codes, limit, offset),
            )
        else:
            rows = await self._db.fetchall(
                """
                SELECT module_run_id, run_id, module_id, system_code, status,
                       ended_at, created_by_user_id
                FROM anomaly_inbox_index
                ORDER BY ended_at DESC, module_run_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        return [_row_to_inbox(row) for row in rows]


def _row_to_inbox(row) -> AnomalyInboxRow:
    return AnomalyInboxRow(
        module_run_id=row["module_run_id"],
        run_id=row["run_id"],
        module_id=row["module_id"],
        system_code=row["system_code"],
        status=ModuleStatus(row["status"]),
        ended_at=_parse_dt(row["ended_at"]),
        created_by_user_id=row["created_by_user_id"],
    )
