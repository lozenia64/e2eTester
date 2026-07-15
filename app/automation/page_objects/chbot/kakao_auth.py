from __future__ import annotations

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.automation.page_objects.chbot import simple_auth
from app.automation.scenarios.rep_homepage.constants import (
    KAKAO_AUTH_BACKGROUND_WAIT_MS,
    KAKAO_AUTH_MAX_ATTEMPTS,
    is_kakao_auth_incomplete_message,
)
from app.runner.step_logging import log
from app.systems.access_common import browser

KAKAO_AUTH_LINK = "a:has-text('카카오 인증')"
KAKAO_AUTH_CONTAINER = (
    "xpath=//h2[contains(normalize-space(.),'카카오 인증')]"
    "/ancestor::div[contains(@class,'bot_lagacy')][1]"
)
KAKAO_NAME_INPUT = "input[name='aut_custNm']"
KAKAO_PHONE_PREFIX_INPUT = "input[name='hndphTlano']"
KAKAO_PHONE_MIDDLE_INPUT = "input[name='hndphTltno']"
KAKAO_PHONE_LAST_INPUT = "input[name='hndphTlsno']"
KAKAO_FORM_CONFIRM_BUTTON = "a.chatting-btn.orange:has-text('확인')"
KAKAO_COMPLETE_CONFIRM_BUTTON = (
    "a:has-text('카카오 인증완료 확인'), "
    "a:has-text('인증완료 확인'), "
    "a.chatting-btn.orange:has-text('확인')"
)
KAKAO_SENT_MODAL = ".d_modal"
KAKAO_SENT_MODAL_MARKER = "인증번호가 발송"
KAKAO_SENT_MODAL_CONFIRM = ".d_modal_ok, .d_modal_btn:has-text('확인')"

WELCOME_CHECK_TIMEOUT_MS = 5000
MODAL_DISMISS_TIMEOUT_MS = 5000


def _kakao_auth_container(page: Page) -> Locator:
    return page.locator(KAKAO_AUTH_CONTAINER).last


def _select_kakao_auth(page: Page) -> None:
    log("[step] Select kakao authentication")
    simple_auth._step_pause(page)
    simple_auth._wait_for_text(page, "간편인증 선택")
    simple_auth._step_pause(page)
    page.locator(KAKAO_AUTH_LINK).last.click()
    simple_auth._scroll_chat_to_bottom(page)
    simple_auth._step_pause(page)
    simple_auth._wait_for_text(page, "카카오 인증")


def _agree_kakao_auth_terms(container: Locator) -> None:
    checkbox = container.locator("input[name='checkbox01']")
    if checkbox.is_checked():
        log("[step] Kakao terms already agreed")
        return

    log("[step] Agree to kakao-auth terms (label click; checkbox is visually hidden)")
    agree_label = container.locator("label:has-text('약관 전체동의')").first
    agree_label.scroll_into_view_if_needed()
    agree_label.click()

    if not checkbox.is_checked():
        checkbox.evaluate(
            """
            (el) => {
                el.checked = true;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('click', { bubbles: true }));
            }
            """
        )

    if not checkbox.is_checked():
        raise RuntimeError("카카오 인증 약관 전체동의 선택에 실패했습니다.")


def _input_in_container(container: Locator, selector: str) -> Locator:
    """카카오 폼 컨테이너 안에서 최신 입력란 하나만 집는다."""
    return container.locator(selector).last


def _fill_input_field(
    field: Locator,
    value: str,
    *,
    label: str,
    allow_prefilled: bool = False,
) -> None:
    field.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    field.scroll_into_view_if_needed()

    current = (field.input_value() or "").strip()
    if allow_prefilled and current == value.strip():
        log(f"[step] {label} already filled")
        return

    readonly = field.get_attribute("readonly")
    if allow_prefilled and (readonly is not None or field.is_disabled()):
        if current:
            log(f"[step] {label} is readonly with value {current!r}; skip fill")
            return

    try:
        field.click()
        field.fill(value)
    except PlaywrightTimeoutError:
        field.evaluate(
            """
            (el, val) => {
                el.removeAttribute('readonly');
                el.value = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
            """,
            value,
        )


def _fill_kakao_auth_form(
    container: Locator,
    *,
    name: str,
    phone_prefix: str,
    phone_middle: str,
    phone_last: str,
) -> None:
    log("[step] Fill kakao auth form (name, phone)")
    _fill_input_field(
        _input_in_container(container, KAKAO_NAME_INPUT),
        name,
        label="Kakao name",
        allow_prefilled=True,
    )
    _fill_input_field(
        _input_in_container(container, KAKAO_PHONE_PREFIX_INPUT),
        phone_prefix,
        label="Kakao phone prefix",
    )
    _fill_input_field(
        _input_in_container(container, KAKAO_PHONE_MIDDLE_INPUT),
        phone_middle,
        label="Kakao phone middle",
    )
    _fill_input_field(
        _input_in_container(container, KAKAO_PHONE_LAST_INPUT),
        phone_last,
        label="Kakao phone last",
    )


