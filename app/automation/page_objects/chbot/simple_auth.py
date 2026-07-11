from __future__ import annotations

import re
import time

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.systems.access_common import browser

CHAT_MESSAGE_INPUT = "#message"
CHAT_SEND_BUTTON = "#btn-chat-send"

IDENTITY_NAME_INPUT = "input[name='hnglCtmnm']"
IDENTITY_BIRTH_INPUT = "input[name^='ssn1']"
IDENTITY_GENDER_SELECT = "select[name^='sex2']"
IDENTITY_CONFIRM_BUTTON = "#btn_conf, a[data-sinario='AUT002']"

PHONE_AUTH_LINK = "a:has-text('휴대폰 인증')"

PHONE_AUTH_CONTAINER = "xpath=//h2[contains(normalize-space(.),'휴대폰 인증')]/ancestor::div[contains(@class,'bot_lagacy')][1]"
CARRIER_SELECT = "select[name='hp_com']"
PHONE_PREFIX_INPUT = "input[name='hndphTlano']"
PHONE_MIDDLE_INPUT = "input[name='hndphTltno']"
PHONE_LAST_INPUT = "input[name='hndphTlsno']"
OTP_INPUT = "input[name='smsCertNo']"
OTP_CONFIRM_BUTTON = "a[data-sinario='AUT003_1']"
SMS_REQUEST_LINK = "a:text-is('인증번호')"

CARRIER_VALUES: dict[str, str] = {
    "01": "01",
    "skt": "01",
    "sk": "01",
    "02": "02",
    "kt": "02",
    "03": "03",
    "lgu": "03",
    "lgu+": "03",
    "lguplus": "03",
    "lg": "03",
    "05": "05",
    "skt_mvno": "05",
    "skt-mvno": "05",
    "sktmvno": "05",
    "06": "06",
    "kt_mvno": "06",
    "kt-mvno": "06",
    "ktmvno": "06",
    "07": "07",
    "lgu_mvno": "07",
    "lgu-mvno": "07",
    "lgumvno": "07",
    "lguplus_mvno": "07",
    "lguplus-mvno": "07",
    "lguplusmvno": "07",
}

GENDER_CODE_PATTERN = re.compile(r"^[1-8]$")
OTP_PATTERN = re.compile(r"\d{4,8}")
STEP_TRANSITION_PAUSE_MS = 1000


