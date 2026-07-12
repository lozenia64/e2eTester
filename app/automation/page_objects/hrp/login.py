from __future__ import annotations

import re

from playwright.sync_api import FrameLocator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.runner.step_logging import log
from app.systems.access_common import browser

FIRST_PAGE_PATH = "/first.do"
AUTH_SUCCESS_PATH = "amain.do"
AUTH_POPUP_IFRAME = '[id^="__POP_ID_"] iframe'

USER_ID_SELECTOR = "#firstId"
PASSWORD_SELECTOR = "#firstPw"
LOGIN_BUTTON_SELECTOR = "#btnRA"

SMS_BUTTON_SELECTOR = "#btnSMS"
OTP_INPUT_SELECTOR = "#smsNum"
SUBMIT_OTP_BUTTON_SELECTOR = "#btnOk"
TIMER_SELECTOR = "#setTime"

OTP_PATTERN = re.compile(r"\d{4,8}")


def _first_page_url(base_url: str) -> str:
    return f"{browser.normalize_base_url(base_url, base_url)}{FIRST_PAGE_PATH}"


def _auth_frame(page: Page) -> FrameLocator:
    return page.frame_locator(AUTH_POPUP_IFRAME)


def _ensure_first_page(page: Page, base_url: str) -> None:
    if FIRST_PAGE_PATH in page.url:
        return
    login_url = _first_page_url(base_url)
    log(f"[wait] Navigate to login page: {login_url}")
    page.goto(login_url, wait_until="domcontentloaded", timeout=browser.MAX_TIMEOUT_MS)
    log(f"[wait] Login page ready: {page.url}")


def _auth_frame_ready(page: Page, *, timeout_ms: int = 1000) -> bool:
    """cubePopup 부모 div 는 is_visible() 이 false 인 경우가 있어 iframe 내용으로 판별한다."""
    try:
        return (
            _auth_frame(page)
            .get_by_role("heading", name="사용자 인증")
            .is_visible(timeout=timeout_ms)
        )
    except PlaywrightTimeoutError:
        return False


def _wait_for_auth_popup(page: Page) -> FrameLocator:
    page.locator('[id^="__POP_ID_"] iframe').wait_for(
        state="attached", timeout=browser.MAX_TIMEOUT_MS
    )
    frame = _auth_frame(page)
    frame.get_by_role("heading", name="사용자 인증").wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )
    frame.locator(SMS_BUTTON_SELECTOR).wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    log("[wait] User auth popup ready")
    return frame


def _ensure_auth_frame(page: Page) -> FrameLocator:
    if _auth_frame_ready(page):
        return _auth_frame(page)
    return _wait_for_auth_popup(page)


def _click_frame_button(frame: FrameLocator, *, name: str, selector: str) -> None:
    button = frame.get_by_role("button", name=name)
    try:
        button.click(timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log(f"[warn] Role click failed for {name!r}; retry with force")
        frame.locator(selector).click(force=True, timeout=browser.MAX_TIMEOUT_MS)


def _submit_credentials(page: Page, user_id: str, password: str) -> None:
    log("[step] Fill login credentials")
    page.locator(USER_ID_SELECTOR).fill(user_id)
    page.locator(PASSWORD_SELECTOR).fill(password)
    log("[step] Submit login form")
    page.locator(LOGIN_BUTTON_SELECTOR).click()


def _issue_sms_code(frame: FrameLocator) -> None:
    log("[step] Request SMS verification code")
    _click_frame_button(frame, name="인증번호 받기", selector=SMS_BUTTON_SELECTOR)
    frame.locator(TIMER_SELECTOR).wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    otp_input = frame.locator(OTP_INPUT_SELECTOR)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    if not otp_input.is_enabled():
        raise RuntimeError("인증번호 입력란이 비활성 상태입니다. SMS 발급을 다시 시도해 주세요.")
    timer_text = frame.locator(TIMER_SELECTOR).inner_text()
    log(f"[wait] SMS auth timer started: {timer_text.strip()}")


def _resolve_otp_code(otp_code: str) -> str:
    candidate = (otp_code or "").strip()
    if not OTP_PATTERN.fullmatch(candidate):
        raise RuntimeError("인증번호는 4~8자리 숫자여야 합니다.")
    return candidate


def _wait_for_auth_success(page: Page, dialog_messages: list[str]) -> None:
    try:
        page.wait_for_url(lambda url: AUTH_SUCCESS_PATH in url, timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        if dialog_messages:
            raise RuntimeError(f"로그인 실패: {dialog_messages[-1]}")
        raise RuntimeError(f"로그인 후 메인화면({AUTH_SUCCESS_PATH})으로 이동하지 못했습니다.")
    browser.maybe_close_popup(page)
    log(f"[step] Login succeeded: {page.url}")


def request_otp(
    page: Page,
    *,
    user_id: str,
    password: str,
    base_url: str,
) -> str:
    """아이디·비밀번호 로그인 후 사용자 인증 팝업에서 SMS 인증번호를 발급한다."""
    if AUTH_SUCCESS_PATH in page.url:
        return f"로그인 생략(이미 로그인됨): {page.url}"

    _ensure_first_page(page, base_url)
    if not _auth_frame_ready(page):
        browser.maybe_close_popup(page)

    if not _auth_frame_ready(page):
        _submit_credentials(page, user_id, password)
        frame = _wait_for_auth_popup(page)
    else:
        log("[step] User auth popup already open")
        frame = _auth_frame(page)

    _issue_sms_code(frame)
    return "휴대폰 인증문자 발송 성공"


def submit_otp_and_login(
    page: Page,
    *,
    otp_code: str,
    dialog_messages: list[str],
) -> str:
    """발급된 SMS 인증번호를 제출하고 로그인을 완료한다."""
    if AUTH_SUCCESS_PATH in page.url:
        return f"로그인 성공: {page.url}"

    resolved = _resolve_otp_code(otp_code)
    frame = _ensure_auth_frame(page)
    log("[step] Submit SMS verification code")
    otp_input = frame.locator(OTP_INPUT_SELECTOR)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    otp_input.fill(resolved)
    _click_frame_button(frame, name="확인", selector=SUBMIT_OTP_BUTTON_SELECTOR)

    _wait_for_auth_success(page, dialog_messages)
    return f"로그인 성공: {page.url}"
