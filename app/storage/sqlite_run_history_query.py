"""Run 이력 조회 — ``run_history_index`` 프로젝션 + ``runs`` blob 조립."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import RunStatus
from app.core.models import Run
from app.eventsourcing.support import SqliteDatabase
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class SqliteRunHistoryQuery:
    """``RunHistoryQueryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase, write_repo: SqliteRunWriteRepository) -> None:
        self._db = db
        self._write_repo = write_repo

    async def list_all_runs(self) -> list[Run]:
        rows = await self._db.fetchall(
            "SELECT run_id FROM run_history_index ORDER BY requested_at DESC"
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def get_run(self, run_id: str) -> Run:
        return await self._write_repo.get_run(run_id)

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        rows = await self._db.fetchall(
            """
            SELECT run_id FROM run_history_index
            WHERE created_by_user_id = ?
            ORDER BY requested_at DESC
            """,
            (user_id,),
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def list_runs_by_system(self, system_code: str) -> list[Run]:
        rows = await self._db.fetchall(
            """
            SELECT run_id FROM run_history_index
            WHERE system_code = ?
            ORDER BY requested_at DESC
            """,
            (system_code,),
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def list_runs_by_schedule(self, schedule_id: str, limit: int = 30) -> list[Run]:
        rows = await self._db.fetchall(
            """
            SELECT run_id FROM run_history_index
            WHERE schedule_id = ?
            ORDER BY requested_at DESC
            LIMIT ?
            """,
            (schedule_id, limit),
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def list_schedule_tagged_runs(self) -> list[Run]:
        rows = await self._db.fetchall(
            """
            SELECT run_id FROM run_history_index
            WHERE schedule_id IS NOT NULL
            ORDER BY requested_at DESC
            """
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def list_runs_since(self, since: datetime) -> list[Run]:
        since_iso = since.isoformat()
        rows = await self._db.fetchall(
            """
            SELECT run_id FROM run_history_index
            WHERE requested_at >= ?
            ORDER BY requested_at DESC
            """,
            (since_iso,),
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def list_runs_with_statuses(self, statuses: frozenset) -> list[Run]:
        if not statuses:
            return []
        placeholders = ",".join("?" for _ in statuses)
        values = tuple(status.value for status in statuses)
        rows = await self._db.fetchall(
            f"""
            SELECT run_id FROM run_history_index
            WHERE status IN ({placeholders})
            ORDER BY requested_at DESC
            """,
            values,
        )
        return await self._load_many([row["run_id"] for row in rows])

    async def list_waiting_input_runs(self) -> list[Run]:
        return await self.list_runs_with_statuses(frozenset({RunStatus.WAITING_INPUT}))

    async def last_finished_at_by_system(self) -> dict[str, datetime]:
        rows = await self._db.fetchall(
            "SELECT system_code, last_finished_at FROM system_last_finished"
        )
        result: dict[str, datetime] = {}
        for row in rows:
            moment = _parse_dt(row["last_finished_at"])
            if moment is not None:
                result[row["system_code"]] = (
                    moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
                )
        return result

    async def find_previous_finished_run(self, run: Run) -> Run | None:
        rows = await self._db.fetchall(
            """
            SELECT run_id FROM run_history_index
            WHERE system_code = ?
              AND status IN (?, ?, ?, ?)
              AND requested_at < ?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (
                run.system_code,
                RunStatus.PASSED.value,
                RunStatus.ANOMALY.value,
                RunStatus.ERROR.value,
                RunStatus.FAILED.value,
                run.requested_at.isoformat(),
            ),
        )
        if not rows:
            return None
        candidate_id = rows[0]["run_id"]
        if candidate_id == run.run_id:
            return None
        try:
            return await self._write_repo.get_run(candidate_id)
        except KeyError:
            return None

    async def _load_many(self, run_ids: list[str]) -> list[Run]:
        runs: list[Run] = []
        for run_id in run_ids:
            try:
                runs.append(await self._write_repo.get_run(run_id))
            except KeyError:
                continue
        return runs
