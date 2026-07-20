"""도메인 이벤트 → 읽기 모델 프로젝션 핸들러."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.schedule_time import schedule_day_label
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES
from app.domain.summary_fields import (
    MODULE_HISTORY_STATUSES,
    module_history_fields_from_wire,
    run_summary_fields,
)
from app.platform.eventing.envelope import EventEnvelope
from app.platform.eventing.hydration import AggregateHydratorPort
from app.platform.eventing.support import SqliteDatabase

PROJECTION_NAMES = (
    "run_history_index",
    "suite_history_index",
    "module_history_index",
    "anomaly_inbox_index",
    "daily_system_status",
    "stats_rollup",
    "schedule_execution_history",
    "system_last_finished",
    "run_comparison_cache",
)
# RunDeleted 는 Run 단위 파생 행(run/module 이력·이상건 인박스·비교 캐시)을 정리한다.
# 일간 현황·통계 롤업은 "그날 점검이 있었다"는 사실의 기록이므로 Run 삭제에도 보존한다.

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


def _module_history_upsert(run_id: str, run_summary: dict, fields: dict) -> Mutation:
    """이벤트·스냅샷 backfill 공용 — ``module_history_index`` 한 행 upsert."""
    return (
        """
        INSERT OR REPLACE INTO module_history_index
            (run_id, module_id, system_code, module_name, status, message,
             started_at, ended_at, duration_ms, current_url, artifacts,
             ai_category, ai_summary, ai_action, suite_id, schedule_id, triggered_by,
             requested_at, created_by_user_id, created_by_user_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            fields["module_id"],
            fields["system_code"],
            fields.get("module_name"),
            fields["status"],
            fields.get("message"),
            fields.get("started_at"),
            fields.get("ended_at"),
            fields.get("duration_ms"),
            fields.get("current_url"),
            json.dumps(fields.get("artifacts", []), ensure_ascii=False),
            fields.get("ai_category"),
            fields.get("ai_summary"),
            fields.get("ai_action"),
            fields.get("suite_id"),
            fields.get("schedule_id"),
            run_summary.get("triggered_by"),
            run_summary.get("requested_at"),
            fields.get("created_by_user_id"),
            run_summary.get("created_by_user_name"),
        ),
    )


