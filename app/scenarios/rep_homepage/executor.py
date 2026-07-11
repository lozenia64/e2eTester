"""대표홈페이지(PC·모바일) 공용 시나리오 실행기.

워크플로 단계 디스패치는 automation BC ``ScenarioEngine``(Flow)이 담당한다.
이 실행기는 런타임 기동·OTP 반영·브라우저 종료만 소유한다.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import replace

from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_engine import BaseWorkflowExecutor, StepHandler
from app.scenarios.rep_homepage.channel import ChannelProfile
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class RepHomepageExecutor(BaseWorkflowExecutor):
    """대표홈페이지 채널 한 개를 구동하는 공용 시나리오 실행기."""

    def __init__(self, artifact_manager: ArtifactManager, profile: ChannelProfile) -> None:
        super().__init__(artifact_manager)
        self._profile = profile

    @property
    def execution_mode(self) -> str:
        return self._profile.execution_mode

    def build_runtime(
        self, input_data: dict[str, str], run_id: str, module_id: str
    ) -> RepHomepageRuntime:
        profile = self._profile
        common = profile.common
        headless = self._resolve_headless(input_data)
        args = argparse.Namespace(
            env_file=str(common.DEFAULT_ENV_FILE_PATH),
            auth_method=(input_data.get("auth_method") or "phone").strip().lower(),
            base_url=input_data.get("base_url") or common.DEFAULT_BASE_URL,
            name=input_data.get("name"),
            birthdate=input_data.get("birthdate"),
            gender=input_data.get("gender"),
            residency=input_data.get("residency"),
            carrier=input_data.get("carrier"),
            phone_number=input_data.get("phone_number"),
            phone_prefix=input_data.get("phone_prefix"),
            otp_code=input_data.get("otp_code"),
            headless=headless,
            slow_mo=250 if not headless else 0,
            timeout_ms=common.MAX_TIMEOUT_MS,
            success_stabilization_ms=common.MAX_TIMEOUT_MS,
            keep_open=False,
            post_login_fragment=profile.post_login_fragment,
            screenshot=str(common.DEFAULT_SCREENSHOT_PATH),
        )
        config = common.build_config(args)
        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        context = common.launch_persistent_browser_context(
            playwright, config.headless, config.slow_mo
        )
        page = context.pages[0] if context.pages else context.new_page()
        if profile.mobile:
            common.apply_mobile_device_mode(playwright, page)
        else:
            common.grant_browser_permissions(context, config.base_url)
        page.set_default_timeout(config.timeout_ms)
        page.set_default_navigation_timeout(config.timeout_ms)
        dialog_messages = common.add_dialog_logger(page)
        return RepHomepageRuntime(
            channel=profile,
            config=config,
            playwright_manager=playwright_manager,
            browser=None,
            context=context,
            page=page,
            dialog_messages=dialog_messages,
        )

    def _shutdown_browser(self, runtime: RepHomepageRuntime) -> None:
        runtime.channel.common.shutdown_browser(runtime.page, runtime.context, runtime.browser)

    def build_step_registry(self) -> Mapping[str, StepHandler]:
        # 단계 실행은 automation BC Flow 가 담당 — 레거시 폴백용 빈 레지스트리.
        return {}

    def update_otp_code(self, runtime: RepHomepageRuntime, otp_code: str) -> None:
        runtime.config = replace(runtime.config, otp_code=otp_code)
