from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.runner.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_engine import StepContext, StepHandler
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor
from app.systems.hrp.steps import login, salvage_bid_inquiry_detail, salvage_bid_inquiry_list

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
        return {
            **super().build_step_registry(),
            "login": self._step_login,
            "salvage_bid_inquiry_list": self._step_salvage_bid_inquiry_list,
            "salvage_bid_inquiry_detail": self._step_salvage_bid_inquiry_detail,
        }

    def _step_login(self, ctx: StepContext) -> StepOutcome:
        runtime: HrpRuntime = ctx.runtime  # type: ignore[assignment]
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

    def _step_salvage_bid_inquiry_list(self, ctx: StepContext) -> StepOutcome:
        runtime: HrpRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(salvage_bid_inquiry_list.run(runtime.page, base_url=runtime.base_url))

    def _step_salvage_bid_inquiry_detail(self, ctx: StepContext) -> StepOutcome:
        runtime: HrpRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            salvage_bid_inquiry_detail.run(runtime.page, base_url=runtime.base_url)
        )

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