def _normalize_carrier(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key not in CARRIER_VALUES:
        allowed = ", ".join(sorted({"skt", "kt", "lgu+", "skt_mvno", "kt_mvno", "lgu_mvno"}))
        raise ValueError(f"지원하지 않는 통신사입니다: {raw!r}. 허용 값: {allowed}")
    return CARRIER_VALUES[key]


def _normalize_gender_code(raw: str) -> str:
    value = (raw or "").strip()
    if not GENDER_CODE_PATTERN.fullmatch(value):
        raise ValueError("성별코드는 1~8 사이의 한 자리 숫자여야 합니다.")
    return value


def _normalize_birthdate(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 8:
        digits = digits[2:]
    if len(digits) != 6:
        raise ValueError("생년월일은 6자리(YYMMDD) 또는 8자리(YYYYMMDD)로 입력해 주세요.")
    return digits


def _parse_phone_number(raw_phone: str) -> tuple[str, str, str]:
    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) != 11 or not digits.startswith("010"):
        raise ValueError("휴대폰 번호는 010으로 시작하는 11자리 숫자여야 합니다.")
    return digits[:3], digits[3:7], digits[7:]


def _step_pause(page: Page) -> None:
    print(f"[wait] Step transition pause ({STEP_TRANSITION_PAUSE_MS} ms)")
    page.wait_for_timeout(STEP_TRANSITION_PAUSE_MS)


def _scroll_chat_to_bottom(page: Page) -> None:
    page.evaluate(
        """
        () => {
            const targets = [
                document.querySelector('#cb-chatting-body'),
                document.querySelector('.cb-chatting-scroll'),
                document.querySelector('#chatting-logContainer'),
            ].filter(Boolean);
            for (const el of targets) {
                el.scrollTop = el.scrollHeight;
            }
        }
        """
    )


def _wait_for_text(page: Page, text: str, *, timeout_ms: int | None = None) -> None:
    timeout = timeout_ms or browser.MAX_TIMEOUT_MS
    print(f"[wait] Visible text: {text!r}")
    page.get_by_text(text, exact=False).last.wait_for(state="visible", timeout=timeout)
    _scroll_chat_to_bottom(page)


def _phone_auth_container(page: Page) -> Locator:
    return page.locator(PHONE_AUTH_CONTAINER).last


def _agree_phone_auth_terms(container: Locator) -> None:
    checkbox = container.locator("input[name='checkbox']")
    if checkbox.is_checked():
        print("[step] Terms already agreed")
        return

    print("[step] Agree to phone-auth terms (label click; checkbox is visually hidden)")
    agree_label = container.locator(".check_header label, label:has-text('약관 전체동의')").first
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
        raise RuntimeError("약관 전체동의 선택에 실패했습니다.")


def _send_chat_message(page: Page, message: str) -> None:
    print(f"[step] Send chat message: {message!r}")
    input_box = page.locator(CHAT_MESSAGE_INPUT)
    deadline = time.monotonic() + browser.MAX_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        try:
            if input_box.is_enabled():
                break
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(200)
    else:
        raise RuntimeError("챗봇 메시지 입력창이 활성화되지 않았습니다.")

    input_box.fill(message)
    page.locator(CHAT_SEND_BUTTON).click()
    _scroll_chat_to_bottom(page)


def _fill_identity_form(page: Page, *, name: str, birthdate: str, gender_code: str) -> None:
    print("[step] Fill identity verification form")
    page.locator(IDENTITY_NAME_INPUT).last.fill(name)
    page.locator(IDENTITY_BIRTH_INPUT).last.fill(birthdate)
    page.locator(IDENTITY_GENDER_SELECT).last.select_option(gender_code)


def _click_identity_confirm(page: Page) -> None:
    print("[step] Confirm identity verification")
    confirm = page.locator(IDENTITY_CONFIRM_BUTTON).last
    confirm.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    confirm.click()
    _scroll_chat_to_bottom(page)


def _select_phone_auth(page: Page) -> None:
    print("[step] Select phone authentication")
    _step_pause(page)
    _wait_for_text(page, "간편인증 선택")
    _step_pause(page)
    page.locator(PHONE_AUTH_LINK).last.click()
    _scroll_chat_to_bottom(page)
    _step_pause(page)
    _wait_for_text(page, "휴대폰 인증")


def _fill_phone_auth_form(
    page: Page,
    *,
    carrier_code: str,
    phone_prefix: str,
    phone_middle: str,
    phone_last: str,
) -> None:
    print("[step] Agree to phone-auth terms and fill phone fields")
    container = _phone_auth_container(page)
    container.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    container.scroll_into_view_if_needed()

    _agree_phone_auth_terms(container)

    container.locator(CARRIER_SELECT).select_option(carrier_code)
    container.locator(PHONE_PREFIX_INPUT).fill(phone_prefix)
    container.locator(PHONE_MIDDLE_INPUT).fill(phone_middle)
    container.locator(PHONE_LAST_INPUT).fill(phone_last)


def _request_sms_code(page: Page) -> None:
    print("[step] Request SMS verification code")
    container = _phone_auth_container(page)
    container.locator(SMS_REQUEST_LINK).first.click()

    otp_input = container.locator(OTP_INPUT)
    deadline = time.monotonic() + browser.MAX_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        try:
            readonly = otp_input.get_attribute("readonly")
            if readonly is None:
                print("[wait] OTP input enabled")
                return
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(250)

    print("[wait] OTP input still readonly; SMS request assumed complete")


def _fill_otp_code(page: Page, otp_code: str) -> None:
    resolved = OTP_PATTERN.search(otp_code.strip())
    if not resolved:
        raise ValueError("인증번호 형식이 올바르지 않습니다.")
    code = resolved.group(0)

    print("[step] Fill OTP code")
    container = _phone_auth_container(page)
    otp_input = container.locator(OTP_INPUT)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)

    try:
        otp_input.fill(code)
    except PlaywrightTimeoutError:
        page.evaluate(
            """
            ({ selector, code }) => {
                const input = document.querySelector(selector);
                if (!input) throw new Error('OTP input not found');
                input.removeAttribute('readonly');
                input.value = code;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
            """,
            {"selector": OTP_INPUT, "code": code},
        )


def _submit_otp(page: Page) -> None:
    print("[step] Submit OTP confirmation")
    container = _phone_auth_container(page)
    container.locator(OTP_CONFIRM_BUTTON).click()
    _scroll_chat_to_bottom(page)


def _verify_welcome(page: Page) -> None:
    print("[wait] Welcome message after authentication")
    _wait_for_text(page, "환영합니다", timeout_ms=browser.MAX_TIMEOUT_MS)


def request_otp(
    page: Page,
    *,
    name: str,
    birthdate: str,
    gender_code: str,
    carrier: str,
    phone_number: str,
) -> str:
    """계약조회 진입부터 SMS 인증번호 요청까지 수행한다."""
    normalized_birth = _normalize_birthdate(birthdate)
    normalized_gender = _normalize_gender_code(gender_code)
    carrier_code = _normalize_carrier(carrier)
    phone_prefix, phone_middle, phone_last = _parse_phone_number(phone_number)

    _send_chat_message(page, "계약조회")
    _step_pause(page)
    _wait_for_text(page, "본인 정보 확인")
    _step_pause(page)
    _fill_identity_form(
        page,
        name=name.strip(),
        birthdate=normalized_birth,
        gender_code=normalized_gender,
    )
    _click_identity_confirm(page)
    _select_phone_auth(page)
    _step_pause(page)
    _fill_phone_auth_form(
        page,
        carrier_code=carrier_code,
        phone_prefix=phone_prefix,
        phone_middle=phone_middle,
        phone_last=phone_last,
    )
    _request_sms_code(page)
    _step_pause(page)
    return "챗봇 휴대폰 인증번호를 입력해 주세요."


def submit_otp_and_verify(page: Page, *, otp_code: str) -> str:
    """OTP 입력 후 확인하고 환영 메시지를 검증한다."""
    _step_pause(page)
    _fill_otp_code(page, otp_code)
    _submit_otp(page)
    _step_pause(page)
    _verify_welcome(page)
    return "간편본인인증 성공"
