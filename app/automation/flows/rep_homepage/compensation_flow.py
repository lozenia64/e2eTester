"""대표홈페이지 보험금청구·증명서 Flow."""

from __future__ import annotations

from app.automation.ports import AutomationContext
from app.runner.step_outcome import StepCompleted, StepOutcome
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class CompensationChargeFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.compensation_charge.run(ctx.page, runtime.config)
        )


class CompensationResultFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.compensation_result.run(ctx.page, runtime.config)
        )


class CompensationCancelFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.compensation_cancel.run(ctx.page, runtime.config)
        )


class LongTermPolicyCertificateFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.long_term_policy_certificate.run(
                ctx.page,
                runtime.config,
                ctx.artifact_dir,
                ctx.dialog_messages,
            )
        )
