from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.runner.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_engine import StepContext, StepHandler
from app.systems.access_common import browser
from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor
from app.systems.hwtc.steps import phone_auth, video_playback

DEFAULT_BASE_URL = "https://sls.hwgeneralins.com"


@dataclass
class HwtcRuntime(AccessRuntime):
    user_id: str = ""
    password: str = ""
    otp_code: str = ""
    phone_auth_sms_requested: bool = False


class HwtcWorkflowExecutor(AccessWorkflowExecutor):
    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> HwtcRuntime:
        headless = self._resolve_headless(input_data)
        base_url = browser.normalize_base_url(input_data.get("base_url"), self._base_url)

        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        context = browser.launch_standard_browser_context(playwright, headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(browser.MAX_TIMEOUT_MS)
        page.set_default_navigation_timeout(browser.MAX_TIMEOUT_MS)
        dialog_messages = browser.add_dialog_logger(page)
        return HwtcRuntime(
            base_url=base_url,
            mobile=self._mobile,
            playwright_manager=playwright_manager,
            context=context,
            page=page,
            dialog_messages=dialog_messages,
            user_id=(input_data.get("user_id") or "").strip(),
            password=(input_data.get("password") or "").strip(),
            otp_code=(input_data.get("otp_code") or "").strip(),
        )

    def _shutdown_browser(self, runtime: HwtcRuntime) -> None:
        browser.shutdown_browser(runtime.page, runtime.context)

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        # main_access 는 부모(접속 점검)와 달리 phone_auth 모듈의 진입 화면이라 덮어쓴다.
        return {
            **super().build_step_registry(),
            "main_access": self._step_main_access,
            "phone_auth": self._step_phone_auth,
            "video_playback": self._step_video_playback,
        }

    def _step_main_access(self, ctx: StepContext) -> StepOutcome:
        runtime: HwtcRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(phone_auth.run_main_access(runtime.page, runtime.base_url))

    def _step_phone_auth(self, ctx: StepContext) -> StepOutcome:
        runtime: HwtcRuntime = ctx.runtime  # type: ignore[assignment]
        if not runtime.user_id or not runtime.password:
            raise RuntimeError("아이디와 비밀번호를 입력해 주세요.")
        if not runtime.phone_auth_sms_requested:
            message = phone_auth.request_sms(
                runtime.page,
                user_id=runtime.user_id,
                password=runtime.password,
                base_url=runtime.base_url,
                dialog_messages=runtime.dialog_messages,
            )
            runtime.phone_auth_sms_requested = True
            if not runtime.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            phone_auth.submit_otp_and_login(
                runtime.page,
                otp_code=runtime.otp_code,
                dialog_messages=runtime.dialog_messages,
            )
        )

    def _step_video_playback(self, ctx: StepContext) -> StepOutcome:
        runtime: HwtcRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(video_playback.run(runtime.page, base_url=runtime.base_url))

    def update_otp_code(self, runtime: HwtcRuntime, otp_code: str) -> None:
        runtime.otp_code = otp_code.strip()


def create_executor(artifact_manager: ArtifactManager) -> HwtcWorkflowExecutor:
    return HwtcWorkflowExecutor(
        artifact_manager,
        execution_mode="hwtc_workflow_step",
        system_code="hwtc",
        base_url=DEFAULT_BASE_URL,
        mobile=False,
    )
