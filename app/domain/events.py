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


def run_created(
    run_id: str,
    system_code: str,
    triggered_by: str,
    *,
    all_modules: list[dict] | None = None,
) -> DomainEvent:
    # 이벤트를 진실의 원천으로 만드는 evolve 폴드가 빈 상태에서 초기 Run 을 재구성할 수 있도록
    # 초기 모듈 전체 스냅샷을 싣는다. 런레벨 초기 필드는 _emit 이 주입하는 run_summary 가 담는다.
    return DomainEvent.create(
        "Run",
        run_id,
        "RunCreated",
        {
            "system_code": system_code,
            "triggered_by": triggered_by,
            "all_modules": all_modules or [],
        },
    )


def run_started(run_id: str) -> DomainEvent:
    return DomainEvent.create("Run", run_id, "RunStarted", {})


def module_queued(run_id: str, module_id: str, *, module: dict | None = None) -> DomainEvent:
    # 실시간 프로젝터가 blob 재수화 없이 module_* WS 이벤트를 만들 수 있도록
    # 모듈 본문(로그 제외)을 payload 에 동봉한다(fat event).
    return DomainEvent.create(
        "Run", run_id, "ModuleQueued", {"module_id": module_id, "module": module}
    )


def module_started(run_id: str, module_id: str, *, module: dict | None = None) -> DomainEvent:
    return DomainEvent.create(
        "Run", run_id, "ModuleStarted", {"module_id": module_id, "module": module}
    )


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
    current_url: str | None = None,
    artifacts: list[str] | None = None,
    module: dict | None = None,
) -> DomainEvent:
    # 프로젝션(이상건 인박스·일간 현황·모듈 이력)과 실시간 프로젝터가 blob 재수화 없이
    # 행/WS payload 를 만들 수 있도록 모듈 종료 사실의 파생 값을 payload 에 싣는다(fat event).
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
            "current_url": current_url,
            "artifacts": list(artifacts or []),
            "module": module,
        },
    )


def run_waiting_input(run_id: str, module_id: str, *, module: dict | None = None) -> DomainEvent:
    return DomainEvent.create(
        "Run", run_id, "RunWaitingInput", {"module_id": module_id, "module": module}
    )


def run_resumed(run_id: str, module_id: str, *, module: dict | None = None) -> DomainEvent:
    return DomainEvent.create(
        "Run", run_id, "RunResumed", {"module_id": module_id, "module": module}
    )


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


def run_module_blocked(run_id: str, module_id: str, *, module: dict | None = None) -> DomainEvent:
    return DomainEvent.create(
        "Run", run_id, "RunModuleBlocked", {"module_id": module_id, "module": module}
    )


def run_modules_cancelled(
    run_id: str, module_ids: list[str], *, modules: list[dict] | None = None
) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunModulesCancelled",
        {"module_ids": module_ids, "modules": list(modules or [])},
    )


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


def run_sealed_interrupted(run_id: str, *, all_modules: list[dict] | None = None) -> DomainEvent:
    # 봉인은 여러 모듈을 한 번에 CANCELLED 로 바꾸므로, evolve 완전성을 위해 전체 모듈
    # 스냅샷을 싣는다(개별 module_finished 이벤트를 내지 않는 벌크 전이).
    return DomainEvent.create(
        "Run", run_id, "RunSealedInterrupted", {"all_modules": all_modules or []}
    )


def run_module_retried(
    run_id: str, module_id: str, attempt: int, *, module: dict | None = None
) -> DomainEvent:
    return DomainEvent.create(
        "Run",
        run_id,
        "RunModuleRetried",
        {"module_id": module_id, "attempt": attempt, "module": module},
    )


def run_partial_rerun_started(
    run_id: str, from_module_id: str, *, all_modules: list[dict] | None = None
) -> DomainEvent:
    # 부분 재실행은 from_index 이후 모듈들을 한 번에 초기화하므로, evolve 완전성을 위해
    # 전체 모듈 스냅샷을 싣는다(개별 모듈 리셋 이벤트를 내지 않는 벌크 전이).
    return DomainEvent.create(
        "Run",
        run_id,
        "RunPartialRerunStarted",
        {"from_module_id": from_module_id, "all_modules": all_modules or []},
    )


def module_failure_analysis_attached(
    run_id: str,
    module_id: str,
    *,
    category: str | None = None,
    user_summary: str | None = None,
    recommended_action: str | None = None,
    module: dict | None = None,
) -> DomainEvent:
    # 모듈 이력 프로젝션이 실패 유형 분포·요약·권장 조치를 blob 재수화 없이 채우도록
    # 동봉한다(fat event).
    return DomainEvent.create(
        "Run",
        run_id,
        "ModuleFailureAnalysisAttached",
        {
            "module_id": module_id,
            "category": category,
            "user_summary": user_summary,
            "recommended_action": recommended_action,
            "module": module,
        },
    )


def run_imported(
    run_id: str,
    *,
    run_summary: dict,
    all_modules: list[dict],
) -> DomainEvent:
    """레거시 blob → 이벤트 스트림 1회성 마이그레이션의 genesis 이벤트(WP-B6).

    합성 가능한 세부 전이를 일일이 재구성하는 대신, 종료된 Run 의 **최종 상태 전체**
    (run_summary + 모든 모듈 와이어)를 한 이벤트에 담는다. ``evolve`` 는 이를 ``RunCreated`` 와
    동일하게 접어(빈 상태에서 초기화) 권위 있는 스냅샷을 재구성한다 — 이후 프로젝션 리빌드가
    이 스트림에서 결정적으로 파생된다. ``schema_version`` 으로 합성 출처를 표기한다.
    """
    return DomainEvent.create(
        "Run",
        run_id,
        "RunImported",
        {"run_summary": run_summary, "all_modules": all_modules},
        schema_version=2,
    )


def run_deleted(run_id: str) -> DomainEvent:
    """Run 삭제(보존 정리·수동 삭제) — 프로젝션이 파생 행을 함께 정리하도록 발행한다.

    삭제는 종료된 Run 에 대한 저장소 수준 작업이라 애그리거트가 아니라 서비스가 발행한다.
    리빌드 재생 시에도 같은 순서로 재적용되어 삭제된 Run 의 행이 되살아나지 않는다(결정성).
    """
    return DomainEvent.create("Run", run_id, "RunDeleted", {})


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
