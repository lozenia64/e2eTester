"""사이트 방어 스크립트(EVFW/OhRep) alert·강제 새로고침 대응 검증.

대표홈페이지(PC)는 EVFW/OhRep 방어 스크립트가 자동화를 개발자도구·HTML 위변조로 오판하면
alert 을 띄우고 ``window.location.reload(true)`` 를 반복한다. alert 루프는 ``page.goto`` 를
정지시키고, 새로고침 루프는 클릭 대상을 DOM 에서 떼어내(element was detached) Locator.click
을 타임아웃시킨다 — 둘 다 일일점검 Run 을 실패로 만든다.

2026-08-19 실측된 실제 alert 문구는 '새로고침 후 이용해 주시길 바랍니다.' 였고, dialog 핸들러
안에서 부른 ``log`` 이 전부 유실돼 운영자·AI 분석이 원인을 오판했다(bind_log 로 수정).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.automation.page_objects.hom import login_common as hom_common
from app.runner import step_logging
from app.systems.access_common import browser as access_browser

AUTOMATION_CONTROLLED_FLAG = "--disable-blink-features=AutomationControlled"
# 사이트가 실제로 띄우는 문구 (공백 없는 '개발자도구')
BLOCK_ALERT_MESSAGE = "개발자도구 사용을 차단하였습니다!!"
# 2026-08-19 run_20260819_102719_ec8e9c 의 dialog_messages 에 4회 기록된 실제 문구
DEFENSE_RELOAD_MESSAGE = "새로고침 후 이용해 주시길 바랍니다."


class _FakeContext:
    def __init__(self) -> None:
        self.pages: list = []
        self.init_scripts: list[str] = []

    def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)


class _FakeChromium:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.contexts: list[_FakeContext] = []

    def launch_persistent_context(self, user_data_dir, **kwargs):
        self.calls.append({"user_data_dir": user_data_dir, **kwargs})
        context = _FakeContext()
        self.contexts.append(context)
        return context


class _FakePlaywright:
    def __init__(self) -> None:
        self.chromium = _FakeChromium()


class _FakeDialog:
    def __init__(self, message: str) -> None:
        self.message = message
        self.accepted = False

    def accept(self) -> None:
        self.accepted = True


class _FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def emit_dialog(self, message: str) -> _FakeDialog:
        dialog = _FakeDialog(message)
        for handler in self.handlers.get("dialog", []):
            handler(dialog)
        return dialog


class _SettlePage:
    """``wait_for_function`` 이 N 번째 폴링에서 통과하는 페이지 스텁."""

    url = "https://www.hwgeneralins.com/"

    def __init__(self, *, settle_after_polls: int) -> None:
        self._settle_after_polls = settle_after_polls
        self.settle_polls = 0
        self.clicked_after_settle = False
        self.locator_stub = SimpleNamespace(click=self._click)

    def _click(self) -> None:
        self.clicked_after_settle = self.settle_polls >= self._settle_after_polls

    def wait_for_function(self, expression: str, timeout: int | None = None):
        assert "performance.now()" in expression
        self.settle_polls = self._settle_after_polls

    def expect_navigation(self, **kwargs):
        from contextlib import nullcontext

        return nullcontext()

    def wait_for_url(self, url_or_pattern, timeout: int | None = None) -> None:
        return None


@pytest.mark.parametrize(
    "message",
    [
        BLOCK_ALERT_MESSAGE,
        "개발자 도구 사용이 감지되었습니다.",
        "개발자도구를 종료해 주세요",
        "HTML변경이 감지되었습니다!!",
        DEFENSE_RELOAD_MESSAGE,
        "새로고침후 이용해 주시길 바랍니다",
    ],
)
def test_site_defense_dialog_detected_regardless_of_spacing(message: str) -> None:
    assert access_browser.is_site_defense_dialog(message)


def test_normal_dialog_is_not_treated_as_site_defense() -> None:
    assert not access_browser.is_site_defense_dialog("정상적으로 처리되었습니다.")


def test_hom_persistent_launch_disables_automation_controlled(tmp_path) -> None:
    playwright = _FakePlaywright()

    hom_common.launch_persistent_browser_context(
        playwright, headless=False, slow_mo=0, user_data_dir=tmp_path
    )

    args = playwright.chromium.calls[0]["args"]
    assert AUTOMATION_CONTROLLED_FLAG in args


def test_legacy_access_launch_disables_automation_controlled(tmp_path) -> None:
    playwright = _FakePlaywright()

    access_browser.launch_legacy_persistent_browser_context(
        playwright, headless=False, slow_mo=0, user_data_dir=tmp_path
    )

    args = playwright.chromium.calls[0]["args"]
    assert AUTOMATION_CONTROLLED_FLAG in args


def test_hom_launch_installs_console_serialization_guard(tmp_path) -> None:
    """EVFW 실제 트리거인 콘솔 직렬화 지연을 없애는 init script 가 반드시 걸려야 한다."""
    playwright = _FakePlaywright()

    context = hom_common.launch_persistent_browser_context(
        playwright, headless=False, slow_mo=0, user_data_dir=tmp_path
    )

    assert len(context.init_scripts) == 1
    script = context.init_scripts[0]
    assert "console" in script
    assert "table" in script, "console.table 직렬화 비용이 판정 신호이므로 반드시 포함한다"


def test_legacy_launch_installs_console_guard(tmp_path) -> None:
    """FP(영업가족 위촉)·HRP(현장출동) 이 쓰는 legacy 런치."""
    playwright = _FakePlaywright()

    context = access_browser.launch_legacy_persistent_browser_context(
        playwright, headless=False, slow_mo=0, user_data_dir=tmp_path
    )

    assert len(context.init_scripts) == 1
    assert "table" in context.init_scripts[0]


def test_mcp_style_launch_installs_console_guard(tmp_path) -> None:
    """HWTC(연수원) 가 쓰는 Playwright MCP 스타일 런치."""
    playwright = _FakePlaywright()

    context = access_browser.launch_playwright_mcp_browser_context(
        playwright, headless=False, user_data_dir=tmp_path
    )

    assert len(context.init_scripts) == 1
    assert "table" in context.init_scripts[0]


def test_console_guard_keeps_error_and_warn_for_diagnostics() -> None:
    script = access_browser.CONSOLE_SERIALIZATION_GUARD_SCRIPT

    assert "'error'" not in script and '"error"' not in script
    assert "'warn'" not in script and '"warn"' not in script


def test_hom_dialog_logger_folds_repeated_defense_alerts() -> None:
    page = _FakePage()
    messages = hom_common.add_dialog_logger(page)

    for _ in range(4):
        dialog = page.emit_dialog(DEFENSE_RELOAD_MESSAGE)

    assert dialog.accepted, "차단 alert 도 닫아야 페이지가 계속 진행된다"
    assert messages == [DEFENSE_RELOAD_MESSAGE], (
        "증거는 1회 남기고 반복 기록으로 점검 판정을 오염시키지 않는다"
    )


def test_dialog_logger_log_survives_playwright_event_context() -> None:
    """dialog 핸들러의 로그가 스텝 싱크에 도달해야 한다.

    Playwright 이벤트 콜백은 dispatcher greenlet 에서 실행되므로 ContextVar 싱크가 보이지
    않는다. 핸들러 등록 시점에 싱크를 고정(bind_log)하지 않으면 로그가 조용히 사라진다.
    """
    captured: list[str] = []
    token = step_logging.push_sink(captured.append)
    try:
        page = _FakePage()
        hom_common.add_dialog_logger(page)
    finally:
        step_logging.pop_sink(token)

    # 핸들러 등록 이후, 싱크가 컨텍스트에서 사라진 뒤에 dialog 가 발생하는 상황을 재현한다.
    page.emit_dialog(DEFENSE_RELOAD_MESSAGE)
    page.emit_dialog("정상적으로 등록되었습니다.")

    assert any("[defense]" in line and DEFENSE_RELOAD_MESSAGE in line for line in captured), (
        f"방어 alert 로그가 유실됐다: {captured}"
    )
    assert any("[dialog] 정상적으로 등록되었습니다." == line for line in captured)


def test_navigation_click_waits_for_document_to_settle() -> None:
    """강제 새로고침 중에는 클릭하지 않고, 문서가 정착한 뒤에 클릭해야 한다."""
    page = _SettlePage(settle_after_polls=2)

    hom_common.click_and_wait_for_navigation(page, page.locator_stub, r"/util/login/login\.do$")

    assert page.settle_polls >= 2, "performance.now() 정착을 실제로 기다려야 한다"
    assert page.clicked_after_settle, "정착 전에 클릭하면 대상이 DOM 에서 떨어진다"


class _GotoPage:
    """goto 가 타임아웃하고, 문서 상태만 evaluate 로 확인 가능한 페이지."""

    def __init__(self, *, timeout: bool, doc_state: dict) -> None:
        self._timeout = timeout
        self._doc_state = doc_state
        self.goto_calls: list[str] = []

    def goto(self, url: str, **kwargs):
        self.goto_calls.append(url)
        if self._timeout:
            raise PlaywrightTimeoutError("Timeout 20000ms exceeded.")

    def evaluate(self, expression: str, *args, **kwargs):
        return self._doc_state


def test_navigation_continues_when_document_rendered_despite_block_alerts() -> None:
    page = _GotoPage(
        timeout=True,
        doc_state={"readyState": "complete", "title": "한화손보 - 메인페이지", "textLength": 119},
    )

    hom_common.goto_tolerating_block_alert(page, "https://www.hwgeneralins.com", 20000)

    assert page.goto_calls == ["https://www.hwgeneralins.com"]


def test_navigation_raises_actionable_error_when_document_empty() -> None:
    page = _GotoPage(
        timeout=True, doc_state={"readyState": "loading", "title": "", "textLength": 0}
    )

    with pytest.raises(RuntimeError, match="개발자도구"):
        hom_common.goto_tolerating_block_alert(page, "https://www.hwgeneralins.com", 20000)


def test_navigation_stays_quiet_on_normal_load() -> None:
    page = _GotoPage(timeout=False, doc_state={})

    hom_common.goto_tolerating_block_alert(page, "https://www.hwgeneralins.com", 20000)

    assert page.goto_calls == ["https://www.hwgeneralins.com"]


def test_hom_dialog_logger_keeps_business_dialog() -> None:
    page = _FakePage()
    messages = hom_common.add_dialog_logger(page)

    page.emit_dialog("정상적으로 등록되었습니다.")

    assert messages == ["정상적으로 등록되었습니다."]
