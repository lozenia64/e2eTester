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

    @staticmethod
    def create(
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        version: int = 1,
    ) -> DomainEvent:
        return DomainEvent(
            event_id=uuid4().hex,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            version=version,
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


def run_module_queued(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunModuleQueued", {"module_id": module_id})


def run_module_running(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunModuleRunning", {"module_id": module_id})


def run_module_completed(
    run_id: str,
    module_id: str,
    status: ModuleStatus,
    *,
    system_code: str,
    schedule_id: str | None,
    suite_id: str | None,
) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunModuleCompleted",
        {
            "module_id": module_id,
            "status": status.value,
            "system_code": system_code,
            "schedule_id": schedule_id,
            "suite_id": suite_id,
        },
    )


def run_paused_for_otp(run_id: str, module_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunPausedForOtp", {"module_id": module_id})


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


def run_comparison_attached(run_id: str, baseline_run_id: str | None) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunComparisonAttached",
        {"baseline_run_id": baseline_run_id},
    )


def run_sealed_interrupted(run_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunSealedInterrupted", {})


# --- Suite events ---------------------------------------------------------


def suite_finished(suite_id: str, status: SuiteStatus) -> DomainEvent:
    return DomainEvent.create("Suite", suite_id, "SuiteFinished", {"status": status.value})
