from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.runner.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_engine import StepContext, StepHandler
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor
from app.systems.fp.steps import document_writing, identity_verification

DEFAULT_BASE_URL = "https://fp.hwgeneralins.com"


@dataclass
class FpRuntime(AccessRuntime):
    name: str = ""
    ssn_front: str = ""
    ssn_back: str = ""
    carrier: str = ""
    phone_number: str = ""
    otp_code: str = ""
    phone_auth_sms_requested: bool = False
    document_sms_requested: bool = False


class FpWorkflowExecutor(AccessWorkflowExecutor):
    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> FpRuntime:
        base = super().build_runtime(input_data, run_id, module_id)
        return FpRuntime(
            base_url=base.base_url,
            mobile=base.mobile,
            playwright_manager=base.playwright_manager,
            context=base.context,
            page=base.page,
            dialog_messages=base.dialog_messages,
            executor=base.executor,
            closed=base.closed,
            name=(input_data.get("name") or "").strip(),
            ssn_front=(input_data.get("ssn_front") or "").strip(),
            ssn_back=(input_data.get("ssn_back") or "").strip(),
            carrier=(input_data.get("carrier") or "").strip(),
            phone_number=(input_data.get("phone_number") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        return {
            **super().build_step_registry(),
            "identity_verification": self._step_identity_verification,
            "document_writing": self._step_document_writing,
        }

    def _step_identity_verification(self, ctx: StepContext) -> StepOutcome:
        runtime: FpRuntime = ctx.runtime  # type: ignore[assignment]
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

    def _step_document_writing(self, ctx: StepContext) -> StepOutcome:
        runtime: FpRuntime = ctx.runtime  # type: ignore[assignment]
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

    def update_otp_code(self, runtime: FpRuntime, otp_code: str) -> None:
        runtime.otp_code = otp_code.strip()


def create_executor(artifact_manager: ArtifactManager) -> FpWorkflowExecutor:
    return FpWorkflowExecutor(
        artifact_manager,
        execution_mode="fp_workflow_step",
        system_code="fp",
        base_url=DEFAULT_BASE_URL,
        mobile=False,
    )
