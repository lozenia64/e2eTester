"""실행 정책(Operational Policy) 값 객체 — 매니페스트 선언을 도메인 타입으로 승격한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition, SystemDefinition

ExecutionProfile = Literal["heavy", "light", "interactive"]

_VALID_PROFILES = frozenset({"heavy", "light", "interactive"})
_VALID_RETRYABLE = frozenset(
    {
        ModuleStatus.ERROR.value,
        ModuleStatus.ANOMALY.value,
        ModuleStatus.FAILED.value,
    }
)


@dataclass(frozen=True)
class ModuleExecutionPolicy:
    max_retries: int
    retry_backoff_ms: int
    retryable_on: frozenset[ModuleStatus]
    partial_rerun_allowed: bool

    @property
    def max_attempts(self) -> int:
        return 1 + self.max_retries


@dataclass(frozen=True)
class SystemExecutionPolicy:
    execution_profile: ExecutionProfile
    module_policies: dict[str, ModuleExecutionPolicy]


def _parse_retryable_on(raw_values: list[str]) -> frozenset[ModuleStatus]:
    parsed: set[ModuleStatus] = set()
    for raw in raw_values:
        normalized = raw.strip().upper()
        if normalized not in _VALID_RETRYABLE:
            raise ValueError(f"retryable_on 에 허용되지 않은 상태: {raw}")
        parsed.add(ModuleStatus(normalized))
    return frozenset(parsed)


def module_policy_from_definition(module: ModuleDefinition) -> ModuleExecutionPolicy:
    return ModuleExecutionPolicy(
        max_retries=module.max_retries,
        retry_backoff_ms=module.retry_backoff_ms,
        retryable_on=_parse_retryable_on(module.retryable_on),
        partial_rerun_allowed=module.partial_rerun_allowed,
    )


def system_policy_from_definition(system: SystemDefinition) -> SystemExecutionPolicy:
    profile = system.execution_profile
    if profile not in _VALID_PROFILES:
        raise ValueError(f"execution_profile must be heavy|light|interactive, got {profile!r}")
    return SystemExecutionPolicy(
        execution_profile=profile,  # type: ignore[arg-type]
        module_policies={
            module.module_id: module_policy_from_definition(module) for module in system.modules
        },
    )
