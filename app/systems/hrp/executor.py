from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_engine import WAITING_INPUT_PREFIX
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor
from app.systems.hrp.steps import login

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
            executor=base.executor,
            closed=base.closed,
            user_id=(input_data.get("user_id") or "").strip(),
            password=(input_data.get("password") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

    def _run_step(self, runtime: HrpRuntime, module: ModuleDefinition, artifact_dir: Path) -> str:
        if module.workflow_step == "login":
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
                    return f"{WAITING_INPUT_PREFIX}{message}"
            return login.submit_otp_and_login(
                runtime.page,
                otp_code=runtime.otp_code,
                dialog_messages=runtime.dialog_messages,
            )
        return super()._run_step(runtime, module, artifact_dir)

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