def _run_history_upsert(run_id: str, summary: dict) -> Mutation:
    """이벤트에 동봉된 ``run_summary`` 로 요약 인덱스 한 행 전체를 upsert 한다."""
    return (
        """
        INSERT OR REPLACE INTO run_history_index
            (run_id, system_code, system_name, status, requested_at, started_at, ended_at,
             schedule_id, suite_id, created_by_user_id, created_by_user_name, triggered_by,
             awaiting_input_module_id, awaiting_input_prompt, module_total,
             module_defined_total, module_skipped, module_passed, current_module_name,
             failed_module_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            summary["system_code"],
            summary.get("system_name"),
            summary["status"],
            summary["requested_at"],
            summary.get("started_at"),
            summary.get("ended_at"),
            summary.get("schedule_id"),
            summary.get("suite_id"),
            summary.get("created_by_user_id"),
            summary.get("created_by_user_name"),
            summary.get("triggered_by", "manual"),
            summary.get("awaiting_input_module_id"),
            summary.get("awaiting_input_prompt"),
            summary.get("module_total"),
            summary.get("module_defined_total"),
            summary.get("module_skipped"),
            summary.get("module_passed"),
            summary.get("current_module_name"),
            summary.get("failed_module_name"),
        ),
    )


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
        loaders: dict[str, AggregateHydratorPort],
    ) -> None:
        self._db = db
        self._loaders = loaders
        self._cursors: dict[str, int] | None = None

    async def apply(self, event: EventEnvelope, sequence_id: int) -> None:
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
        return await self._loaders["Run"].hydrate(run_id)

    # --- run_history_index --------------------------------------------------

    async def _build_run_history_index(self, event: EventEnvelope) -> list[Mutation]:
        if event.event_type == "RunDeleted":
            return [("DELETE FROM run_history_index WHERE run_id = ?", (event.aggregate_id,))]
        summary = event.payload.get("run_summary")
        if summary is not None:
            # fat event 경로: 애그리거트가 발행 시점에 계산한 요약으로 전체 행을 upsert 한다.
            return [_run_history_upsert(event.aggregate_id, summary)]
        if event.event_type == "RunCreated":
            # 구(thin) RunCreated — 요약이 없어 blob 폴백이 불가피하다(마이그레이션 전 재생 전용).
            run = await self._load_run(event.aggregate_id)
            return [_run_history_upsert(run.run_id, run_summary_fields(run))]
        return self._build_run_history_index_legacy(event)

    def _build_run_history_index_legacy(self, event: EventEnvelope) -> list[Mutation]:
        """요약이 없는 구(thin) 이벤트용 부분 갱신 — 마이그레이션 전 이력 재생 전용."""
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

    # --- suite_history_index --------------------------------------------------

    async def _build_suite_history_index(self, event: EventEnvelope) -> list[Mutation]:
        summary = event.payload.get("suite_summary")
        if summary is None or event.aggregate_type != "Suite":
            return []
        return [
            (
                """
                INSERT OR REPLACE INTO suite_history_index
                    (suite_id, status, requested_at, started_at, ended_at,
                     current_step_index, active_run_id, awaiting_input_run_id,
                     awaiting_input_prompt, browser_mode, selected_system_codes,
                     triggered_by, schedule_id, created_by_user_id, created_by_user_name,
                     step_total, steps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.aggregate_id,
                    summary["status"],
                    summary["requested_at"],
                    summary.get("started_at"),
                    summary.get("ended_at"),
                    summary.get("current_step_index", 0),
                    summary.get("active_run_id"),
                    summary.get("awaiting_input_run_id"),
                    summary.get("awaiting_input_prompt"),
                    summary.get("browser_mode"),
                    json.dumps(summary.get("selected_system_codes", []), ensure_ascii=False),
                    summary.get("triggered_by", "manual"),
                    summary.get("schedule_id"),
                    summary.get("created_by_user_id"),
                    summary.get("created_by_user_name"),
                    summary.get("step_total", 0),
                    json.dumps(summary.get("steps", []), ensure_ascii=False),
                ),
            )
        ]

    # --- module_history_index -------------------------------------------------

    async def _build_module_history_index(self, event: EventEnvelope) -> list[Mutation]:
        if event.event_type == "RunDeleted":
            return [("DELETE FROM module_history_index WHERE run_id = ?", (event.aggregate_id,))]
        if event.event_type == "ModuleFailureAnalysisAttached":
            return [
                (
                    """
                    UPDATE module_history_index
                    SET ai_category = ?, ai_summary = ?, ai_action = ?
                    WHERE run_id = ? AND module_id = ?
                    """,
                    (
                        event.payload.get("category"),
                        event.payload.get("user_summary"),
                        event.payload.get("recommended_action"),
                        event.aggregate_id,
                        event.payload["module_id"],
                    ),
                )
            ]
        if event.event_type == "RunImported":
            run_summary = event.payload.get("run_summary") or {}
            mutations: list[Mutation] = []
            for wire in event.payload.get("all_modules", []):
                if ModuleStatus(wire["status"]) not in MODULE_HISTORY_STATUSES:
                    continue
                fields = module_history_fields_from_wire(run_summary, wire)
                mutations.append(_module_history_upsert(event.aggregate_id, run_summary, fields))
            return mutations
        if event.event_type != "ModuleFinished":
            return []
        payload = event.payload
        if "module_name" not in payload:
            return []  # 구(thin) 이벤트 — 마이그레이션 재합성 전까지 모듈 이력은 채우지 않는다.
        run_summary = payload.get("run_summary") or {}
        fields = {
            "module_id": payload["module_id"],
            "system_code": payload["system_code"],
            "module_name": payload.get("module_name"),
            "status": payload["status"],
            "message": payload.get("message"),
            "started_at": payload.get("started_at"),
            "ended_at": payload.get("ended_at"),
            "duration_ms": payload.get("duration_ms"),
            "current_url": payload.get("current_url"),
            "artifacts": payload.get("artifacts", []),
            "suite_id": payload.get("suite_id"),
            "schedule_id": payload.get("schedule_id"),
            "created_by_user_id": payload.get("created_by_user_id"),
        }
        return [_module_history_upsert(event.aggregate_id, run_summary, fields)]

    # --- anomaly_inbox_index ------------------------------------------------

    async def _build_anomaly_inbox_index(self, event: EventEnvelope) -> list[Mutation]:
        if event.event_type == "RunDeleted":
            return [("DELETE FROM anomaly_inbox_index WHERE run_id = ?", (event.aggregate_id,))]
        if event.event_type != "ModuleFinished":
            return []
        status = ModuleStatus(event.payload["status"])
        if status not in MODULE_ANOMALY_STATUSES and status not in MODULE_ERROR_STATUSES:
            return []
        module_id = event.payload["module_id"]
        ended_at = event.payload.get("ended_at")
        created_by_user_id = event.payload.get("created_by_user_id")
        if "ended_at" not in event.payload:
            # 구(thin) ModuleFinished — blob 폴백(마이그레이션 전 재생 전용).
            run = await self._load_run(event.aggregate_id)
            created_by_user_id = run.created_by_user_id
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
                    f"{event.aggregate_id}::{module_id}",
                    event.aggregate_id,
                    module_id,
                    event.payload["system_code"],
                    status.value,
                    ended_at,
                    created_by_user_id,
                ),
            )
        ]

    # --- daily_system_status ------------------------------------------------

    async def _build_daily_system_status(self, event: EventEnvelope) -> list[Mutation]:
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
                    (day_key, system_code, module_id, last_status, last_run_id,
                     duration_ms, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day_key, system_code, module_id) DO UPDATE SET
                    last_status = excluded.last_status,
                    last_run_id = excluded.last_run_id,
                    duration_ms = excluded.duration_ms,
                    updated_at = excluded.updated_at
                """,
                (
                    day_key,
                    event.payload["system_code"],
                    event.payload["module_id"],
                    status.value,
                    event.aggregate_id,
                    event.payload.get("duration_ms"),
                    event.occurred_at.isoformat(),
                ),
            )
        ]

    # --- stats_rollup -------------------------------------------------------

    async def _build_stats_rollup(self, event: EventEnvelope) -> list[Mutation]:
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

    async def _build_schedule_execution_history(self, event: EventEnvelope) -> list[Mutation]:
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

    async def _build_system_last_finished(self, event: EventEnvelope) -> list[Mutation]:
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

    async def _build_run_comparison_cache(self, event: EventEnvelope) -> list[Mutation]:
        if event.event_type == "RunDeleted":
            return [("DELETE FROM run_comparison_cache WHERE run_id = ?", (event.aggregate_id,))]
        if event.event_type != "RunComparisonAttached":
            return []
        if "newly_failed" in event.payload:
            baseline_run_id = event.payload.get("baseline_run_id")
            newly_failed = event.payload["newly_failed"]
            recovered = event.payload.get("recovered", [])
            still_failing = event.payload.get("still_failing", [])
        else:
            # 구(thin) RunComparisonAttached — blob 폴백(마이그레이션 전 재생 전용).
            run = await self._load_run(event.aggregate_id)
            comparison = run.comparison
            if comparison is None:
                return []
            baseline_run_id = comparison.baseline_run_id
            newly_failed = comparison.newly_failed
            recovered = comparison.recovered
            still_failing = comparison.still_failing
        return [
            (
                """
                INSERT OR REPLACE INTO run_comparison_cache
                    (run_id, baseline_run_id, newly_failed, recovered, still_failing,
                     computed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.aggregate_id,
                    baseline_run_id,
                    json.dumps(newly_failed, ensure_ascii=False),
                    json.dumps(recovered, ensure_ascii=False),
                    json.dumps(still_failing, ensure_ascii=False),
                    event.occurred_at.isoformat(),
                ),
            )
        ]
