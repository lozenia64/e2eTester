from __future__ import annotations

import re
from pathlib import Path

import mhm_login_common as common

# 카카오톡에서 사용자 인증을 마칠 시간을 주기 위해 '인증요청' 후 이 시간만큼 대기한 뒤 '인증완료'를 누른다.
KAKAO_AUTH_BACKGROUND_WAIT_MS = 20_000

LOGIN_HUB_URL_FRAGMENT = "/util/login/login.do"
KAKAO_POPUP_SELECTOR = "#uiPOPKakaoLogin"


def _visible_kakao_popup(page):
    popup = page.locator(KAKAO_POPUP_SELECTOR)
    common.wait_locator_visible_with_log(popup, common.MAX_TIMEOUT_MS, "카카오 인증 팝업")
    return popup


def _wait_for_kakao_required_consents(page, timeout_ms: int, reason: str) -> None:
    common.wait_function_with_log(
        page,
        """
        () => {
            const popup = document.querySelector('#uiPOPKakaoLogin');
            const whole = popup?.querySelector('#formChkAll');
            const agree1 = popup?.querySelector('#kakaoChkAgree1_1');
            const agree2 = popup?.querySelector('#kakaoChkAgree2_1');
            return Boolean(whole?.checked && agree1?.checked && agree2?.checked);
        }
        """,
        timeout_ms,
        reason,
    )


def open_kakao_identity_popup(page) -> None:
    """로그인 허브에서 카카오 인증 카드의 로그인 링크를 눌러 팝업을 연다."""
    if LOGIN_HUB_URL_FRAGMENT not in page.url:
        print(f"[warn] 로그인 허브 URL이 아닐 수 있음 (기대: …{LOGIN_HUB_URL_FRAGMENT}): {page.url}")

    login_cta = page.locator('a[href="#uiPOPKakaoLogin"]').first
    try:
        common.wait_locator_visible_with_log(login_cta, common.MAX_TIMEOUT_MS, "카카오 탭 — 로그인 링크")
        common.click_with_log(login_cta, "카카오 인증 탭 — 로그인 링크")
    except Exception:
        fallback = page.locator(
            'li:has-text("카카오 인증") a[href="#uiPOPKakaoLogin"], a[href="#uiPOPKakaoLogin"]'
        ).first
        try:
            common.wait_locator_visible_with_log(fallback, common.MAX_TIMEOUT_MS, "카카오 탭 로그인 CTA (fallback)")
            common.click_with_log(fallback, "카카오 인증 탭 — 로그인 (fallback)")
        except Exception as exc2:
            raise RuntimeError(
                "login.do에서 카카오 인증 영역의 로그인 CTA를 찾지 못했습니다. "
                "페이지 구조가 바뀌었을 수 있습니다."
            ) from exc2

    _visible_kakao_popup(page)
    common.wait_timeout_with_log(page, 300, "카카오 본인정보 입력 팝업 안정화 대기")


def _ensure_kakao_consents(page) -> None:
    """카카오 팝업에서 전체동의를 눌러 필수 2개 항목을 동의 상태로 맞춘다."""
    print("[step] Kakao 필수 동의")
    popup = _visible_kakao_popup(page)
    common.scroll_to_page_bottom(page)

    whole_label = popup.locator('label[for="formChkAll"]').first
    common.wait_locator_visible_with_log(whole_label, common.MAX_TIMEOUT_MS, "Kakao 전체동의 라벨")
    common.click_with_log(whole_label, "Kakao 전체동의")

    try:
        _wait_for_kakao_required_consents(page, 3000, "Kakao 전체동의 반영")
        return
    except Exception:
        pass

    for field_id, description in (
        ("kakaoChkAgree1_1", "Kakao 개인(신용)정보 수집·이용 동의"),
        ("kakaoChkAgree2_1", "Kakao 개인(신용)정보 제3자 제공 동의"),
    ):
        agree_label = popup.locator(f'label[for="{field_id}"]').first
        common.wait_locator_visible_with_log(agree_label, common.MAX_TIMEOUT_MS, description)
        common.click_with_log(agree_label, description)

    _wait_for_kakao_required_consents(page, common.MAX_TIMEOUT_MS, "Kakao 필수 동의 최종 확인")


