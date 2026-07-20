"""Run 도메인 이벤트 — 판별 유니온 + 이벤트 레코드."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

from app.contexts.run.contracts.records import RunModuleRecord
from app.core.enums import ModuleStatus, RunStatus


class RunSummaryWire(TypedDict):
    """``run_summary_fields`` 가 만드는 fat-event 요약(dict 키 고정)."""

    system_code: str
    system_name: str
    status: str
    requested_at: str
    started_at: str | None
    ended_at: str | None
    awaiting_input_module_id: str | None
    awaiting_input_prompt: str | None
    module_total: int
    module_defined_total: int
    module_skipped: int
    module_passed: int
    current_module_name: str | None
    failed_module_name: str | None
    triggered_by: str
    schedule_id: str | None
    suite_id: str | None
    created_by_user_id: str | None
    created_by_user_name: str | None
    selected_module_ids: list[str]
    comparison: dict[str, Any] | None


@dataclass(frozen=True)
class RunCreated:
    system_code: str
    triggered_by: str
    all_modules: list[RunModuleRecord] = field(default_factory=list)


@dataclass(frozen=True)
class RunStarted:
    pass


@dataclass(frozen=True)
class ModuleQueued:
    module_id: str
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class ModuleStarted:
    module_id: str
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class ModuleFinished:
    module_id: str
    status: ModuleStatus
    system_code: str
    schedule_id: str | None
    suite_id: str | None
    module_name: str | None = None
    message: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    created_by_user_id: str | None = None
    current_url: str | None = None
    artifacts: list[str] = field(default_factory=list)
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class RunWaitingInput:
    module_id: str
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class RunResumed:
    module_id: str
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class RunFinished:
    status: RunStatus
    system_code: str
    schedule_id: str | None
    suite_id: str | None
    requested_at: datetime
    ended_at: datetime | None
    created_by_user_id: str | None


@dataclass(frozen=True)
class RunModuleBlocked:
    module_id: str
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class RunModulesCancelled:
    module_ids: list[str]
    modules: list[RunModuleRecord] = field(default_factory=list)


@dataclass(frozen=True)
class RunComparisonAttached:
    baseline_run_id: str | None
    newly_failed: list[str] = field(default_factory=list)
    recovered: list[str] = field(default_factory=list)
    still_failing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunSealedInterrupted:
    all_modules: list[RunModuleRecord] = field(default_factory=list)


@dataclass(frozen=True)
class RunModuleRetried:
    module_id: str
    attempt: int
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class RunPartialRerunStarted:
    from_module_id: str
    all_modules: list[RunModuleRecord] = field(default_factory=list)


@dataclass(frozen=True)
class ModuleFailureAnalysisAttached:
    module_id: str
    category: str | None = None
    user_summary: str | None = None
    recommended_action: str | None = None
    module: RunModuleRecord | None = None


@dataclass(frozen=True)
class RunImported:
    run_summary: RunSummaryWire
    all_modules: list[RunModuleRecord]


@dataclass(frozen=True)
class RunDeleted:
    pass


RunEvent = (
    RunCreated
    | RunStarted
    | ModuleQueued
    | ModuleStarted
    | ModuleFinished
    | RunWaitingInput
    | RunResumed
    | RunFinished
    | RunModuleBlocked
    | RunModulesCancelled
    | RunComparisonAttached
    | RunSealedInterrupted
    | RunModuleRetried
    | RunPartialRerunStarted
    | ModuleFailureAnalysisAttached
    | RunImported
    | RunDeleted
)


@dataclass(frozen=True)
class RunEventRecord:
    event: RunEvent
    run_summary: RunSummaryWire
    event_id: str
    occurred_at: datetime
    version: int = 1
