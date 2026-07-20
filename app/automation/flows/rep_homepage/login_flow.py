"""대표홈페이지 로그인 Flow (휴대폰 OTP / 카카오)."""

from __future__ import annotations

from app.automation.ports import AutomationContext, Flow
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class LoginFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        steps = runtime.channel.steps
        if runtime.config.auth_method == "kakao":
            steps.login_move.run(ctx.page)
            return StepCompleted(
                steps.kakao_login.run(ctx.page, runtime.config, ctx.dialog_messages)
            )
        if not runtime.phone_login_sms_requested:
            steps.login_move.run(ctx.page)
            message = steps.phone_login.request_sms(ctx.page, runtime.config, ctx.dialog_messages)
            runtime.phone_login_sms_requested = True
            if not runtime.config.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            steps.phone_login.submit_otp_and_login(ctx.page, runtime.config, ctx.dialog_messages)
        )
