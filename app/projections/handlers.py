"""도메인 이벤트 → 읽기 모델 프로젝션 핸들러."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES
from app.domain.events import DomainEvent
from app.eventsourcing.support import SqliteDatabase
from app.scheduling.scheduler import schedule_today_label
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository

PROJECTION_NAMES = (
    "run_history_index",
    "anomaly_inbox_index",
    "daily_system_status",
    "stats_rollup",
    "schedule_execution_history",
    "system_last_finished",
    "run_comparison_cache",
)

_TERMINAL_RUN_STATUSES = {
    RunStatus.PASSED,
    RunStatus.ANOMALY,
    RunStatus.ERROR,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


class ProjectionHandlers:
    """이벤트 타입별 프로젝션 갱신(멱등)."""

    def __init__(
        self,
        db: SqliteDatabase,
        write_repo: SqliteRunWriteRepository,
    ) -> None:
        self._db = db
        self._write_repo = write_repo

    async def apply(self, event: DomainEvent) -> None:
        for name in PROJECTION_NAMES:
            if await self._is_applied(name, event.event_id):
                continue
            handler = getattr(self, f"_apply_{name}", None)
            if handler is None:
                continue
            await handler(event)
            await self._mark_applied(name, event.event_id)

    async def _is_applied(self, projection_name: str, event_id: str) -> bool:
        row = await self._db.fetchone(
            """
            SELECT 1 FROM projection_checkpoints
            WHERE projection_name = ? AND event_id = ?
            """,
            (projection_name, event_id),
        )
        return row is not None

    async def _mark_applied(self, projection_name: str, event_id: str) -> None:
        await self._db.execute(
            """
            INSERT OR IGNORE INTO projection_checkpoints
                (projection_name, event_id, applied_at)
            VALUES (?, ?, ?)
            """,
            (projection_name, event_id, datetime.now(UTC).isoformat()),
        )

    async def _load_run(self, run_id: str):
        return await self._write_repo.get_run(run_id)

    # --- run_history_index --------------------------------------------------

    async def _apply_run_history_index(self, event: DomainEvent) -> None:
        if event.event_type == "RunCreated":
            run = await self._load_run(event.aggregate_id)
            await self._db.execute(
                """
                INSERT OR REPLACE INTO run_history_index
                    (run_id, system_code, status, requested_at, ended_at,
                     schedule_id, suite_id, created_by_user_id, created_by_user_name, triggered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.system_code,
                    run.status.value,
                    run.requested_at.isoformat(),
                    run.ended_at.isoformat() if run.ended_at else None,
                    run.schedule_id,
                    run.suite_id,
                    run.created_by_user_id,
                    run.created_by_user_name,
                    run.triggered_by,
                ),
            )
            return

        if event.event_type == "RunStarted":
            await self._db.execute(
                "UPDATE run_history_index SET status = ? WHERE run_id = ?",
                (RunStatus.RUNNING.value, event.aggregate_id),
            )
            return

        if event.event_type in {"RunFinished", "RunSealedInterrupted"}:
            payload = event.payload
            await self._db.execute(
                """
                UPDATE run_history_index
                SET status = ?, ended_at = ?
                WHERE run_id = ?
                """,
                (
                    payload.get("status", RunStatus.CANCELLED.value),
                    payload.get("ended_at"),
                    event.aggregate_id,
                ),
            )
            return

        if event.event_type == "RunPausedForOtp":
            await self._db.execute(
                "UPDATE run_history_index SET status = ? WHERE run_id = ?",
                (RunStatus.WAITING_INPUT.value, event.aggregate_id),
            )
            return

        if event.event_type == "RunResumed":
            await self._db.execute(
                "UPDATE run_history_index SET status = ? WHERE run_id = ?",
                (RunStatus.RUNNING.value, event.aggregate_id),
            )

    # --- anomaly_inbox_index ------------------------------------------------

    async def _apply_anomaly_inbox_index(self, event: DomainEvent) -> None:
        if event.event_type != "RunModuleCompleted":
            return
        status = ModuleStatus(event.payload["status"])
        if status not in MODULE_ANOMALY_STATUSES and status not in MODULE_ERROR_STATUSES:
            return
        run = await self._load_run(event.aggregate_id)
        module_id = event.payload["module_id"]
        module_run_id = f"{run.run_id}::{module_id}"
        ended_at = None
        for module in run.modules:
            if module.module_id == module_id:
                ended_at = module.ended_at.isoformat() if module.ended_at else None
                break
        await self._db.execute(
            """
            INSERT OR REPLACE INTO anomaly_inbox_index
                (module_run_id, run_id, module_id, system_code, status, ended_at, created_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                module_run_id,
                run.run_id,
                module_id,
                run.system_code,
                status.value,
                ended_at,
                run.created_by_user_id,
            ),
        )

    # --- daily_system_status ------------------------------------------------

    async def _apply_daily_system_status(self, event: DomainEvent) -> None:
        if event.event_type != "RunModuleCompleted":
            return
        status = ModuleStatus(event.payload["status"])
        if status in {ModuleStatus.PENDING, ModuleStatus.QUEUED, ModuleStatus.SKIPPED}:
            return
        day_key = schedule_today_label()
        await self._db.execute(
            """
            INSERT INTO daily_system_status
                (day_key, system_code, module_id, last_status, last_run_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(day_key, system_code, module_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_run_id = excluded.last_run_id,
                updated_at = excluded.updated_at
            """,
            (
                day_key,
                event.payload["system_code"],
                event.payload["module_id"],
                status.value,
                event.aggregate_id,
                datetime.now(UTC).isoformat(),
            ),
        )

    # --- stats_rollup -------------------------------------------------------

    async def _apply_stats_rollup(self, event: DomainEvent) -> None:
        if event.event_type != "RunFinished":
            return
        status = RunStatus(event.payload["status"])
        if status not in _TERMINAL_RUN_STATUSES:
            return
        requested_at = datetime.fromisoformat(event.payload["requested_at"])
        day_key = requested_at.astimezone(UTC).strftime("%Y-%m-%d")
        system_code = event.payload["system_code"]
        column = {
            RunStatus.PASSED: "passed_count",
            RunStatus.ANOMALY: "anomaly_count",
            RunStatus.FAILED: "anomaly_count",
            RunStatus.ERROR: "error_count",
            RunStatus.CANCELLED: "cancelled_count",
        }.get(status)
        if column is None:
            return
        await self._db.execute(
            """
            INSERT INTO stats_rollup
                (day_key, system_code, passed_count, anomaly_count, error_count, cancelled_count)
            VALUES (?, ?, 0, 0, 0, 0)
            ON CONFLICT(day_key, system_code) DO NOTHING
            """,
            (day_key, system_code),
        )
        await self._db.execute(
            f"""
            UPDATE stats_rollup
            SET {column} = {column} + 1
            WHERE day_key = ? AND system_code = ?
            """,
            (day_key, system_code),
        )

    # --- schedule_execution_history -----------------------------------------

    async def _apply_schedule_execution_history(self, event: DomainEvent) -> None:
        if event.event_type != "RunFinished":
            return
        schedule_id = event.payload.get("schedule_id")
        if not schedule_id:
            return
        await self._db.execute(
            """
            INSERT OR REPLACE INTO schedule_execution_history
                (schedule_id, run_id, status, requested_at, ended_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                schedule_id,
                event.aggregate_id,
                event.payload["status"],
                event.payload["requested_at"],
                event.payload.get("ended_at"),
            ),
        )

    # --- system_last_finished -----------------------------------------------

    async def _apply_system_last_finished(self, event: DomainEvent) -> None:
        if event.event_type != "RunFinished":
            return
        status = RunStatus(event.payload["status"])
        if status == RunStatus.CANCELLED:
            return
        if status not in _TERMINAL_RUN_STATUSES:
            return
        ended_at = event.payload.get("ended_at") or event.payload["requested_at"]
        await self._db.execute(
            """
            INSERT INTO system_last_finished (system_code, last_finished_at)
            VALUES (?, ?)
            ON CONFLICT(system_code) DO UPDATE SET
                last_finished_at = excluded.last_finished_at
            WHERE excluded.last_finished_at > system_last_finished.last_finished_at
            """,
            (event.payload["system_code"], ended_at),
        )

    # --- run_comparison_cache -----------------------------------------------

    async def _apply_run_comparison_cache(self, event: DomainEvent) -> None:
        if event.event_type != "RunComparisonAttached":
            return
        run = await self._load_run(event.aggregate_id)
        comparison = run.comparison
        if comparison is None:
            return
        await self._db.execute(
            """
            INSERT OR REPLACE INTO run_comparison_cache
                (run_id, baseline_run_id, newly_failed, recovered, still_failing, computed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                comparison.baseline_run_id,
                json.dumps(comparison.newly_failed, ensure_ascii=False),
                json.dumps(comparison.recovered, ensure_ascii=False),
                json.dumps(comparison.still_failing, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
            ),
        )
