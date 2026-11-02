"""MHM 하단 배너(.dialog.bottom.bottom_bnr) 처리 회귀 테스트.

2026-11-02 run_20261101_230945_62e5fc: 로그인 후 메인에 뷰포트 전체를 덮는 배너가 떴지만
``maybe_close_post_login_popup`` 이 감지하지 못해 계약현황조회 클릭이 타임아웃됐다.
배너는 사이트 캠페인이라 언제든 사라질 수 있으므로, 없을 때도 오류 없이 넘어가야 한다.
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import sync_playwright

from app.automation.page_objects.mhm import login_common as common


def _banner_html(*, close_button: bool = True, style: str = "") -> str:
    close = (
        """<button class="btn s1 c1 ui_dialog_close"
                   onclick="this.closest('.dialog').classList.remove('show');
                            this.closest('.dialog').style.display = 'none'">닫기</button>"""
        if close_button
        else ""
    )
    return f"""
    <div role="dialog" class="dialog bottom bottom_bnr show"
         style="position: fixed; inset: 0; z-index: 200; {style}">
      <button>확인하러가기</button>{close}
    </div>
    """


TARGET_HTML = """
<main><button id="target" onclick="document.body.dataset.clicked = '1'">계약현황조회</button></main>
"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    # 워커와 동일한 기본 타임아웃 — 배너가 사라졌을 때 이 시간만큼 묶이면 안 된다.
    page.set_default_timeout(common.MAX_TIMEOUT_MS)
    yield page
    context.close()


@pytest.fixture
def logs(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(common, "log", lines.append)
    return lines


def _banner_visible(page) -> bool:
    return page.locator(".dialog.bottom.bottom_bnr.show").first.is_visible()


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_post_login_check_closes_banner_so_blocked_button_is_clickable(page, logs):
    page.set_content(TARGET_HTML + _banner_html())

    common.maybe_close_post_login_popup(page, 600)

    assert not _banner_visible(page)
    page.locator("#target").click(timeout=1000)
    assert page.evaluate("document.body.dataset.clicked") == "1"


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_post_login_check_closes_banner_that_appears_during_polling(page, logs):
    page.set_content(TARGET_HTML + _banner_html(style="display: none;"))
    page.evaluate(
        "setTimeout(() => document.querySelector('.bottom_bnr').style.display = 'block', 200)"
    )

    common.maybe_close_post_login_popup(page, 1000)

    assert not _banner_visible(page)


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_post_login_check_passes_when_banner_never_existed(page, logs):
    page.set_content(TARGET_HTML)

    common.maybe_close_post_login_popup(page, 600)

    assert any("No post-login popup detected" in line for line in logs)
    assert not any(line.startswith("[warn]") for line in logs)


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_post_login_check_passes_quietly_when_banner_vanishes_before_click(page, logs):
    # 닫기 버튼이 가려져 클릭이 재시도되는 사이 사이트가 배너를 직접 제거하는 상황.
    page.set_content(
        TARGET_HTML
        + _banner_html()
        + """<div style="position: fixed; inset: 0; z-index: 300"
                  id="cover"></div>"""
    )
    page.evaluate(
        """setTimeout(() => {
            document.querySelector('.bottom_bnr').remove();
            document.querySelector('#cover').remove();
        }, 500)"""
    )

    started = time.monotonic()
    common.maybe_close_post_login_popup(page, 600)
    elapsed = time.monotonic() - started

    assert not _banner_visible(page)
    assert not any(line.startswith("[warn]") for line in logs)
    assert elapsed < 8


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_post_login_check_does_not_raise_when_banner_cannot_be_closed(page, logs):
    page.set_content(TARGET_HTML + _banner_html(close_button=False))

    common.maybe_close_post_login_popup(page, 600)

    assert any(line.startswith("[warn]") for line in logs)


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_pre_login_check_still_closes_banner(page, logs):
    page.set_content(TARGET_HTML + _banner_html())

    common.maybe_close_pre_login_bottom_popup(page)

    assert not _banner_visible(page)
    assert not any(line.startswith("[warn]") for line in logs)


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
def test_post_login_check_closes_delayed_banner_covering_existing_modal(page, logs):
    page.set_default_timeout(1200)
    page.set_content(
        TARGET_HTML
        + _banner_html(style="display: none;")
        + """<div id="uiPOPCtmAgre" class="dialog modal show"
                   style="display: none; position: fixed; inset: 0; z-index: 100">
             모바일 안내장 신청 안내
             <button onclick="this.parentElement.style.display = 'none'">다음에 할게요</button>
           </div>"""
    )
    page.evaluate(
        """setTimeout(() => {
            document.querySelector('.bottom_bnr').style.display = 'block';
            document.querySelector('#uiPOPCtmAgre').style.display = 'block';
        }, 200)"""
    )

    common.maybe_close_post_login_popup(page, 1000)

    assert not _banner_visible(page)
    assert not page.locator("#uiPOPCtmAgre").is_visible()
    page.locator("#target").click(timeout=1000)
    assert page.evaluate("document.body.dataset.clicked") == "1"


@pytest.mark.spec("SPEC-SYS-MHM", "AC-001")
@pytest.mark.parametrize(
    "check", [common.maybe_close_pre_login_bottom_popup, common.maybe_close_post_login_popup]
)
def test_banner_check_ignores_hidden_copy_before_visible_banner(page, logs, check):
    page.set_content(TARGET_HTML + _banner_html(style="display: none;") + _banner_html())

    check(page)

    assert page.locator(".bottom_bnr:visible").count() == 0
    page.locator("#target").click(timeout=1000)
    assert page.evaluate("document.body.dataset.clicked") == "1"
