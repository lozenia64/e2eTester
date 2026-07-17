"""HRP 시스템 Flow."""

from __future__ import annotations

from app.automation.page_objects.hrp import (
    login,
    salvage_bid_inquiry_detail,
    salvage_bid_inquiry_list,
)
from app.automation.ports import AutomationContext, Flow
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome


class HrpLoginFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        if not runtime.user_id or not runtime.password:
            raise RuntimeError("아이디와 비밀번호를 입력해 주세요.")
        if not runtime.login_otp_requested:
            message = login.request_otp(
                runtime.page,
                user_id=runtime.user_id,
                password=runtime.password,
                base_url=runtime.base_url,
            )
            runtime.login_otp_requested = True
            if not runtime.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            login.submit_otp_and_login(
                runtime.page,
                otp_code=runtime.otp_code,
                dialog_messages=runtime.dialog_messages,
            )
        )


class HrpSalvageBidListFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        return StepCompleted(salvage_bid_inquiry_list.run(runtime.page, base_url=runtime.base_url))


class HrpSalvageBidDetailFlow(Flow):
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        return StepCompleted(
            salvage_bid_inquiry_detail.run(runtime.page, base_url=runtime.base_url)
        )
