from __future__ import annotations

import re
from pathlib import Path

from . import login_common as common

LOGIN_TYPE_SELECT_URL_FRAGMENT = "/lin/fid/LginTyp"
PHONE_LOGIN_URL_FRAGMENT = "/lin/fid/LginTypSlc1020"
OTHER_LOGIN_METHOD_SELECTOR = 'main button.btn.btn_more:has-text("다른 로그인 방법")'
PHONE_ENTRY_SELECTOR = (
    'main a[role="button"]:has(span.cert_select_text:text-is("휴대폰인증")), '
    'main a.c5:has-text("휴대폰인증"), '
    'main a[role="button"]:has-text("휴대폰인증"), '
    'main button:has-text("휴대폰인증")'
)
PHONE_ENTRY_XPATH = (
    'xpath=//main//span[contains(@class,"cert_select_text") '
    'and contains(normalize-space(.),"휴대폰")]/ancestor::a[1]'
)
CARRIER_SELECT_LABELS: dict[str, str] = {
    "01": "SKT",
    "02": "KT",
    "03": "LGU+",
    "05": "SKT알뜰폰",
    "06": "KT알뜰폰",
    "07": "LGU+알뜰폰",
}
OTP_INPUT_ENABLED_JS = """
() => {
    const otp = document.querySelector('main #reqPhoneCheck');
    return Boolean(otp && !otp.disabled);
}
"""
CONFIRM_BUTTON_ENABLED_JS = """
() => {
    const btn = Array.from(document.querySelectorAll('main button.btn.s1.c1')).find(
        (element) => /확\\s*인|확인/.test((element.innerText || "").replace(/\\s+/g, ""))
    );
    return Boolean(btn && !btn.disabled);
}
"""
POST_LOGIN_MAIN_URL_FRAGMENT = "/myh/mai/MySubMain"
SMS_SENT_ALERT_CONFIRM_SELECTOR = (
    '.dialog.modal.alert.show:has-text("인증번호가 발송되었습니다") '
    'button.btn.ui_dialog_close, '
    '.dialog.modal.alert.show a.dialog_close.ui_dialog_close'
)
SMS_SENT_ALERT_DISMISSED_JS = """
() => !document.querySelector('.dialog.modal.alert.show')
"""


def _phone_form_root(page):
    root = page.locator("main")
    common.wait_locator_visible_with_log(root.locator("#customerName"), common.MAX_TIMEOUT_MS, "휴대폰인증 폼")
    return root


def _prepare_login_type_select_page(page) -> None:
    common.wait_url_with_log(
        page,
        re.compile(LOGIN_TYPE_SELECT_URL_FRAGMENT),
        common.MAX_TIMEOUT_MS,
        "로그인 방법 선택 페이지",
    )
    close_menu = page.locator('button:has-text("전체메뉴 닫기"), a.btn_gnb_close')
    try:
        if close_menu.first.is_visible(timeout=1000):
            common.click_with_log(close_menu.first, "전체메뉴 닫기")
    except Exception:
        pass
    try:
        common.wait_locator_visible_with_log(
            page.get_by_role("heading", name=re.compile(r"로그인\s*방법\s*선택")),
            common.MAX_TIMEOUT_MS,
            "로그인 방법 선택 제목",
        )
    except Exception:
        common.wait_locator_visible_with_log(page.locator("main"), common.MAX_TIMEOUT_MS, "로그인 방법 선택 main")


def _find_phone_auth_entry(page):
    try:
        return common.first_visible_locator(
            page.locator(PHONE_ENTRY_SELECTOR),
            "휴대폰인증 진입 (CSS)",
        )
    except RuntimeError:
        return common.first_visible_locator(
            page.locator(PHONE_ENTRY_XPATH),
            "휴대폰인증 진입 (XPath)",
        )


