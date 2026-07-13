from __future__ import annotations

import re
import time

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.runner.step_logging import log
from app.systems.access_common import browser

LOGIN_FORM_PATH = "/login/loginForm.do"
SMS_FORM_PATH = "/login/loginSmsForm.do"
AUTH_SUCCESS_PATH = "/main/main.do"

USER_ID_SELECTOR = "#userId"
PASSWORD_SELECTOR = "#password"
LOGIN_BUTTON_SELECTOR = "button.btn.org.login"

POPUP_ALERT_SELECTOR = "#popAlert"
POPUP_CONFIRM_SELECTOR = "#popAlert button.btn.fill.small.org.ok"
LONG_IDLE_LOGIN_HEADING = "30일이상 미 로그인"

CERTI_KEY_SELECTOR = "#certiKey"
CERTI_KEY_ENABLED_SELECTOR = "#certiKey:not([disabled])"
SEND_SMS_BUTTON_SELECTOR = "#sendBtn1"
SUBMIT_OTP_BUTTON_SELECTOR = "#sendBtn3"

OTP_PATTERN = re.compile(r"\d{5}")

# MCP 와 동일: goto 직후 dialog 핸들러 + fill/click. 추가 CDP 세션은 금지.
LOGIN_FORM_SETTLE_MS = 1500
LOGIN_FORM_SUBMIT_TIMEOUT_MS = 60_000
LOGIN_FORM_RETRY_INTERVAL_MS = 50
LOGIN_FIELD_ACTION_TIMEOUT_MS = 5_000
LOGIN_SECURITY_BLOCK_SUBSTRING = "비정상적인 데이터"


def login_entry_url(base_url: str) -> str:
    return f"{browser.normalize_base_url(base_url, base_url)}{LOGIN_FORM_PATH}"


def run_main_access(page: Page, base_url: str) -> str:
    """HWTC 메인 접속: MCP 와 같이 loginForm.do 로 직접 진입한다."""
    _ensure_login_page(page, base_url)
    return "메인화면 접속 성공"


def _ensure_login_page(page: Page, base_url: str, *, reload: bool = True) -> None:
    if not reload and LOGIN_FORM_PATH in page.url:
        try:
            if page.locator(USER_ID_SELECTOR).is_visible(timeout=500):
                log(f"[wait] Reuse login form: {page.url}")
                return
        except PlaywrightTimeoutError:
            pass
    login_url = login_entry_url(base_url)
    log(f"[wait] Navigate to login form: {login_url}")
    page.goto(login_url, wait_until="domcontentloaded", timeout=browser.MAX_TIMEOUT_MS)
    log(f"[wait] Login form ready: {page.url}")
    _wait_for_login_form_ready(page)


def _wait_for_login_form_ready(page: Page) -> None:
    deadline = time.monotonic() + LOGIN_FORM_SUBMIT_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        try:
            if page.locator(USER_ID_SELECTOR).is_visible(timeout=500):
                log("[wait] Login form fields ready")
                return
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(LOGIN_FORM_RETRY_INTERVAL_MS)
    raise RuntimeError("로그인 화면(/login/loginForm.do) 입력란을 찾지 못했습니다.")


def _popup_heading_text(page: Page) -> str:
    try:
        return (page.locator(f"{POPUP_ALERT_SELECTOR} h2.tit").text_content() or "").strip()
    except Exception:
        return ""


def _is_popup_visible(page: Page) -> bool:
    try:
        return page.locator(POPUP_ALERT_SELECTOR).is_visible(timeout=1000)
    except PlaywrightTimeoutError:
        return False


def _click_popup_confirm(page: Page) -> None:
    """#popAlert 확인 버튼은 뷰포트 밖에 그려지는 경우가 있어 JS 클릭을 우선한다."""
    clicked = page.evaluate(
        """() => {
            const button = document.querySelector('#popAlert button.btn.fill.small.org.ok');
            if (!button) {
                return false;
            }
            button.click();
            return true;
        }"""
    )
    if clicked:
        return
    page.locator(POPUP_CONFIRM_SELECTOR).click(force=True)


