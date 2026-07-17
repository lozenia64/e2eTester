"""대표홈페이지 메인 접속 Flow."""

from __future__ import annotations

from app.automation.ports import AutomationContext, Flow
from app.runner.step_outcome import StepCompleted, StepOutcome
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class MainAccessFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        steps = runtime.channel.steps
        return StepCompleted(steps.main_access.run(ctx.page, runtime.config))
