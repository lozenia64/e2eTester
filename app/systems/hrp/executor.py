from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.platform.artifact_manager import ArtifactManager
from app.runner.workflow_engine import StepHandler
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor

DEFAULT_BASE_URL = "https://www.eagleprm.co.kr"


@dataclass
class HrpRuntime(AccessRuntime):
    user_id: str = ""
    password: str = ""
    otp_code: str = ""
    login_otp_requested: bool = False


class HrpWorkflowExecutor(AccessWorkflowExecutor):
    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> HrpRuntime:
        base = super().build_runtime(input_data, run_id, module_id)
        return HrpRuntime(
            base_url=base.base_url,
            mobile=base.mobile,
            playwright_manager=base.playwright_manager,
            context=base.context,
            page=base.page,
            dialog_messages=base.dialog_messages,
            closed=base.closed,
            user_id=(input_data.get("user_id") or "").strip(),
            password=(input_data.get("password") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        return {}

    def update_otp_code(self, runtime: HrpRuntime, otp_code: str) -> None:
        runtime.otp_code = otp_code.strip()


def create_executor(artifact_manager: ArtifactManager) -> HrpWorkflowExecutor:
    return HrpWorkflowExecutor(
        artifact_manager,
        execution_mode="hrp_workflow_step",
        system_code="hrp",
        base_url=DEFAULT_BASE_URL,
        mobile=False,
    )
