"""Scenario engine — workflow_step → Flow 디스패치."""

from __future__ import annotations

from collections.abc import Mapping

from app.automation.ports import AutomationContext, AutomationPort, Flow
from app.runner.step_outcome import StepOutcome


class ScenarioEngine:
    """workflow_step 이름으로 Flow 를 조회·실행하는 automation 디스패처."""

    def __init__(self, flows: Mapping[str, Flow] | None = None) -> None:
        self._flows: dict[str, Flow] = dict(flows or {})

    def register(self, workflow_step: str, flow: Flow) -> None:
        self._flows[workflow_step] = flow

    def has_flow(self, workflow_step: str) -> bool:
        return workflow_step in self._flows

    def run_step(self, workflow_step: str, ctx: AutomationContext) -> StepOutcome | None:
        flow = self._flows.get(workflow_step)
        if flow is None:
            return None
        return flow.run(ctx)


def as_automation_port(engine: ScenarioEngine) -> AutomationPort:
    """ScenarioEngine 을 AutomationPort 로 노출한다(구조적 타이핑)."""
    return engine
