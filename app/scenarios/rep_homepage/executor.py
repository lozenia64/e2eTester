"""대표홈페이지(PC·모바일) 공용 시나리오 실행기.

워크플로(메인접속 → 로그인 → 계약목록 → 계약상세 → 보험금청구 → 결과확인 →
취소 → 장기보험증명서)는 채널과 무관한 *단일 시나리오* 로, 이 한 클래스의
``_run_step`` 에만 존재한다. PC(HOM)·모바일(MHM) 차이는 생성자에 주입되는
``ChannelProfile`` (셀렉터 어댑터 step 묶음 + 모바일 모드 + ``post_login_fragment``)
로만 표현된다.

기존에는 ``HomWorkflowExecutor`` / ``MhmWorkflowExecutor`` 두 클래스가 import 경로,
런타임 클래스명, ``post_login_fragment``, 모바일 모드 한 줄을 빼면 ``_run_step``
디스패치 테이블까지 완전히 동일하게 복제돼 있었다. 그 중복을 이 클래스 하나로
흡수한다.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from app.core.models import ModuleDefinition
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_engine import WAITING_INPUT_PREFIX, BaseWorkflowExecutor
from app.scenarios.rep_homepage.channel import ChannelProfile
from app.scenarios.rep_homepage.runtime import RepHomepageRuntime


class RepHomepageExecutor(BaseWorkflowExecutor):
    """대표홈페이지 채널 한 개를 구동하는 공용 시나리오 실행기."""

    def __init__(self, artifact_manager: ArtifactManager, profile: ChannelProfile) -> None:
        super().__init__(artifact_manager)
        self._profile = profile

    @property
    def execution_mode(self) -> str:
        # 채널 프로파일이 SSOT. 로더/오케스트레이터는 이 값으로 실행기를 매핑한다.
        return self._profile.execution_mode

    def build_runtime(self, input_data: dict[str, str], run_id: str, module_id: str) -> RepHomepageRuntime:
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
            # 스크린샷은 공용 엔진이 모듈 종료 시 책임지므로 워크플로에서는 쓰이지 않는다.
            # build_config 가 요구하는 값만 기본값으로 채운다(LoginConfig.screenshot_path 는 CLI 전용).
            screenshot=str(common.DEFAULT_SCREENSHOT_PATH),
        )
        config = common.build_config(args)
        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        context = common.launch_persistent_browser_context(playwright, config.headless, config.slow_mo)
        page = context.pages[0] if context.pages else context.new_page()
        # 모바일 채널은 페이지 생성 직후, 접속 이전에 모바일 디바이스 모드를 적용한다.
        if profile.mobile:
            common.apply_mobile_device_mode(playwright, page)
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

    def _run_step(self, runtime: RepHomepageRuntime, module: ModuleDefinition, artifact_dir: Path) -> str:
        steps = runtime.channel.steps
        step = module.workflow_step

        if step == "main_access":
            return steps.main_access.run(runtime.page, runtime.config)

        if step == "login":
            if runtime.config.auth_method == "kakao":
                steps.login_move.run(runtime.page)
                return steps.kakao_login.run(
                    runtime.page,
                    runtime.config,
                    runtime.dialog_messages,
                )
            if not runtime.phone_login_sms_requested:
                steps.login_move.run(runtime.page)
                message = steps.phone_login.request_sms(
                    runtime.page,
                    runtime.config,
                    runtime.dialog_messages,
                )
                runtime.phone_login_sms_requested = True
                if not runtime.config.otp_code:
                    return f"{WAITING_INPUT_PREFIX}{message}"
            return steps.phone_login.submit_otp_and_login(
                runtime.page,
                runtime.config,
                runtime.dialog_messages,
            )

        if step == "contract_list":
            return steps.contract_list.run(runtime.page, runtime.config)

        if step == "contract_detail":
            return steps.contract_detail.run(runtime.page, runtime.config)

        if step == "compensation_charge":
            return steps.compensation_charge.run(runtime.page, runtime.config)

        if step == "compensation_result":
            return steps.compensation_result.run(runtime.page, runtime.config)

        if step == "compensation_cancel":
            return steps.compensation_cancel.run(runtime.page, runtime.config)

        if step == "long_term_policy_certificate":
            return steps.long_term_policy_certificate.run(
                runtime.page,
                runtime.config,
                artifact_dir,
                runtime.dialog_messages,
            )

        raise RuntimeError(f"Unsupported {runtime.channel.label} workflow step: {step}")

    def update_otp_code(self, runtime: RepHomepageRuntime, otp_code: str) -> None:
        runtime.config = replace(runtime.config, otp_code=otp_code)
