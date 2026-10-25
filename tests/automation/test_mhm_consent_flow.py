from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from app.automation.page_objects.mhm import compensation_charge as cc

CONSENT_HTML = """
<div class="dialog full show">
  <h2>동의 안내</h2><p>보험금청구를 위한 동의입니다.</p>
  <input type="checkbox" id="allCheck"
         onchange="document.querySelectorAll('.sub').forEach(c => c.checked = this.checked)">
  <label for="allCheck">전체 동의</label>
  <input type="checkbox" class="sub" id="[필수] 보험금 청구 동의">
  <label for="[필수] 보험금 청구 동의">[필수] 보험금 청구 동의</label>
  <button type="button" onclick="document.body.dataset.next = (+(document.body.dataset.next||0)+1)">다음</button>
</div>
"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch()
    except Exception as exc:
        playwright.stop()
        pytest.skip(f"Chromium 미설치 — python3 -m playwright install chromium 후 재실행: {exc}")
    yield browser
    browser.close()
    playwright.stop()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def test_new_consent_modal_checks_all_then_clicks_next(page):
    page.set_content(CONSENT_HTML)
    assert cc._handle_consent_flow(page, 5000) is True
    assert page.locator("#allCheck").is_checked()
    assert page.locator('input[id="[필수] 보험금 청구 동의"]').is_checked()
    assert int(page.evaluate("document.body.dataset.next || 0")) >= 1


def test_new_consent_modal_is_idempotent(page):
    page.set_content(CONSENT_HTML)
    page.locator("#allCheck").check()
    cc._handle_consent_flow(page, 5000)
    assert page.locator("#allCheck").is_checked()


def test_new_consent_modal_raises_when_not_checked(page):
    page.set_content(CONSENT_HTML.replace('id="allCheck"', 'id="allCheck" onclick="return false"'))
    with pytest.raises(RuntimeError, match="전체 동의 체크를 확인하지 못했습니다"):
        cc._handle_consent_flow(page, 5000)
    assert page.evaluate("document.body.dataset.next || ''") == ""


def test_no_consent_modal_returns_false(page):
    page.set_content("<main>청구사유</main>")
    assert cc._handle_consent_flow(page, 5000) is False
