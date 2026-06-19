from __future__ import annotations

import re
from typing import Literal

from app.scenarios.rep_homepage.constants import (
    KAKAO_AUTH_BACKGROUND_WAIT_MS,
    KAKAO_AUTH_MAX_ATTEMPTS,
    is_kakao_auth_incomplete_message,
)

from . import login_common as common

LOGIN_HUB_URL_FRAGMENT = "/util/login/login.do"
KAKAO_POPUP_SELECTOR = "#uiPOPKakaoLogin"
KAKAO_RESULT_MODAL_SELECTOR = "#uiPOPKakaoLoginResult"
KAKAO_AUTH_REQUEST_SELECTOR = "#kakaoSignReq"
KAKAO_AUTH_RESEND_SELECTOR = "#sendKakaoCertf"
KAKAO_AUTH_COMPLETE_RESULT_SELECTOR = "#signReqRes"

KakaoAuthResult = Literal["success", "incomplete", "fatal"]


def _kakao_result_modal(page):
    return page.locator(KAKAO_RESULT_MODAL_SELECTOR)


def _is_kakao_result_modal_open(page) -> bool:
    modal = _kakao_result_modal(page)
    try:
        return modal.is_visible(timeout=500)
    except Exception:
        return False


def _kakao_popup(page):
    return page.locator(KAKAO_POPUP_SELECTOR)


def _visible_kakao_popup(page):
    popup = _kakao_popup(page)
    common.wait_locator_visible_with_log(popup, common.MAX_TIMEOUT_MS, "카카오 인증 팝업")
    return popup


def _ensure_kakao_popup_visible(page):
    """카카오 입력 팝업이 숨김이면 로그인 CTA를 다시 눌러 연다 (초기 진입 복구용).

    인증요청 후에는 `#uiPOPKakaoLoginResult` 가 열리므로, 재시도는 `_find_visible_kakao_auth_request` 가
    그 안의 `#sendKakaoCertf`(인증재요청)를 사용한다. Result 모달이 열려 있을 때 login CTA를 누르면 클릭이 가로막힌다.
    """
    if _is_kakao_result_modal_open(page):
        raise RuntimeError(
            "카카오 인증 결과 모달이 열려 있으나 인증재요청 버튼을 찾지 못했습니다."
        )

    popup = _kakao_popup(page)
    try:
        if popup.is_visible(timeout=500):
            return popup
    except Exception:
        pass

    print("[step] Kakao 인증 팝업 재오픈 (재시도)")
    login_cta = page.locator('a[href="#uiPOPKakaoLogin"]').first
    try:
        common.wait_locator_visible_with_log(login_cta, common.MAX_TIMEOUT_MS, "카카오 탭 — 로그인 링크")
        common.click_with_log(login_cta, "카카오 인증 팝업 재오픈")
    except Exception:
        fallback = page.locator(
            'li:has-text("카카오 인증") a[href="#uiPOPKakaoLogin"], a[href="#uiPOPKakaoLogin"]'
        ).first
        common.wait_locator_visible_with_log(fallback, common.MAX_TIMEOUT_MS, "카카오 탭 로그인 CTA (fallback)")
        common.click_with_log(fallback, "카카오 인증 팝업 재오픈 (fallback)")

    common.wait_locator_visible_with_log(popup, common.MAX_TIMEOUT_MS, "카카오 인증 팝업")
    common.wait_timeout_with_log(page, 300, "카카오 인증 팝업 재오픈 안정화 대기")
    return popup


def _find_visible_kakao_auth_request(page):
    """팝업·결과 모달·페이지 전역에서 보이는 인증요청/인증재요청 컨트롤을 찾는다."""
    if _is_kakao_result_modal_open(page):
        try:
            resend = page.locator(KAKAO_AUTH_RESEND_SELECTOR).first
            if resend.is_visible(timeout=500):
                return resend
        except Exception:
            pass

    popup = _kakao_popup(page)
    scopes: list = []
    try:
        if popup.is_visible(timeout=500):
            scopes.append(popup)
    except Exception:
        pass
    scopes.append(page)

    for scope in scopes:
        try:
            auth_req = scope.locator(KAKAO_AUTH_REQUEST_SELECTOR).first
            if auth_req.is_visible(timeout=500):
                return auth_req
        except Exception:
            pass
        try:
            return common.first_visible_locator(
                scope.get_by_role("button", name=re.compile(r"인증\s*요청|인증요청")),
                "Kakao 인증요청 버튼",
            )
        except Exception:
            pass
        try:
            return common.first_visible_locator(
                scope.get_by_role("link", name=re.compile(r"인증\s*재?\s*요청|인증\s*요청|인증요청")),
                "Kakao 인증요청 링크",
            )
        except Exception:
            pass
    return None


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


def _is_kakao_resend_cooldown_dialog(message: str) -> bool:
    normalized = message.strip().replace(" ", "")
    return "재전송" in normalized and "60초" in normalized