def _maybe_confirm_popup(page: Page, *, heading_contains: str | None = None) -> bool:
    if not _is_popup_visible(page):
        return False
    heading = _popup_heading_text(page)
    if heading_contains and heading_contains not in heading:
        return False
    log(f"[step] Confirm alert popup: {heading or '(no heading)'}")
    _click_popup_confirm(page)
    return True


def _past_login_form(page: Page) -> bool:
    url = page.url
    return SMS_FORM_PATH in url or AUTH_SUCCESS_PATH in url


def _latest_security_block_message(dialog_messages: list[str]) -> str | None:
    for message in reversed(dialog_messages):
        if LOGIN_SECURITY_BLOCK_SUBSTRING in message:
            return message
    return None


def _submit_credentials(
    page: Page,
    user_id: str,
    password: str,
    dialog_messages: list[str],
) -> None:
    """MCP browser_run_code 와 동일: settle → fill → click (dialog 는 런타임 핸들러가 accept)."""
    if _past_login_form(page):
        log("[step] Skip login form submit (already past login)")
        return

    start_dialog_count = len(dialog_messages)
    log("[step] Fill login credentials")
    page.wait_for_timeout(LOGIN_FORM_SETTLE_MS)

    deadline = time.monotonic() + LOGIN_FORM_SUBMIT_TIMEOUT_MS / 1000
    filled = False
    while time.monotonic() < deadline:
        if _past_login_form(page):
            log("[step] Login form submit skipped (navigation detected)")
            return

        blocked = _latest_security_block_message(dialog_messages[start_dialog_count:])
        if blocked:
            raise RuntimeError(f"로그인 차단: {blocked}")

        try:
            page.locator(USER_ID_SELECTOR).fill(user_id, timeout=LOGIN_FIELD_ACTION_TIMEOUT_MS)
            page.locator(PASSWORD_SELECTOR).fill(password, timeout=LOGIN_FIELD_ACTION_TIMEOUT_MS)
            filled = True
            break
        except PlaywrightTimeoutError:
            page.wait_for_timeout(LOGIN_FORM_RETRY_INTERVAL_MS)

    if not filled:
        raise RuntimeError(
            "로그인 화면에서 아이디·비밀번호 입력에 실패했습니다. (개발자도구 차단 alert 반복)"
        )

    log("[step] Submit login form")
    page.locator(LOGIN_BUTTON_SELECTOR).click(timeout=LOGIN_FIELD_ACTION_TIMEOUT_MS)
    log("[step] Login form submitted")

    page.wait_for_timeout(500)
    blocked = _latest_security_block_message(dialog_messages[start_dialog_count:])
    if blocked:
        raise RuntimeError(f"로그인 차단: {blocked}")

    nav_deadline = time.monotonic() + browser.MAX_TIMEOUT_MS / 1000
    while time.monotonic() < nav_deadline:
        if _past_login_form(page):
            log(f"[wait] Left login form: {page.url}")
            return
        blocked = _latest_security_block_message(dialog_messages[start_dialog_count:])
        if blocked:
            raise RuntimeError(f"로그인 차단: {blocked}")
        page.wait_for_timeout(LOGIN_FORM_RETRY_INTERVAL_MS)

    if LOGIN_FORM_PATH in page.url:
        blocked = _latest_security_block_message(dialog_messages[start_dialog_count:])
        if blocked:
            raise RuntimeError(f"로그인 차단: {blocked}")
        raise RuntimeError(
            "LOGIN 제출 후 휴대폰 인증 화면으로 이동하지 못했습니다. "
            "개발자도구 차단 alert 또는 로그인 정보를 확인해 주세요."
        )

    try:
        page.locator(".wrap-loading").wait_for(state="hidden", timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("[warn] Login loading indicator did not hide in time")


def _ensure_sms_form(page: Page) -> None:
    if SMS_FORM_PATH in page.url:
        return

    if _maybe_confirm_popup(page, heading_contains=LONG_IDLE_LOGIN_HEADING):
        log("[step] Confirmed long-idle login popup")
    elif _maybe_confirm_popup(page):
        log("[step] Confirmed post-login popup")

    try:
        page.wait_for_url(f"**{SMS_FORM_PATH}", timeout=browser.MAX_TIMEOUT_MS)
        log(f"[wait] SMS auth form ready: {page.url}")
        return
    except PlaywrightTimeoutError:
        pass

    if AUTH_SUCCESS_PATH in page.url:
        log(f"[step] Already logged in: {page.url}")
        return

    if "/login/" not in page.url:
        log(f"[step] Already past login flow: {page.url}")
        return

    raise RuntimeError("휴대폰 인증 화면(/login/loginSmsForm.do)으로 이동하지 못했습니다.")


def _dismiss_visible_alert_popup(page: Page) -> bool:
    if not _is_popup_visible(page):
        return False
    log(f"[step] Dismiss alert popup: {_popup_heading_text(page) or '(no heading)'}")
    _click_popup_confirm(page)
    page.wait_for_timeout(300)
    return True


def _wait_for_sms_entry_ready(page: Page) -> None:
    """발급 후 안내 팝업을 닫고 인증번호 입력·제출 UI가 준비될 때까지 기다린다."""
    deadline = time.monotonic() + browser.MAX_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        _dismiss_visible_alert_popup(page)
        certi = page.locator(CERTI_KEY_ENABLED_SELECTOR)
        submit = page.locator(SUBMIT_OTP_BUTTON_SELECTOR)
        try:
            if certi.is_visible() and submit.is_visible():
                log("[wait] SMS auth inputs ready")
                return
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(250)

    raise RuntimeError("SMS 인증번호 발급 후 입력 화면이 준비되지 않았습니다.")


def _issue_sms_code(page: Page) -> None:
    log("[step] Request SMS verification code")
    page.locator(SEND_SMS_BUTTON_SELECTOR).click()
    _wait_for_sms_entry_ready(page)
    log("[step] SMS verification code issued")


def _resolve_otp_code(otp_code: str) -> str:
    candidate = (otp_code or "").strip()
    if not OTP_PATTERN.fullmatch(candidate):
        raise RuntimeError("인증번호는 5자리 숫자여야 합니다.")
    return candidate


def _wait_for_auth_success(page: Page, dialog_messages: list[str]) -> None:
    try:
        page.wait_for_url(lambda url: AUTH_SUCCESS_PATH in url, timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        if dialog_messages:
            raise RuntimeError(f"휴대폰 인증 실패: {dialog_messages[-1]}")
        raise RuntimeError(f"휴대폰 인증 후 메인화면({AUTH_SUCCESS_PATH})으로 이동하지 못했습니다.")
    browser.maybe_close_popup(page)
    log(f"[step] Phone auth succeeded: {page.url}")


def request_sms(
    page: Page,
    *,
    user_id: str,
    password: str,
    base_url: str,
    dialog_messages: list[str],
) -> str:
    """아이디·비밀번호 로그인 후 SMS 인증번호를 발급한다."""
    _ensure_login_page(page, base_url, reload=True)
    _submit_credentials(page, user_id, password, dialog_messages)
    _ensure_sms_form(page)

    if SMS_FORM_PATH not in page.url:
        return f"휴대폰 인증 생략(이미 로그인됨): {page.url}"

    _issue_sms_code(page)
    return "휴대폰 인증문자 발송 성공"


def submit_otp_and_login(
    page: Page,
    *,
    otp_code: str,
    dialog_messages: list[str],
) -> str:
    """발급된 SMS 인증번호를 제출하고 로그인을 완료한다."""
    if SMS_FORM_PATH not in page.url:
        _wait_for_auth_success(page, dialog_messages)
        return f"휴대폰 인증 성공: {page.url}"

    resolved = _resolve_otp_code(otp_code)
    log("[step] Submit SMS verification code")
    _dismiss_visible_alert_popup(page)
    certi = page.locator(CERTI_KEY_SELECTOR)
    certi.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    if not certi.is_enabled():
        raise RuntimeError("인증번호 입력란이 비활성 상태입니다. SMS 발급을 다시 시도해 주세요.")
    certi.fill(resolved)
    page.locator(SUBMIT_OTP_BUTTON_SELECTOR).click()

    try:
        page.locator(".wrap-loading").wait_for(state="hidden", timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("[warn] OTP submit loading indicator did not hide in time")

    _wait_for_auth_success(page, dialog_messages)
    return f"휴대폰 인증 성공: {page.url}"
