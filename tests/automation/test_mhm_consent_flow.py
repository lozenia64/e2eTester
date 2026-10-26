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


UPLOAD_HTML = """
<button type="button">+ 보험금청구서류 (영수증 등 증빙자료)</button>
<div class="dialog full show"><h2>서류 등록</h2>
<ul>
 <li tabindex="0" role="button"><div class="form_item"><label for="none">카메라</label></div></li>
 <li>
  <div class="form_item" style="display: none;"><label for="galleyFile">앨범</label>
   <div class="input"><input type="file" id="galleyFile" multiple style="display: none;"></div></div>
  <div class="form_item"><label for="galleyFile">앨범</label>
   <div class="input"><input type="file" id="galleyFile" multiple style="display: none;"></div></div>
 </li>
</ul></div>
<script>
document.querySelectorAll('input[type=file]').forEach(i => i.addEventListener('change', () => {
  document.body.insertAdjacentHTML('beforeend',
    '<img alt="미리보기 이미지" style="width:50px;height:50px">');
}));
</script>
"""

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def test_upload_via_album_uses_visible_label_when_album_label_duplicated(page, tmp_path):
    png = tmp_path / "doc.png"
    png.write_bytes(PNG_1X1)
    page.set_content(UPLOAD_HTML)
    cc._upload_via_album(page, cc.PRIMARY_UPLOAD_BUTTON_PATTERN, png, "보험금청구서류")
    assert page.locator('img[alt*="미리보기"]').count() >= 1
