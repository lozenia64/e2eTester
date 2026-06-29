"""대표홈페이지(PC·모바일) 공용 시나리오 실행기.

워크플로(메인접속 → 로그인 → 계약목록 → 계약상세 → 보험금청구 → 결과확인 →
취소 → 장기보험증명서)는 채널과 무관한 *단일 시나리오* 로, 이 한 클래스의
단계 핸들러(``build_step_registry``)에만 존재한다. PC(HOM)·모바일(MHM) 차이는 생성자에
주입되는 ``ChannelProfile`` (셀렉터 어댑터 step 묶음 + 모바일 모드 + ``post_login_fragment``)
로만 표현된다.

기존에는 ``HomWorkflowExecutor`` / ``MhmWorkflowExecutor`` 두 클래스가 import 경로,
런타임 클래스명, ``post_login_fragment``, 모바일 모드 한 줄을 빼면 단계 디스패치
테이블까지 완전히 동일하게 복제돼 있었다. 그 중복을 이 클래스 하나로 흡수한다.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import replace

from app.runner.artifact_manager import ArtifactManager
from app.runner.step_outcome import StepCompleted, StepNeedsInput, StepOutcome
from app.runner.workflow_engine import BaseWorkflowExecutor, StepContext, StepHandler
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
            # 스크린샷은 공용 엔진이 모듈 종료 시 책임지므로 워크플로에서는 쓰이지 않는다.
            # build_config 가 요구하는 값만 기본값으로 채운다(LoginConfig.screenshot_path 는 CLI 전용).
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
        # 모바일 채널은 페이지 생성 직후, 접속 이전에 모바일 디바이스 모드를 적용한다.
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
        # 워크플로 단계 → 핸들러. 채널(PC/모바일) 차이는 runtime.channel.steps 어댑터로만
        # 표현되므로, 디스패치 테이블 자체는 채널 무관하게 단 한 벌만 존재한다.
        return {
            "main_access": self._step_main_access,
            "login": self._step_login,
            "contract_list": self._step_contract_list,
            "contract_detail": self._step_contract_detail,
            "compensation_charge": self._step_compensation_charge,
            "compensation_result": self._step_compensation_result,
            "compensation_cancel": self._step_compensation_cancel,
            "long_term_policy_certificate": self._step_long_term_policy_certificate,
        }

    def _step_main_access(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(runtime.channel.steps.main_access.run(ctx.page, runtime.config))

    def _step_login(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        steps = runtime.channel.steps
        if runtime.config.auth_method == "kakao":
            steps.login_move.run(ctx.page)
            return StepCompleted(
                steps.kakao_login.run(ctx.page, runtime.config, ctx.dialog_messages)
            )
        if not runtime.phone_login_sms_requested:
            steps.login_move.run(ctx.page)
            message = steps.phone_login.request_sms(ctx.page, runtime.config, ctx.dialog_messages)
            runtime.phone_login_sms_requested = True
            if not runtime.config.otp_code:
                return StepNeedsInput(message)
        return StepCompleted(
            steps.phone_login.submit_otp_and_login(ctx.page, runtime.config, ctx.dialog_messages)
        )

    def _step_contract_list(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(runtime.channel.steps.contract_list.run(ctx.page, runtime.config))

    def _step_contract_detail(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(runtime.channel.steps.contract_detail.run(ctx.page, runtime.config))

    def _step_compensation_charge(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.compensation_charge.run(ctx.page, runtime.config)
        )

    def _step_compensation_result(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.compensation_result.run(ctx.page, runtime.config)
        )

    def _step_compensation_cancel(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.compensation_cancel.run(ctx.page, runtime.config)
        )

    def _step_long_term_policy_certificate(self, ctx: StepContext) -> StepOutcome:
        runtime: RepHomepageRuntime = ctx.runtime  # type: ignore[assignment]
        return StepCompleted(
            runtime.channel.steps.long_term_policy_certificate.run(
                ctx.page,
                runtime.config,
                ctx.artifact_dir,
                ctx.dialog_messages,
            )
        )

    def update_otp_code(self, runtime: RepHomepageRuntime, otp_code: str) -> None:
        runtime.config = replace(runtime.config, otp_code=otp_code)
