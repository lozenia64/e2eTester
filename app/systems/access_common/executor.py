from __future__ import annotations

from dataclasses import dataclass

from app.platform.artifact_manager import ArtifactManager
from app.runner.workflow_engine import BaseWorkflowExecutor
from app.systems.access_common import browser


@dataclass
class AccessRuntime:
    base_url: str
    mobile: bool
    playwright_manager: object
    context: object
    page: object
    dialog_messages: list[str]
    # 실행 스레드 풀은 게이트웨이 세션이 소유한다(런타임은 인프라 필드를 들지 않는다).
    closed: bool = False


class AccessWorkflowExecutor(BaseWorkflowExecutor):
    """메인화면 접속만 점검하는 단순 시스템들의 공용 실행기.

    각 시스템 executor 가 ``execution_mode``·``base_url``·모바일 여부를 주입한다.
    로그인/인증/OTP 단계가 없으므로 절대 ``WAITING_INPUT`` 으로 멈추지 않는다.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        *,
        execution_mode: str,
        system_code: str,
        base_url: str,
        mobile: bool,
    ) -> None:
        super().__init__(artifact_manager)
        self.execution_mode = execution_mode
        self._system_code = system_code
        self._base_url = browser.normalize_base_url(base_url, base_url)
        self._mobile = mobile

    def build_runtime(
        self, input_data: dict[str, str], run_id: str, module_id: str
    ) -> AccessRuntime:
        headless = self._resolve_headless(input_data)
        base_url = browser.normalize_base_url(input_data.get("base_url"), self._base_url)

        from playwright.sync_api import sync_playwright

        playwright_manager = sync_playwright()
        playwright = playwright_manager.__enter__()
        if self._system_code in browser.LEGACY_BROWSER_ACCESS_SYSTEMS:
            slow_mo = 250 if not headless else 0
            user_data_dir = browser.resolve_user_data_dir(f"{self._system_code}-chrome-profile")
            context = browser.launch_legacy_persistent_browser_context(
                playwright, headless, slow_mo, user_data_dir
            )
        else:
            context = browser.launch_standard_browser_context(playwright, headless)
        page = context.pages[0] if context.pages else context.new_page()
        if self._mobile:
            browser.apply_mobile_device_mode(playwright, page)
        if self._system_code in browser.LEGACY_BROWSER_ACCESS_SYSTEMS:
            browser.grant_browser_permissions(context, base_url)
        page.set_default_timeout(browser.MAX_TIMEOUT_MS)
        page.set_default_navigation_timeout(browser.MAX_TIMEOUT_MS)
        dialog_messages = browser.add_dialog_logger(page)
        return AccessRuntime(
            base_url=base_url,
            mobile=self._mobile,
            playwright_manager=playwright_manager,
            context=context,
            page=page,
            dialog_messages=dialog_messages,
        )

    def _shutdown_browser(self, runtime: AccessRuntime) -> None:
        browser.shutdown_browser(runtime.page, runtime.context)


def create_access_executor(
    artifact_manager: ArtifactManager,
    *,
    execution_mode: str,
    system_code: str,
    base_url: str,
    mobile: bool = False,
) -> AccessWorkflowExecutor:
    return AccessWorkflowExecutor(
        artifact_manager,
        execution_mode=execution_mode,
        system_code=system_code,
        base_url=base_url,
        mobile=mobile,
    )
