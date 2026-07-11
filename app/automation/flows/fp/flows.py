"""FP 시스템 Flow."""

from __future__ import annotations

from app.automation.page_objects.fp import document_writing, identity_verification
from app.automation.ports import AutomationContext
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome


class FpIdentityVerificationFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        if not runtime.phone_auth_sms_requested:
            message = identity_verification.request_otp(
                runtime.page,
                base_url=runtime.base_url,
                name=runtime.name,
                ssn_front=runtime.ssn_front,
                ssn_back=runtime.ssn_back,
                carrier=runtime.carrier,
                phone_number=runtime.phone_number,
                dialog_messages=runtime.dialog_messages,
            )
            runtime.phone_auth_sms_requested = True
            if not runtime.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            identity_verification.submit_otp_and_complete(
                runtime.page,
                otp_code=runtime.otp_code,
                dialog_messages=runtime.dialog_messages,
            )
        )


class FpDocumentWritingFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        if not runtime.document_sms_requested:
            runtime.otp_code = ""
            message = document_writing.request_otp(
                runtime.page,
                base_url=runtime.base_url,
                dialog_messages=runtime.dialog_messages,
            )
            runtime.document_sms_requested = True
            if not runtime.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            document_writing.submit_otp_and_complete(
                runtime.page,
                otp_code=runtime.otp_code,
                dialog_messages=runtime.dialog_messages,
            )
        )
