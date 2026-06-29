from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.runner.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_engine import StepContext, StepHandler
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor
from app.systems.chbot.steps import contract_list, simple_auth

DEFAULT_BASE_URL = "https://chbot.hwgeneralins.com/P29GCdKMTnbsy0PRr"


@dataclass
class ChbotRuntime(AccessRuntime):
    name: str = ""
    birthdate: str = ""
    gender_code: str = ""
    carrier: str = ""
    phone_number: str = ""
    otp_code: str = ""
    simple_auth_sms_requested: bool = False


class ChbotWorkflowExecutor(AccessWorkflowExecutor):
    def build_runtime(
        self, input_data: dict[str, str], run_id: str, module_id: str
    ) -> ChbotRuntime:
        runtime = super().build_runtime(input_data, run_id, module_id)
        return ChbotRuntime(
            base_url=runtime.base_url,
            mobile=runtime.mobile,
            playwright_manager=runtime.playwright_manager,
            context=runtime.context,
            page=runtime.page,
            dialog_messages=runtime.dialog_messages,
            closed=runtime.closed,
            name=(input_data.get("name") or "").strip(),
            birthdate=(input_data.get("birthdate") or "").strip(),
            gender_code=(input_data.get("gender_code") or "").strip(),
            carrier=(input_data.get("carrier") or "").strip(),
            phone_number=(input_data.get("phone_number") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        return {
            **super().build_step_registry(),
            "simple_auth": self._step_simple_auth,
            "contract_list": self._step_contract_list,
        }

    def _step_simple_auth(self, ctx: StepContext) -> StepOutcome:
        runtime: ChbotRuntime = ctx.runtime  # type: ignore[assignment]
        if not runtime.name or not runtime.birthdate or not runtime.gender_code:
            raise RuntimeError("성명, 생년월일, 성별코드를 입력해 주세요.")
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

    def _step_contract_list(self, ctx: StepContext) -> StepOutcome:
        runtime: ChbotRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(contract_list.run(runtime.page))

    def update_otp_code(self, runtime: ChbotRuntime, otp_code: str) -> None:
        runtime.otp_code = otp_code.strip()


def create_executor(artifact_manager: ArtifactManager) -> ChbotWorkflowExecutor:
    return ChbotWorkflowExecutor(
        artifact_manager,
        execution_mode="chbot_workflow_step",
        system_code="chbot",
        base_url=DEFAULT_BASE_URL,
        mobile=True,
    )
