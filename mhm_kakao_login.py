from __future__ import annotations

import re
from pathlib import Path

import mhm_login_common as common

# 카카오톡에서 사용자 인증을 마칠 시간을 주기 위해 '인증요청' 후 이 시간만큼 대기한 뒤 '인증확인'을 누른다.
KAKAO_AUTH_BACKGROUND_WAIT_MS = 20_000

LOGIN_TYPE_SELECT_URL_FRAGMENT = "/lin/fid/LginTyp"
KAKAO_LOGIN_URL_FRAGMENT = "/lin/kct/KakaoWebLgin"
# 로그인 방법 선택 화면: 카카오인증은 <button>이 아니라 a[role="button"].c4 > span.cert_select_text 구조다.
KAKAO_ENTRY_SELECTOR = (
    'main a[role="button"]:has(span.cert_select_text:text-is("카카오인증")), '
    'main a.c4:has-text("카카오인증"), '
    'main a[role="button"]:has-text("카카오인증"), '
    'main button:has-text("카카오인증")'
)
KAKAO_ENTRY_XPATH = (
    'xpath=//main//span[contains(@class,"cert_select_text") '
    'and contains(normalize-space(.),"카카오")]/ancestor::a[1]'
)
KAKAO_REQUEST_ALERT_CONFIRM_SELECTOR = (
    ".modal.alert.show button.btn.ui_dialog_close, "
    ".modal.alert.show button:has-text(\"확인\")"
)
KAKAO_AUTH_CONFIRM_ENABLED_JS = """
() => {
    const btn = Array.from(document.querySelectorAll("main button")).find(
        (element) => /인증\\s*확인|인증확인/.test((element.innerText || "").replace(/\\s+/g, ""))
    );
    return Boolean(btn && !btn.disabled);
}
"""


def _kakao_form_root(page):
    root = page.locator("main")
    common.wait_locator_visible_with_log(root.locator("#name"), common.MAX_TIMEOUT_MS, "카카오 인증 폼")
    return root


def _wait_for_kakao_consent_checked(page, timeout_ms: int, reason: str) -> None:
    common.wait_function_with_log(
        page,
        "() => Boolean(document.querySelector('main #G29')?.checked)",
        timeout_ms,
        reason,
    )


def _prepare_login_type_select_page(page) -> None:
    common.wait_url_with_log(
        page,
        re.compile(LOGIN_TYPE_SELECT_URL_FRAGMENT),
        common.MAX_TIMEOUT_MS,
        "로그인 방법 선택 페이지",
    )
    close_menu = page.locator('button:has-text("전체메뉴 닫기")')
    try:
        if close_menu.is_visible(timeout=1000):
            common.click_with_log(close_menu, "전체메뉴 닫기")
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


def _find_kakao_auth_entry(page):
    try:
        return common.first_visible_locator(
            page.locator(KAKAO_ENTRY_SELECTOR),
            "카카오인증 진입 (CSS)",
        )
    except RuntimeError:
        return common.first_visible_locator(
            page.locator(KAKAO_ENTRY_XPATH),
            "카카오인증 진입 (XPath)",
        )


def open_kakao_login_page(page) -> None:
    """로그인 방법 선택 화면에서 카카오인증을 눌러 카카오 본인인증 페이지로 이동한다."""
    if KAKAO_LOGIN_URL_FRAGMENT in page.url:
        _kakao_form_root(page)
        return

    if LOGIN_TYPE_SELECT_URL_FRAGMENT not in page.url:
        print(
            f"[warn] 로그인 방법 선택 URL이 아닐 수 있음 "
            f"(기대: …{LOGIN_TYPE_SELECT_URL_FRAGMENT}): {page.url}"
        )

    _prepare_login_type_select_page(page)
    kakao_button = _find_kakao_auth_entry(page)

    common.click_and_wait_for_navigation(page, kakao_button, KAKAO_LOGIN_URL_FRAGMENT)
    _kakao_form_root(page)
    common.wait_timeout_with_log(page, 300, "카카오 인증 폼 안정화 대기")


def _ensure_kakao_consents(page) -> None:
    """카카오 본인인증 페이지에서 전체동의 체크박스를 선택한다."""
    print("[step] Kakao 필수 동의")
    root = _kakao_form_root(page)
    checkbox = root.locator("#G29")
    if checkbox.is_checked():
        return

    consent_label = root.get_by_text("전체동의", exact=True)
    common.wait_locator_visible_with_log(consent_label, common.MAX_TIMEOUT_MS, "Kakao 전체동의")
    common.click_with_log(consent_label, "Kakao 전체동의")
    _wait_for_kakao_consent_checked(page, common.MAX_TIMEOUT_MS, "Kakao 전체동의 반영")


