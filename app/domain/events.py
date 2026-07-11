"""도메인 이벤트 타입군 — write path에서 aggregate가 산출하고 outbox/event store에 기록된다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus


@dataclass(frozen=True)
class DomainEvent:
    """모든 도메인 이벤트의 공통 메타데이터."""

    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    schema_version: int = 1

    @staticmethod
    def create(
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        version: int = 1,
        schema_version: int = 1,
    ) -> DomainEvent:
        return DomainEvent(
            event_id=uuid4().hex,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            version=version,
            schema_version=schema_version,
        )


# --- Run events -----------------------------------------------------------


def run_created(run_id: str, system_code: str, triggered_by: str) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunCreated",
        {"system_code": system_code, "triggered_by": triggered_by},
    )


def run_started(run_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunStarted", {})


def module_queued(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "ModuleQueued", {"module_id": module_id})


def module_started(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "ModuleStarted", {"module_id": module_id})


def module_finished(
    run_id: str,
    module_id: str,
    status: ModuleStatus,
    *,
    system_code: str,
    schedule_id: str | None,
    suite_id: str | None,
    module_name: str | None = None,
    message: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_ms: int | None = None,
    created_by_user_id: str | None = None,
) -> DomainEvent:
    # 프로젝션(이상건 인박스·일간 현황)이 blob 재수화 없이 행을 만들 수 있도록
    # 모듈 종료 사실의 파생 값을 payload 에 함께 싣는다(fat event).
    return DomainEvent.create(
        "Run",
        run_id,
        "ModuleFinished",
        {
            "module_id": module_id,
            "status": status.value,
            "system_code": system_code,
            "schedule_id": schedule_id,
            "suite_id": suite_id,
            "module_name": module_name,
            "message": message,
            "started_at": started_at.isoformat() if started_at else None,
            "ended_at": ended_at.isoformat() if ended_at else None,
            "duration_ms": duration_ms,
            "created_by_user_id": created_by_user_id,
        },
    )


def module_log_appended(run_id: str, module_id: str, message: str) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "ModuleLogAppended",
        {"module_id": module_id, "message": message},
    )


def run_waiting_input(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunWaitingInput", {"module_id": module_id})


def run_resumed(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunResumed", {"module_id": module_id})


def run_finished(
    run_id: str,
    status: RunStatus,
    *,
    system_code: str,
    schedule_id: str | None,
    suite_id: str | None,
    requested_at: datetime,
    ended_at: datetime | None,
    created_by_user_id: str | None,
) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunFinished",
        {
            "status": status.value,
            "system_code": system_code,
            "schedule_id": schedule_id,
            "suite_id": suite_id,
            "requested_at": requested_at.isoformat(),
            "ended_at": ended_at.isoformat() if ended_at else None,
            "created_by_user_id": created_by_user_id,
        },
    )


def run_module_blocked(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunModuleBlocked", {"module_id": module_id})


def run_modules_cancelled(run_id: str, module_ids: list[str]) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunModulesCancelled", {"module_ids": module_ids})


def run_comparison_attached(
    run_id: str,
    baseline_run_id: str | None,
    *,
    newly_failed: list[str] | None = None,
    recovered: list[str] | None = None,
    still_failing: list[str] | None = None,
) -> DomainEvent:
    # 비교 캐시 프로젝션이 blob 재수화 없이 행을 만들 수 있도록 결과를 동봉한다(fat event).
    return DomainEvent.create(
        "Run",
        run_id,
        "RunComparisonAttached",
        {
            "baseline_run_id": baseline_run_id,
            "newly_failed": list(newly_failed or []),
            "recovered": list(recovered or []),
            "still_failing": list(still_failing or []),
        },
    )


def run_sealed_interrupted(run_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunSealedInterrupted", {})


def run_module_retried(run_id: str, module_id: str, attempt: int) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunModuleRetried",
        {"module_id": module_id, "attempt": attempt},
    )


def run_partial_rerun_started(run_id: str, from_module_id: str) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunPartialRerunStarted",
        {"from_module_id": from_module_id},
    )


def module_failure_analysis_attached(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "ModuleFailureAnalysisAttached",
        {"module_id": module_id},
    )


# --- Suite events ---------------------------------------------------------


def suite_created(suite_id: str, triggered_by: str) -> DomainEvent:
    return DomainEvent.create(
        "Suite",
        suite_id,
        "SuiteCreated",
        {"triggered_by": triggered_by},
    )


def suite_started(suite_id: str) -> DomainEvent:
    return DomainEvent.create("Suite", suite_id, "SuiteStarted", {})


def suite_step_started(suite_id: str, step_index: int) -> DomainEvent:
    return DomainEvent.create(
        "Suite",
        suite_id,
        "SuiteStepStarted",
        {"step_index": step_index},
    )


def suite_step_run_linked(suite_id: str, step_index: int, run_id: str) -> DomainEvent:
    return DomainEvent.create(
        "Suite",
        suite_id,
        "SuiteStepRunLinked",
        {"step_index": step_index, "run_id": run_id},
    )


def suite_step_finished(suite_id: str, step_index: int, *, error: str | None = None) -> DomainEvent:
    payload: dict[str, Any] = {"step_index": step_index}
    if error is not None:
        payload["error"] = error
    return DomainEvent.create("Suite", suite_id, "SuiteStepFinished", payload)


def suite_waiting_input(suite_id: str, run_id: str) -> DomainEvent:
    return DomainEvent.create("Suite", suite_id, "SuiteWaitingInput", {"run_id": run_id})


def suite_resumed(suite_id: str) -> DomainEvent:
    return DomainEvent.create("Suite", suite_id, "SuiteResumed", {})


def suite_finished(suite_id: str, status: SuiteStatus) -> DomainEvent:
    return DomainEvent.create("Suite", suite_id, "SuiteFinished", {"status": status.value})
