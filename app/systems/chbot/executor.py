from __future__ import annotations

from dataclasses import dataclass

from app.platform.artifact_manager import ArtifactManager
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor

DEFAULT_BASE_URL = "https://chbot.hwgeneralins.com/P29GCdKMTnbsy0PRr"


@dataclass
class ChbotRuntime(AccessRuntime):
    auth_method: str = "phone"
    name: str = ""
    birthdate: str = ""
    gender_code: str = ""
    carrier: str = ""
    phone_number: str = ""
    otp_code: str = ""
    simple_auth_sms_requested: bool = False


class ChbotWorkflowExecutor(AccessWorkflowExecutor):
    def build_runtime(
        self,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
        storage_state: str | None = None,
    ) -> ChbotRuntime:
        runtime = super().build_runtime(input_data, run_id, module_id, storage_state)
        return ChbotRuntime(
            base_url=runtime.base_url,
            mobile=runtime.mobile,
            playwright_manager=runtime.playwright_manager,
            context=runtime.context,
            page=runtime.page,
            dialog_messages=runtime.dialog_messages,
            closed=runtime.closed,
            auth_method=(input_data.get("auth_method") or "phone").strip().lower(),
            name=(input_data.get("name") or "").strip(),
            birthdate=(input_data.get("birthdate") or "").strip(),
            gender_code=(input_data.get("gender_code") or "").strip(),
            carrier=(input_data.get("carrier") or "").strip(),
            phone_number=(input_data.get("phone_number") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

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
