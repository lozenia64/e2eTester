from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.platform.artifact_manager import ArtifactManager
from app.runner.workflow_engine import StepHandler
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor

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
            closed=base.closed,
            name=(input_data.get("name") or "").strip(),
            ssn_front=(input_data.get("ssn_front") or "").strip(),
            ssn_back=(input_data.get("ssn_back") or "").strip(),
            carrier=(input_data.get("carrier") or "").strip(),
            phone_number=(input_data.get("phone_number") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        return {}

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
