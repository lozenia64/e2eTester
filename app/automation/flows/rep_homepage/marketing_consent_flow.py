"""대표홈페이지 마케팅동의 Flow."""

from __future__ import annotations

from app.automation.ports import AutomationContext, Flow
from app.runner.step_outcome import StepCompleted, StepOutcome
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class MarketingConsentApplyFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.marketing_consent_apply.run(
                ctx.page,
                runtime.config,
                ctx.dialog_messages,
            )
        )


class MarketingConsentWithdrawFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.marketing_consent_withdraw.run(
                ctx.page,
                runtime.config,
                ctx.dialog_messages,
            )
        )