def _click_visible_confirm(page: Page, locator: Locator, *, label: str) -> bool:
    for index in range(locator.count() - 1, -1, -1):
        candidate = locator.nth(index)
        try:
            if not candidate.is_visible(timeout=500):
                continue
            candidate.scroll_into_view_if_needed()
            candidate.click()
            log(f"[step] {label}")
            simple_auth._scroll_chat_to_bottom(page)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def _click_kakao_form_confirm(container: Locator, page: Page) -> None:
    clicked = _click_visible_confirm(
        page,
        container.locator(KAKAO_FORM_CONFIRM_BUTTON),
        label="Click kakao form confirm (auth request)",
    )
    if not clicked:
        raise RuntimeError("카카오 인증 폼의 확인 버튼을 찾지 못했습니다.")


def _dismiss_kakao_sent_modal(page: Page) -> None:
    modal = page.locator(KAKAO_SENT_MODAL).filter(has_text=KAKAO_SENT_MODAL_MARKER)
    try:
        modal.first.wait_for(state="visible", timeout=MODAL_DISMISS_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("[wait] Kakao sent modal not found; may already be dismissed")
        return

    confirm = modal.locator(KAKAO_SENT_MODAL_CONFIRM).first
    try:
        confirm.wait_for(state="visible", timeout=MODAL_DISMISS_TIMEOUT_MS)
        confirm.scroll_into_view_if_needed()
        confirm.click()
        log("[step] Dismiss kakao auth sent modal")
    except PlaywrightTimeoutError:
        raise RuntimeError("카카오 인증 발송 알림의 확인 버튼을 찾지 못했습니다.") from None

    try:
        modal.first.wait_for(state="hidden", timeout=MODAL_DISMISS_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("[warn] Kakao sent modal still visible after dismiss click")
    page.wait_for_timeout(500)


def _click_kakao_complete_confirm(page: Page) -> bool:
    simple_auth._scroll_chat_to_bottom(page)
    return _click_visible_confirm(
        page,
        page.locator(KAKAO_COMPLETE_CONFIRM_BUTTON),
        label="Click kakao auth complete confirm",
    )


def _page_has_incomplete_kakao_message(page: Page) -> bool:
    try:
        body_text = page.locator(".bot_lagacy").last.inner_text(timeout=1000)
    except PlaywrightTimeoutError:
        return False
    return is_kakao_auth_incomplete_message(body_text)


def _welcome_visible(page: Page) -> bool:
    try:
        page.get_by_text("환영합니다", exact=False).last.wait_for(
            state="visible",
            timeout=WELCOME_CHECK_TIMEOUT_MS,
        )
        return True
    except PlaywrightTimeoutError:
        return False


def _try_kakao_auth_attempt(page: Page, container: Locator) -> bool:
    _click_kakao_form_confirm(container, page)
    _dismiss_kakao_sent_modal(page)
    simple_auth._step_pause(page)
    log(
        f"[wait] Kakao톡 인증 진행 시간 ({KAKAO_AUTH_BACKGROUND_WAIT_MS} ms) — "
        "사용자가 앱에서 인증할 때까지 대기"
    )
    page.wait_for_timeout(KAKAO_AUTH_BACKGROUND_WAIT_MS)

    if _welcome_visible(page):
        return True

    if not _click_kakao_complete_confirm(page):
        log("[warn] Kakao complete confirm button not found")
        return False

    simple_auth._step_pause(page)
    if _welcome_visible(page):
        return True
    if _page_has_incomplete_kakao_message(page):
        log("[warn] 카카오 인증 미완료 — 재시도")
        return False
    return False


def run(
    page: Page,
    *,
    name: str,
    birthdate: str,
    gender_code: str,
    phone_number: str,
) -> str:
    """계약조회 진입부터 카카오 간편인증 완료·환영 메시지 검증까지 수행한다."""
    phone_prefix, phone_middle, phone_last = simple_auth._parse_phone_number(phone_number)

    simple_auth.run_identity_verification(
        page,
        name=name,
        birthdate=birthdate,
        gender_code=gender_code,
    )
    _select_kakao_auth(page)

    container = _kakao_auth_container(page)
    container.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    container.scroll_into_view_if_needed()
    _agree_kakao_auth_terms(container)
    _fill_kakao_auth_form(
        container,
        name=name.strip(),
        phone_prefix=phone_prefix,
        phone_middle=phone_middle,
        phone_last=phone_last,
    )

    for attempt in range(1, KAKAO_AUTH_MAX_ATTEMPTS + 1):
        log(f"[step] Kakao 인증 시도 {attempt}/{KAKAO_AUTH_MAX_ATTEMPTS}")
        if _try_kakao_auth_attempt(page, container):
            break
        if attempt == KAKAO_AUTH_MAX_ATTEMPTS:
            raise RuntimeError(
                f"카카오 인증 {KAKAO_AUTH_MAX_ATTEMPTS}회 실패: 인증이 완료되지 않았습니다."
            )

    simple_auth._verify_welcome(page)
    return "간편본인인증 성공"