def _expand_other_login_methods(page) -> None:
    try:
        if _find_phone_auth_entry(page).is_visible(timeout=1000):
            return
    except Exception:
        pass

    other_login = page.locator(OTHER_LOGIN_METHOD_SELECTOR).first
    common.wait_locator_visible_with_log(other_login, common.MAX_TIMEOUT_MS, "다른 로그인 방법 버튼")
    common.click_with_log(other_login, "다른 로그인 방법 펼치기")
    common.wait_locator_visible_with_log(
        _find_phone_auth_entry(page),
        common.MAX_TIMEOUT_MS,
        "휴대폰인증 버튼 표시",
    )


def open_phone_login_page(page) -> None:
    """로그인 방법 선택 화면에서 다른 로그인 방법 → 휴대폰인증으로 이동한다."""
    if PHONE_LOGIN_URL_FRAGMENT in page.url:
        _phone_form_root(page)
        return

    if LOGIN_TYPE_SELECT_URL_FRAGMENT not in page.url:
        print(
            f"[warn] 로그인 방법 선택 URL이 아닐 수 있음 "
            f"(기대: …{LOGIN_TYPE_SELECT_URL_FRAGMENT}): {page.url}"
        )

    _prepare_login_type_select_page(page)
    _expand_other_login_methods(page)
    phone_entry = _find_phone_auth_entry(page)
    common.click_with_log(phone_entry, "휴대폰인증 진입")
    _phone_form_root(page)
    common.wait_timeout_with_log(page, 300, "휴대폰인증 폼 안정화 대기")


def _compute_jumin2_digit(config: common.LoginConfig) -> str:
    birth_year = int(config.birthdate[:4])
    is_2000s = birth_year >= 2000
    is_male = config.gender == "01"
    is_domestic = config.residency == "01"

    if is_domestic and not is_2000s:
        return "1" if is_male else "2"
    if is_domestic and is_2000s:
        return "3" if is_male else "4"
    if not is_domestic and not is_2000s:
        return "5" if is_male else "6"
    return "7" if is_male else "8"


def fill_mobile_phone_form(page, config: common.LoginConfig) -> None:
    """모바일 휴대폰인증 페이지(LginTypSlc1020)에 사용자 정보를 입력한다."""
    print("[step] Fill mobile phone auth form")
    root = _phone_form_root(page)

    name_field = root.locator("#customerName")
    common.click_with_log(name_field, "이름 입력란")
    name_field.fill(config.name)

    jumin1 = root.locator("#jumin1")
    common.click_with_log(jumin1, "주민번호 앞 6자리 입력란")
    jumin1.fill(config.birthdate[2:8])

    jumin2 = root.locator("#jumin2")
    common.click_with_log(jumin2, "주민번호 뒷자리(성별) 입력란")
    jumin2.fill(_compute_jumin2_digit(config))

    carrier_label = CARRIER_SELECT_LABELS.get(config.carrier)
    if not carrier_label:
        raise RuntimeError(f"Unsupported carrier code for mobile phone auth: {config.carrier}")
    carrier_select = root.locator("#cellphone0")
    common.click_with_log(carrier_select, "통신사 선택")
    carrier_select.select_option(label=carrier_label)

    phone_number = f"{config.phone_prefix}{config.phone_middle}{config.phone_last}"
    phone_field = root.locator("#cellphone1")
    common.click_with_log(phone_field, "휴대전화번호 입력란")
    phone_field.fill(phone_number)

    checkbox = root.locator("#checkAll")
    if not checkbox.is_checked():
        consent_label = root.get_by_text("전체동의", exact=True)
        common.wait_locator_visible_with_log(consent_label, common.MAX_TIMEOUT_MS, "전체동의")
        common.click_with_log(consent_label, "전체동의")


