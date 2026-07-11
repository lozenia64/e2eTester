"""대표홈페이지 계약 조회 Flow."""

from __future__ import annotations

from app.automation.ports import AutomationContext
from app.runner.step_outcome import StepCompleted, StepOutcome
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class ContractListFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(runtime.channel.steps.contract_list.run(ctx.page, runtime.config))


class ContractDetailFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(runtime.channel.steps.contract_detail.run(ctx.page, runtime.config))
