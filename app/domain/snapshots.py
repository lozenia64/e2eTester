"""도메인 애그리거트의 불변 읽기 스냅샷."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.run_models import FailureAnalysis, Run, RunComparison, RunModule
from app.core.suite_models import SuiteRun, SuiteStep


@dataclass(frozen=True)
class ModuleSnapshot:
    module_id: str
    name: str
    group: str
    order: int
    status: ModuleStatus
    depends_on: tuple[str, ...]
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    retry_count: int
    attempt: int
    max_attempts: int
    message: str
    artifact_count: int
    artifacts: tuple[str, ...]
    logs: tuple[str, ...]
    current_url: str | None
    dialog_messages: tuple[str, ...]
    recovered: bool
    recovery_tiers: tuple[int, ...]
    failure_signals: tuple[str, ...]
    failure_analysis: FailureAnalysis | None

    @classmethod
    def from_module(cls, module: RunModule) -> ModuleSnapshot:
        copied = module.model_copy(deep=True)
        return cls(
            module_id=copied.module_id,
            name=copied.name,
            group=copied.group,
            order=copied.order,
            status=copied.status,
            depends_on=tuple(copied.depends_on),
            started_at=copied.started_at,
            ended_at=copied.ended_at,
            duration_ms=copied.duration_ms,
            retry_count=copied.retry_count,
            attempt=copied.attempt,
            max_attempts=copied.max_attempts,
            message=copied.message,
            artifact_count=copied.artifact_count,
            artifacts=tuple(copied.artifacts),
            logs=tuple(copied.logs),
            current_url=copied.current_url,
            dialog_messages=tuple(copied.dialog_messages),
            recovered=copied.recovered,
            recovery_tiers=tuple(copied.recovery_tiers),
            failure_signals=tuple(copied.failure_signals),
            failure_analysis=copied.failure_analysis,
        )


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    modules: tuple[ModuleSnapshot, ...]
    selected_module_ids: tuple[str, ...]
    awaiting_input_module_id: str | None
    awaiting_input_prompt: str | None
    triggered_by: str
    schedule_id: str | None
    suite_id: str | None
    comparison: RunComparison | None
    created_by_user_id: str | None
    created_by_user_name: str | None

    @classmethod
    def from_run(cls, run: Run) -> RunSnapshot:
        copied = run.model_copy(deep=True)
        return cls(
            run_id=copied.run_id,
            system_code=copied.system_code,
            system_name=copied.system_name,
            status=copied.status,
            requested_at=copied.requested_at,
            started_at=copied.started_at,
            ended_at=copied.ended_at,
            modules=tuple(ModuleSnapshot.from_module(m) for m in copied.modules),
            selected_module_ids=tuple(copied.selected_module_ids),
            awaiting_input_module_id=copied.awaiting_input_module_id,
            awaiting_input_prompt=copied.awaiting_input_prompt,
            triggered_by=copied.triggered_by,
            schedule_id=copied.schedule_id,
            suite_id=copied.suite_id,
            comparison=copied.comparison,
            created_by_user_id=copied.created_by_user_id,
            created_by_user_name=copied.created_by_user_name,
        )

    def to_run(self) -> Run:
        return Run(
            run_id=self.run_id,
            system_code=self.system_code,
            system_name=self.system_name,
            status=self.status,
            requested_at=self.requested_at,
            started_at=self.started_at,
            ended_at=self.ended_at,
            modules=[_module_snapshot_to_run_module(m) for m in self.modules],
            selected_module_ids=list(self.selected_module_ids),
            awaiting_input_module_id=self.awaiting_input_module_id,
            awaiting_input_prompt=self.awaiting_input_prompt,
            triggered_by=self.triggered_by,
            schedule_id=self.schedule_id,
            suite_id=self.suite_id,
            comparison=self.comparison,
            created_by_user_id=self.created_by_user_id,
            created_by_user_name=self.created_by_user_name,
        )


@dataclass(frozen=True)
class SuiteStepSnapshot:
    system_code: str
    system_name: str
    order: int
    run_id: str | None
    status: SuiteStatus
    module_total: int

    @classmethod
    def from_step(cls, step: SuiteStep) -> SuiteStepSnapshot:
        copied = step.model_copy(deep=True)
        return cls(
            system_code=copied.system_code,
            system_name=copied.system_name,
            order=copied.order,
            run_id=copied.run_id,
            status=copied.status,
            module_total=copied.module_total,
        )


@dataclass(frozen=True)
class SuiteSnapshot:
    suite_id: str
    status: SuiteStatus
    steps: tuple[SuiteStepSnapshot, ...]
    current_step_index: int
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    active_run_id: str | None
    awaiting_input_run_id: str | None
    awaiting_input_prompt: str | None
    browser_mode: str
    selected_system_codes: tuple[str, ...]
    created_by_user_id: str | None
    created_by_user_name: str | None
    triggered_by: str
    schedule_id: str | None

    @classmethod
    def from_suite(cls, suite: SuiteRun) -> SuiteSnapshot:
        copied = suite.model_copy(deep=True)
        return cls(
            suite_id=copied.suite_id,
            status=copied.status,
            steps=tuple(SuiteStepSnapshot.from_step(s) for s in copied.steps),
            current_step_index=copied.current_step_index,
            requested_at=copied.requested_at,
            started_at=copied.started_at,
            ended_at=copied.ended_at,
            active_run_id=copied.active_run_id,
            awaiting_input_run_id=copied.awaiting_input_run_id,
            awaiting_input_prompt=copied.awaiting_input_prompt,
            browser_mode=copied.browser_mode,
            selected_system_codes=tuple(copied.selected_system_codes),
            created_by_user_id=copied.created_by_user_id,
            created_by_user_name=copied.created_by_user_name,
            triggered_by=copied.triggered_by,
            schedule_id=copied.schedule_id,
        )

    def to_suite(self) -> SuiteRun:
        return SuiteRun(
            suite_id=self.suite_id,
            status=self.status,
            steps=[_step_snapshot_to_suite_step(s) for s in self.steps],
            current_step_index=self.current_step_index,
            requested_at=self.requested_at,
            started_at=self.started_at,
            ended_at=self.ended_at,
            active_run_id=self.active_run_id,
            awaiting_input_run_id=self.awaiting_input_run_id,
            awaiting_input_prompt=self.awaiting_input_prompt,
            browser_mode=self.browser_mode,
            selected_system_codes=list(self.selected_system_codes),
            created_by_user_id=self.created_by_user_id,
            created_by_user_name=self.created_by_user_name,
            triggered_by=self.triggered_by,
            schedule_id=self.schedule_id,
        )


def _module_snapshot_to_run_module(module: ModuleSnapshot) -> RunModule:
    return RunModule(
        module_id=module.module_id,
        name=module.name,
        group=module.group,
        order=module.order,
        status=module.status,
        depends_on=list(module.depends_on),
        started_at=module.started_at,
        ended_at=module.ended_at,
        duration_ms=module.duration_ms,
        retry_count=module.retry_count,
        attempt=module.attempt,
        max_attempts=module.max_attempts,
        message=module.message,
        artifact_count=module.artifact_count,
        artifacts=list(module.artifacts),
        logs=list(module.logs),
        current_url=module.current_url,
        dialog_messages=list(module.dialog_messages),
        recovered=module.recovered,
        recovery_tiers=list(module.recovery_tiers),
        failure_signals=list(module.failure_signals),
        failure_analysis=module.failure_analysis,
    )


def _step_snapshot_to_suite_step(step: SuiteStepSnapshot) -> SuiteStep:
    return SuiteStep(
        system_code=step.system_code,
        system_name=step.system_name,
        order=step.order,
        run_id=step.run_id,
        status=step.status,
        module_total=step.module_total,
    )
