"""CHBOT 시스템 Flow."""

from __future__ import annotations

from app.automation.page_objects.chbot import contract_list, kakao_auth, simple_auth
from app.automation.ports import AutomationContext
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome


class ChbotSimpleAuthFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        if not runtime.name or not runtime.birthdate or not runtime.gender_code:
            raise RuntimeError("성명, 생년월일, 성별코드를 입력해 주세요.")

        auth_method = (getattr(runtime, "auth_method", None) or "phone").strip().lower()
        if auth_method == "kakao":
            if not runtime.phone_number:
                raise RuntimeError("휴대폰 번호를 입력해 주세요.")
            return StepCompleted(
                kakao_auth.run(
                    runtime.page,
                    name=runtime.name,
                    birthdate=runtime.birthdate,
                    gender_code=runtime.gender_code,
                    phone_number=runtime.phone_number,
                )
            )

        if not runtime.carrier or not runtime.phone_number:
            raise RuntimeError("통신사와 휴대폰 번호를 입력해 주세요.")
        if not runtime.simple_auth_sms_requested:
            message = simple_auth.request_otp(
                runtime.page,
                name=runtime.name,
                birthdate=runtime.birthdate,
                gender_code=runtime.gender_code,
                carrier=runtime.carrier,
                phone_number=runtime.phone_number,
            )
            runtime.simple_auth_sms_requested = True
            if not runtime.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            simple_auth.submit_otp_and_verify(runtime.page, otp_code=runtime.otp_code)
        )


class ChbotContractListFlow:
    def run(self, ctx: AutomationContext) -> StepOutcome:
        runtime = ctx.runtime
        return StepCompleted(contract_list.run(runtime.page))
