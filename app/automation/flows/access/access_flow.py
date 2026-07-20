"""접속 점검 공용 main_access Flow."""

from __future__ import annotations

from app.automation.ports import AutomationContext, Flow
from app.runner.step_outcome import StepCompleted, StepOutcome
from app.systems.access_common import main_access
from app.systems.access_common.executor import AccessRuntime


class AccessMainFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: AccessRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(main_access.run(ctx.page, runtime.base_url))