def submit_kakao_auth_request(page, dialog_messages: list[str], timeout_ms: int) -> None:
    print("[step] Kakao 인증요청 클릭")
    dialog_index = len(dialog_messages)
    common.scroll_to_page_bottom(page)

    auth_req = _find_visible_kakao_auth_request(page)
    if auth_req is None:
        popup = _ensure_kakao_popup_visible(page)
        common.scroll_to_page_bottom(page)
        try:
            auth_req = popup.locator(KAKAO_AUTH_REQUEST_SELECTOR)
            common.wait_locator_visible_with_log(auth_req, common.MAX_TIMEOUT_MS, "Kakao 인증요청 링크")
        except Exception:
            auth_req = common.first_visible_locator(
                popup.get_by_role("button", name=re.compile(r"인증\s*요청|인증요청")),
                "Kakao 인증요청 버튼",
            )

    is_resend = _is_kakao_result_modal_open(page)
    common.click_with_log(
        auth_req,
        "Click Kakao 인증재요청" if is_resend else "Click Kakao 인증요청",
    )
    common.wait_timeout_with_log(page, 1000, "Post-Kakao-request settle")

    if is_resend:
        recent = common.get_new_dialogs(dialog_messages, dialog_index)
        if any(_is_kakao_resend_cooldown_dialog(message) for message in recent):
            print("[warn] 카카오 인증재요청 60초 제한 — 쿨다운 대기 후 재클릭")
            common.wait_timeout_with_log(page, 35_000, "카카오 인증재요청 쿨다운 (60초)")
            cooldown_index = len(dialog_messages)
            auth_req = _find_visible_kakao_auth_request(page)
            if auth_req is None:
                raise RuntimeError("카카오 인증재요청 버튼을 찾지 못했습니다.")
            common.click_with_log(auth_req, "Click Kakao 인증재요청 (cooldown 후)")
            common.wait_timeout_with_log(page, 1000, "Post-Kakao-resend settle")
            dialog_index = cooldown_index

    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "Kakao verification request")


def click_kakao_auth_complete(page) -> None:
    """카카오톡 인증 안내 단계에서 '인증완료'를 눌러 다음 단계로 진행한다."""
    print("[step] Kakao 인증완료 클릭")
    common.scroll_to_page_bottom(page)

    if _is_kakao_result_modal_open(page):
        try:
            complete_link = page.locator(KAKAO_AUTH_COMPLETE_RESULT_SELECTOR).first
            common.wait_locator_visible_with_log(complete_link, common.MAX_TIMEOUT_MS, "Kakao 인증완료 (#signReqRes)")
            common.click_with_log(complete_link, "Click Kakao 인증완료 (#signReqRes)")
            common.wait_timeout_with_log(page, 1000, "Post-Kakao-인증완료 settle")
            return
        except Exception:
            pass

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


def _check_kakao_auth_result(dialog_messages: list[str], start_index: int) -> KakaoAuthResult:
    new_dialogs = common.get_new_dialogs(dialog_messages, start_index)
    incomplete = [message for message in new_dialogs if is_kakao_auth_incomplete_message(message)]
    if incomplete:
        return "incomplete"
    failures = [
        message
        for message in new_dialogs
        if common.is_failure_dialog(message) and not is_kakao_auth_incomplete_message(message)
    ]
    if failures:
        joined = " | ".join(failures)
        raise RuntimeError(f"Kakao 인증완료 failed: {joined}")
    return "success"


def _try_kakao_auth_attempt(page, config: common.LoginConfig, dialog_messages: list[str]) -> bool:
    common.wait_timeout_with_log(
        page,
        KAKAO_AUTH_BACKGROUND_WAIT_MS,
        "Kakao톡 인증 진행 시간 (30초) — 인증요청 후 사용자가 앱에서 인증할 때까지 대기",
    )
    dialog_index = len(dialog_messages)
    click_kakao_auth_complete(page)
    result = _check_kakao_auth_result(dialog_messages, dialog_index)
    if result == "incomplete":
        print("[warn] 카카오 인증 미완료 — 재시도")
        return False
    return True


def run(page, config: common.LoginConfig, dialog_messages: list[str]) -> str:
    open_kakao_identity_popup(page)
    fill_kakao_form(page, config)
    _ensure_kakao_consents(page)

    for attempt in range(1, KAKAO_AUTH_MAX_ATTEMPTS + 1):
        print(f"[step] Kakao 인증 시도 {attempt}/{KAKAO_AUTH_MAX_ATTEMPTS}")
        submit_kakao_auth_request(page, dialog_messages, config.timeout_ms)
        if _try_kakao_auth_attempt(page, config, dialog_messages):
            break
        if attempt == KAKAO_AUTH_MAX_ATTEMPTS:
            raise RuntimeError(
                f"카카오 인증 {KAKAO_AUTH_MAX_ATTEMPTS}회 실패: 인증이 완료되지 않았습니다."
            )

    common.wait_for_login_success(page, config, dialog_messages)
    return f"카카오 로그인 성공: {page.url}"
