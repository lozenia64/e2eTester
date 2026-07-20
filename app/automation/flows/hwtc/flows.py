"""HWTC 시스템 Flow."""

from __future__ import annotations

from app.automation.page_objects.hwtc import phone_auth, video_playback
from app.automation.ports import AutomationContext, Flow
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome


class HwtcMainAccessFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        return StepCompleted(phone_auth.run_main_access(runtime.page, runtime.base_url))


class HwtcPhoneAuthFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        if not runtime.user_id or not runtime.password:
            raise RuntimeError("아이디와 비밀번호를 입력해 주세요.")
        if not runtime.phone_auth_sms_requested:
            message = phone_auth.request_sms(
                runtime.page,
                user_id=runtime.user_id,
                password=runtime.password,
                base_url=runtime.base_url,
                dialog_messages=runtime.dialog_messages,
            )
            runtime.phone_auth_sms_requested = True
            if not runtime.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            phone_auth.submit_otp_and_login(
                runtime.page,
                otp_code=runtime.otp_code,
                dialog_messages=runtime.dialog_messages,
            )
        )


class HwtcVideoPlaybackFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        return StepCompleted(video_playback.run(runtime.page, base_url=runtime.base_url))
