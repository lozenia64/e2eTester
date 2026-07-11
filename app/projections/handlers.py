"""도메인 이벤트 → 읽기 모델 프로젝션 핸들러."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES
from app.domain.events import DomainEvent
from app.eventsourcing.support import SqliteDatabase
from app.scheduling.scheduler import schedule_day_label
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

# 프로젝션 뮤테이션 한 건: (SQL, 파라미터). 빌더는 읽기만 하고 쓰기는 apply 가
# 커서 전진과 **같은 트랜잭션**으로 수행한다.
Mutation = tuple[str, tuple]

_ADVANCE_CURSOR_SQL = """
INSERT INTO projection_cursor (projection_name, last_sequence_id, updated_at)
VALUES (?, ?, ?)
ON CONFLICT(projection_name) DO UPDATE SET
    last_sequence_id = excluded.last_sequence_id,
    updated_at = excluded.updated_at
"""


class ProjectionHandlers:
    """이벤트 타입별 프로젝션 갱신.

    멱등성은 프로젝션별 **단조 커서**(``projection_cursor.last_sequence_id``)로 보장한다:
    이벤트의 정본 시퀀스(``domain_events.sequence_id``)가 커서 이하이면 이미 적용된
    이벤트이므로 건너뛴다. 프로젝션 뮤테이션과 커서 전진은 **한 트랜잭션**이므로, 재전달
    (릴레이 크래시 후 미발행 재클레임)이 와도 비멱등 뮤테이션(stats_rollup 증분)이 이중
    적용될 수 없다. 빌더(``_build_*``)는 트랜잭션 밖에서 읽기만 수행하고 뮤테이션 목록을
    돌려준다. 모든 뮤테이션은 이벤트 발생 시각(``occurred_at``) 기준으로 결정적이어서,
    ``scripts/rebuild_projections.py`` 재생이 라이브 적용과 동일한 행을 만든다.
    """

    def __init__(
        self,
        db: SqliteDatabase,
        write_repo: SqliteRunWriteRepository,
    ) -> None:
        self._db = db
        self._write_repo = write_repo
        self._cursors: dict[str, int] | None = None

    async def apply(self, event: DomainEvent, sequence_id: int) -> None:
        cursors = await self._load_cursors()
        mutations: list[Mutation] = []
        advanced: list[str] = []
        for name in PROJECTION_NAMES:
            if sequence_id <= cursors.get(name, 0):
                continue
            builder = getattr(self, f"_build_{name}", None)
            if builder is not None:
                mutations.extend(await builder(event))
            advanced.append(name)
        if not advanced:
            return
        now = datetime.now(UTC).isoformat()
        async with await self._db.transaction() as tx:
            for sql, params in mutations:
                tx.execute(sql, params)
            for name in advanced:
                tx.execute(_ADVANCE_CURSOR_SQL, (name, sequence_id, now))
        for name in advanced:
            cursors[name] = sequence_id

    async def _load_cursors(self) -> dict[str, int]:
        if self._cursors is None:
            rows = await self._db.fetchall(
                "SELECT projection_name, last_sequence_id FROM projection_cursor"
            )
            self._cursors = {row["projection_name"]: row["last_sequence_id"] for row in rows}
        return self._cursors

    async def _load_run(self, run_id: str):
        return await self._write_repo.get_run(run_id)

    # --- run_history_index --------------------------------------------------

    async def _build_run_history_index(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type == "RunCreated":
            run = await self._load_run(event.aggregate_id)
            return [
                (
                    """
                    INSERT OR REPLACE INTO run_history_index
                        (run_id, system_code, status, requested_at, ended_at,
                         schedule_id, suite_id, created_by_user_id, created_by_user_name,
                         triggered_by)
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
            ]

        if event.event_type == "RunStarted":
            return [
                (
                    "UPDATE run_history_index SET status = ? WHERE run_id = ?",
                    (RunStatus.RUNNING.value, event.aggregate_id),
                )
            ]

        if event.event_type in {"RunFinished", "RunSealedInterrupted"}:
            payload = event.payload
            return [
                (
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
            ]

        if event.event_type == "RunWaitingInput":
            return [
                (
                    "UPDATE run_history_index SET status = ? WHERE run_id = ?",
                    (RunStatus.WAITING_INPUT.value, event.aggregate_id),
                )
            ]

        if event.event_type == "RunResumed":
            return [
                (
                    "UPDATE run_history_index SET status = ? WHERE run_id = ?",
                    (RunStatus.RUNNING.value, event.aggregate_id),
                )
            ]
        return []

    # --- anomaly_inbox_index ------------------------------------------------

    async def _build_anomaly_inbox_index(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type != "ModuleFinished":
            return []
        status = ModuleStatus(event.payload["status"])
        if status not in MODULE_ANOMALY_STATUSES and status not in MODULE_ERROR_STATUSES:
            return []
        run = await self._load_run(event.aggregate_id)
        module_id = event.payload["module_id"]
        module_run_id = f"{run.run_id}::{module_id}"
        ended_at = None
        for module in run.modules:
            if module.module_id == module_id:
                ended_at = module.ended_at.isoformat() if module.ended_at else None
                break
        return [
            (
                """
                INSERT OR REPLACE INTO anomaly_inbox_index
                    (module_run_id, run_id, module_id, system_code, status, ended_at,
                     created_by_user_id)
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
        ]

    # --- daily_system_status ------------------------------------------------

    async def _build_daily_system_status(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type != "ModuleFinished":
            return []
        status = ModuleStatus(event.payload["status"])
        if status in {ModuleStatus.PENDING, ModuleStatus.QUEUED, ModuleStatus.SKIPPED}:
            return []
        # 날짜 귀속·updated_at 모두 이벤트 발생 시각 기준(리빌드 결정성).
        day_key = schedule_day_label(event.occurred_at)
        return [
            (
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
                    event.occurred_at.isoformat(),
                ),
            )
        ]

    # --- stats_rollup -------------------------------------------------------

    async def _build_stats_rollup(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type != "RunFinished":
            return []
        status = RunStatus(event.payload["status"])
        if status not in _TERMINAL_RUN_STATUSES:
            return []
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
            return []
        return [
            (
                """
                INSERT INTO stats_rollup
                    (day_key, system_code, passed_count, anomaly_count, error_count,
                     cancelled_count)
                VALUES (?, ?, 0, 0, 0, 0)
                ON CONFLICT(day_key, system_code) DO NOTHING
                """,
                (day_key, system_code),
            ),
            (
                f"""
                UPDATE stats_rollup
                SET {column} = {column} + 1
                WHERE day_key = ? AND system_code = ?
                """,
                (day_key, system_code),
            ),
        ]

    # --- schedule_execution_history -----------------------------------------

    async def _build_schedule_execution_history(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type != "RunFinished":
            return []
        schedule_id = event.payload.get("schedule_id")
        if not schedule_id:
            return []
        return [
            (
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
        ]

    # --- system_last_finished -----------------------------------------------

    async def _build_system_last_finished(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type != "RunFinished":
            return []
        status = RunStatus(event.payload["status"])
        if status == RunStatus.CANCELLED:
            return []
        if status not in _TERMINAL_RUN_STATUSES:
            return []
        ended_at = event.payload.get("ended_at") or event.payload["requested_at"]
        return [
            (
                """
                INSERT INTO system_last_finished (system_code, last_finished_at)
                VALUES (?, ?)
                ON CONFLICT(system_code) DO UPDATE SET
                    last_finished_at = excluded.last_finished_at
                WHERE excluded.last_finished_at > system_last_finished.last_finished_at
                """,
                (event.payload["system_code"], ended_at),
            )
        ]

    # --- run_comparison_cache -----------------------------------------------

    async def _build_run_comparison_cache(self, event: DomainEvent) -> list[Mutation]:
        if event.event_type != "RunComparisonAttached":
            return []
        run = await self._load_run(event.aggregate_id)
        comparison = run.comparison
        if comparison is None:
            return []
        return [
            (
                """
                INSERT OR REPLACE INTO run_comparison_cache
                    (run_id, baseline_run_id, newly_failed, recovered, still_failing,
                     computed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    comparison.baseline_run_id,
                    json.dumps(comparison.newly_failed, ensure_ascii=False),
                    json.dumps(comparison.recovered, ensure_ascii=False),
                    json.dumps(comparison.still_failing, ensure_ascii=False),
                    event.occurred_at.isoformat(),
                ),
            )
        ]