def fill_kakao_form(page, config: common.LoginConfig) -> None:
    """카카오 팝업 필드는 숨김 템플릿과 id가 겹칠 수 있어, 반드시 *표시 중* 칸만 채운다 (접근성 이름 기준)."""
    print("[step] Fill Kakao auth form (이름, 생년월일, 휴대폰)")
    popup = _visible_kakao_popup(page)

    name_f = common.first_visible_locator(popup.get_by_role("textbox", name="이름"), "Kakao 팝업 이름")
    common.click_with_log(name_f, "Kakao 이름 입력란")
    name_f.fill(config.name)

    birth_f = common.first_visible_locator(popup.get_by_role("textbox", name="생년월일"), "Kakao 팝업 생년월일")
    common.click_with_log(birth_f, "Kakao 생년월일 입력란")
    birth_f.fill(config.birthdate)

    common.fill_kakao_phone_segments(page, config, scope=popup)


def submit_kakao_auth_request(page, dialog_messages: list[str], timeout_ms: int) -> None:
    print("[step] Kakao 인증요청 클릭")
    dialog_index = len(dialog_messages)
    popup = _visible_kakao_popup(page)
    common.scroll_to_page_bottom(page)
    try:
        auth_req = popup.locator("#kakaoSignReq")
        common.wait_locator_visible_with_log(auth_req, common.MAX_TIMEOUT_MS, "Kakao 인증요청 링크")
        common.click_with_log(auth_req, "Click Kakao 인증요청 (link)")
    except Exception:
        btn = common.first_visible_locator(
            popup.get_by_role("button", name=re.compile(r"인증\s*요청|인증요청")),
            "Kakao 인증요청 버튼",
        )
        common.click_with_log(btn, "Click Kakao 인증요청 (button)")
    common.wait_timeout_with_log(page, 1000, "Post-Kakao-request settle")
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "Kakao verification request")


def click_kakao_auth_complete(page, dialog_messages: list[str], timeout_ms: int) -> None:
    """카카오톡 인증 안내 단계에서 '인증완료'를 눌러 다음 단계로 진행한다."""
    print("[step] Kakao 인증완료 클릭")
    dialog_index = len(dialog_messages)
    common.scroll_to_page_bottom(page)
    try:
        complete_btn = common.first_visible_locator(
            page.get_by_role("button", name=re.compile(r"^\s*인증\s*완료\s*$|^\s*인증완료\s*$")),
            "Kakao 인증완료 버튼",
        )
        common.click_with_log(complete_btn, "Click Kakao 인증완료 (button)")
    except Exception:
        try:
            complete_link = common.first_visible_locator(
                page.get_by_role("link", name=re.compile(r"^\s*인증\s*완료\s*$|^\s*인증완료\s*$")),
                "Kakao 인증완료 링크",
            )
            common.click_with_log(complete_link, "Click Kakao 인증완료 (link)")
        except Exception:
            fallback = common.first_visible_locator(
                page.locator(
                    'button:has-text("인증완료"), a:has-text("인증완료"), input[type="button"][value="인증완료"]'
                ),
                "Kakao 인증완료 (텍스트 매칭)",
            )
            common.click_with_log(fallback, "Click Kakao 인증완료 (fallback)")
    common.wait_timeout_with_log(page, 1000, "Post-Kakao-인증완료 settle")
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "Kakao 인증완료")


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
    open_kakao_identity_popup(page)
    fill_kakao_form(page, config)
    _ensure_kakao_consents(page)
    submit_kakao_auth_request(page, dialog_messages, config.timeout_ms)
    return complete_after_background_wait(page, config, dialog_messages, screenshot_path)
