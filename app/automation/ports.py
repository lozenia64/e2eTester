"""Automation BC ports — Flow dispatch contract for workflow executors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.runner.step_outcome import StepOutcome


@dataclass(frozen=True)
class AutomationContext:
    """Flow 실행에 필요한 능력(capability) 표면.

    ``StepContext`` 와 동일한 정보를 담지만 automation BC 경계에서만 사용한다.
    """

    runtime: object
    page: object
    artifact_dir: Path
    log: Callable[[str], None]
    dialog_messages: list[str]


@runtime_checkable
class Flow(Protocol):
    """단일 workflow_step 을 수행하는 시나리오 흐름."""

    def run(self, ctx: AutomationContext) -> StepOutcome: ...


@runtime_checkable
class AutomationPort(Protocol):
    """실행기가 workflow_step 을 automation BC 로 위임할 때 쓰는 포트."""

    def run_step(self, workflow_step: str, ctx: AutomationContext) -> StepOutcome | None:
        """등록된 Flow 가 있으면 실행하고, 없으면 ``None`` (레거시 레지스트리 폴백)."""
        ...