def fill_kakao_form(page, config: common.LoginConfig) -> None:
    """카카오 본인인증 페이지에 이름·생년월일·휴대전화번호를 입력한다."""
    print("[step] Fill Kakao auth form (이름, 생년월일, 휴대폰)")
    root = _kakao_form_root(page)

    name_f = root.locator("#name")
    common.click_with_log(name_f, "Kakao 이름 입력란")
    name_f.fill(config.name)

    birth_f = root.locator("#birth")
    common.click_with_log(birth_f, "Kakao 생년월일 입력란")
    birth_f.fill(config.birthdate)

    phone_number = f"{config.phone_prefix}{config.phone_middle}{config.phone_last}"
    phone_f = root.locator("#cellphone1")
    common.click_with_log(phone_f, "Kakao 휴대전화번호 입력란")
    phone_f.fill(phone_number)


def _kakao_auth_confirm_button(root):
    return root.locator('button.btn.s1.c1:has-text("인증확인"), button:has-text("인증확인")').first


def dismiss_kakao_auth_request_alert(page, timeout_ms: int) -> None:
    """인증요청 성공 후 뜨는 '카카오인증 요청 메시지가 발송되었습니다' 알림을 닫는다."""
    print("[step] Kakao 인증요청 발송 알림 닫기")
    alert_confirm = page.locator(KAKAO_REQUEST_ALERT_CONFIRM_SELECTOR).first
    try:
        common.wait_locator_visible_with_log(alert_confirm, timeout_ms, "카카오 인증요청 발송 알림")
        common.click_with_log(alert_confirm, "카카오 인증요청 발송 알림 — 확인")
        common.wait_function_with_log(
            page,
            "() => !document.querySelector('.modal.alert.show')",
            min(timeout_ms, common.MAX_TIMEOUT_MS),
            "카카오 인증요청 알림 닫힘",
        )
    except Exception as exc:
        print(f"[warn] 카카오 인증요청 알림을 찾지 못했거나 이미 닫힘: {exc}")


def submit_kakao_auth_request(page, dialog_messages: list[str], timeout_ms: int) -> None:
    print("[step] Kakao 인증요청 클릭")
    dialog_index = len(dialog_messages)
    root = _kakao_form_root(page)
    common.scroll_to_page_bottom(page)
    auth_req = common.first_visible_locator(
        root.get_by_role("button", name=re.compile(r"^\s*인증\s*요청\s*$|^\s*인증요청\s*$")),
        "Kakao 인증요청 버튼",
    )
    common.click_with_log(auth_req, "Click Kakao 인증요청")
    dismiss_kakao_auth_request_alert(page, timeout_ms)
    common.wait_timeout_with_log(page, 1000, "Post-Kakao-request settle")
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "Kakao verification request")


def click_kakao_auth_complete(page, dialog_messages: list[str], timeout_ms: int) -> None:
    """카카오톡 인증 완료 후 활성화되는 '인증확인'을 눌러 로그인을 마친다."""
    print("[step] Kakao 인증확인 클릭")
    dialog_index = len(dialog_messages)
    root = _kakao_form_root(page)
    common.scroll_to_page_bottom(page)
    complete_btn = _kakao_auth_confirm_button(root)
    common.wait_locator_visible_with_log(complete_btn, timeout_ms, "Kakao 인증확인 버튼 표시")
    common.wait_function_with_log(
        page,
        KAKAO_AUTH_CONFIRM_ENABLED_JS,
        timeout_ms,
        "Kakao 인증확인 버튼 활성화 (카카오톡 앱 인증 완료 대기)",
    )
    common.click_with_log(complete_btn, "Click Kakao 인증확인")
    common.wait_timeout_with_log(page, 1000, "Post-Kakao-인증확인 settle")
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "Kakao 인증확인")


def complete_after_background_wait(
    page,
    config: common.LoginConfig,
    dialog_messages: list[str],
    screenshot_path: Path,
) -> str:
    common.wait_timeout_with_log(
        page,
        KAKAO_AUTH_BACKGROUND_WAIT_MS,
        "Kakao톡 인증 진행 시간 (60초) — 인증요청 후 사용자가 앱에서 인증할 때까지 대기",
    )
    click_kakao_auth_complete(page, dialog_messages, config.timeout_ms)
    common.wait_for_login_success(page, config, dialog_messages)
    common.save_screenshot(page, screenshot_path)
    return f"카카오 로그인 성공: {page.url}"


def run(page, config: common.LoginConfig, dialog_messages: list[str], screenshot_path: Path) -> str:
    open_kakao_login_page(page)
    fill_kakao_form(page, config)
    _ensure_kakao_consents(page)
    submit_kakao_auth_request(page, dialog_messages, config.timeout_ms)
    return complete_after_background_wait(page, config, dialog_messages, screenshot_path)