def dismiss_sms_sent_alert(page, timeout_ms: int) -> None:
    """인증요청 성공 후 뜨는 '인증번호가 발송되었습니다.' 알림을 닫는다."""
    print("[step] 휴대폰 인증번호 발송 알림 닫기")
    alert_confirm = page.locator(SMS_SENT_ALERT_CONFIRM_SELECTOR).first
    try:
        common.wait_locator_visible_with_log(alert_confirm, timeout_ms, "인증번호 발송 알림")
        common.click_with_log(alert_confirm, "인증번호 발송 알림 — 확인")
        common.wait_function_with_log(
            page,
            SMS_SENT_ALERT_DISMISSED_JS,
            min(timeout_ms, common.MAX_TIMEOUT_MS),
            "인증번호 발송 알림 닫힘",
        )
    except Exception as exc:
        print(f"[warn] 인증번호 발송 알림을 찾지 못했거나 이미 닫힘: {exc}")


def request_mobile_sms_code(page, dialog_messages: list[str], timeout_ms: int) -> None:
    print("[step] Request mobile SMS verification code")
    dialog_index = len(dialog_messages)
    root = _phone_form_root(page)
    common.scroll_to_page_bottom(page)

    auth_request = common.first_visible_locator(
        root.locator('button.btn.s3.c4:has-text("인증요청")'),
        "휴대폰 인증요청 버튼",
    )
    common.click_with_log(auth_request, "휴대폰 인증요청")
    dismiss_sms_sent_alert(page, timeout_ms)
    common.wait_timeout_with_log(page, 1000, "Post-mobile-SMS-request settle delay")
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "mobile SMS verification request")

    try:
        common.wait_function_with_log(
            page,
            OTP_INPUT_ENABLED_JS,
            timeout_ms,
            "모바일 OTP 입력란 활성화",
        )
    except Exception as exc:
        raise RuntimeError("SMS verification request did not enable the OTP input field.") from exc


def submit_mobile_otp(
    page,
    otp_code: str,
    dialog_messages: list[str],
    timeout_ms: int,
    *,
    post_login_fragment: str = POST_LOGIN_MAIN_URL_FRAGMENT,
) -> None:
    print("[step] Submit mobile OTP")
    dialog_index = len(dialog_messages)
    dismiss_sms_sent_alert(page, min(timeout_ms, 5000))
    root = _phone_form_root(page)
    common.scroll_to_page_bottom(page)

    otp_field = root.locator("#reqPhoneCheck")
    common.wait_locator_visible_with_log(otp_field, timeout_ms, "모바일 OTP 입력란")
    common.click_with_log(otp_field, "모바일 OTP 입력란")
    otp_field.fill(otp_code)

    confirm_btn = common.first_visible_locator(
        root.locator('button.btn.s1.c1:has-text("확인")'),
        "휴대폰인증 확인 버튼",
    )
    common.wait_function_with_log(
        page,
        CONFIRM_BUTTON_ENABLED_JS,
        timeout_ms,
        "휴대폰인증 확인 버튼 활성화",
    )
    common.click_with_log(confirm_btn, "휴대폰인증 확인")
    common.wait_timeout_with_log(page, 1000, "Post-mobile-OTP-submit settle delay")
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "mobile OTP submission")

    print(f"[wait] Start post-OTP login redirect wait: {post_login_fragment} ({timeout_ms} ms)")
    common.wait_for_main_page(page, post_login_fragment, timeout_ms)
    print(f"[wait] End post-OTP login redirect wait -> {page.url}")


def request_sms(page, config: common.LoginConfig, dialog_messages: list[str]) -> str:
    open_phone_login_page(page)
    fill_mobile_phone_form(page, config)
    request_mobile_sms_code(page, dialog_messages, config.timeout_ms)
    return "휴대폰 인증문자 발송 성공"


def submit_otp_and_login(
    page,
    config: common.LoginConfig,
    dialog_messages: list[str],
    screenshot_path: Path,
) -> str:
    otp_code = common.resolve_otp_code(config)
    submit_mobile_otp(page, otp_code, dialog_messages, config.timeout_ms, post_login_fragment=config.post_login_fragment)
    common.wait_for_login_success(page, config, dialog_messages)
    common.save_screenshot(page, screenshot_path)
    return f"휴대폰 로그인 성공: {page.url}"
