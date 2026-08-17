"""사이트 방어 스크립트의 '개발자도구 차단' alert 대응 검증.

대표홈페이지(PC)는 EVFW/AATIE 방어 스크립트가 ``navigator.webdriver`` 와 콘솔 계측으로
개발자도구를 탐지해 ``alert("개발자도구 사용을 차단하였습니다!!")`` 를 반복 발생시킨다.
alert 루프는 ``page.goto`` 를 정지시켜 일일점검 Run 을 실패로 만든다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.automation.page_objects.hom import login_common as hom_common
from app.systems.access_common import browser as access_browser

AUTOMATION_CONTROLLED_FLAG = "--disable-blink-features=AutomationControlled"
# 사이트가 실제로 띄우는 문구 (공백 없는 '개발자도구')
BLOCK_ALERT_MESSAGE = "개발자도구 사용을 차단하였습니다!!"


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


@pytest.mark.parametrize(
    "message",
    [
        BLOCK_ALERT_MESSAGE,
        "개발자 도구 사용이 감지되었습니다.",
        "개발자도구를 종료해 주세요",
    ],
)
def test_devtools_block_dialog_detected_regardless_of_spacing(message: str) -> None:
    assert access_browser.is_devtools_block_dialog(message)


def test_normal_dialog_is_not_treated_as_devtools_block() -> None:
    assert not access_browser.is_devtools_block_dialog("정상적으로 처리되었습니다.")


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


def test_hom_dialog_logger_swallows_devtools_block_alert() -> None:
    page = _FakePage()
    messages = hom_common.add_dialog_logger(page)

    dialog = page.emit_dialog(BLOCK_ALERT_MESSAGE)

    assert dialog.accepted, "차단 alert 도 닫아야 페이지가 계속 진행된다"
    assert messages == [], "차단 alert 은 점검 판정용 dialog 기록에서 제외한다"


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
