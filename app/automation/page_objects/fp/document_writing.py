from __future__ import annotations

import math
import re

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.runner.step_logging import log
from app.systems.access_common import browser

CONTRACT_WRITE_PAGE_PATH = "/fp/loan/sales02.do"
DOCUMENT_COMPLETE_PAGE_PATH = "/fp/loan/sales03.do"

INFORMATION_SECURITY_PLEDGE_FORM_LABEL = "(신)정보보호서약서_설계사대리점"
FORM_COMPLETE_TEXT = "작성완료"

AUTH_BUTTON = "#btnSaveCert"
SMS_REQUEST_LINK = "#btnSendAuth"
OTP_INPUT = "#smsCertNo"
SUBMIT_BUTTON = "#btnSave"
PHONE_CERT_SECTION = "#phoneCert"

OZ_POPUP_URL_FRAGMENT = "sales02_oz.jsp"
OZ_SUBMIT_BUTTON = "#btnSaveCert"
OZ_DOCUMENT_CANVAS_INDEX = 1
SIGNATURE_CANVAS_INDEX = 2
OZ_CANVAS_POLL_INTERVAL_MS = 500
OZ_CANVAS_POLL_MAX = 40

OZ_SIGNATURE_RADIUS_RATIO = 0.35
OZ_READ_SIGN_STATE_JS = """
() => {
  const oz = document.getElementById('OZViewer');
  if (!oz) {
    return { signLen: 0, validity: '' };
  }
  const parsed = JSON.parse(oz.GetInformation('INPUT_JSON') || '{}');
  return {
    signLen: (parsed.sign || '').length,
    validity: oz.GetInformation('INPUT_CHECK_VALIDITY') || '',
  };
}
"""
HP_SMS_REQUEST_PATH = "hp-sms-request.json"
OZ_POPUP_OPEN_SETTLE_MS = 10_000
FORM_SUBMIT_SETTLE_MS = 10_000
OZ_POPUP_TIMEOUT_MS = 60_000

OTP_PATTERN = re.compile(r"^\d{4,8}$")

FAILURE_DIALOG_KEYWORDS: tuple[str, ...] = (
    "오류",
    "실패",
    "지연",
    "다시 시도",
    "넣어주세요",
    "입력해",
    "서명해",
)


def _new_dialogs(dialog_messages: list[str], start_index: int) -> list[str]:
    return dialog_messages[start_index:]


def _ensure_no_failure_dialogs(
    dialog_messages: list[str], start_index: int, step_name: str
) -> None:
    failures = [
        message
        for message in _new_dialogs(dialog_messages, start_index)
        if any(keyword in message for keyword in FAILURE_DIALOG_KEYWORDS)
    ]
    if failures:
        joined = " | ".join(failures)
        raise RuntimeError(f"{step_name} 실패: {joined}")


def _resolve_otp_code(otp_code: str) -> str:
    candidate = (otp_code or "").strip()
    if not OTP_PATTERN.fullmatch(candidate):
        raise RuntimeError("인증번호는 4~8자리 숫자여야 합니다.")
    return candidate


def _ensure_contract_write_page(page: Page, base_url: str) -> None:
    if CONTRACT_WRITE_PAGE_PATH in page.url:
        log(f"[wait] Reuse contract write page: {page.url}")
        return
    target = f"{browser.normalize_base_url(base_url, base_url)}{CONTRACT_WRITE_PAGE_PATH}"
    log(f"[step] Open contract write page: {target}")
    page.goto(target, wait_until="domcontentloaded", timeout=browser.MAX_TIMEOUT_MS)
    page.wait_for_url(
        lambda url: CONTRACT_WRITE_PAGE_PATH in url,
        timeout=browser.MAX_TIMEOUT_MS,
    )
    log(f"[wait] Contract write page ready: {page.url}")


def _dismiss_oz_jquery_dialog(popup: Page) -> None:
    confirm = popup.locator(".ui-dialog-buttonpane button").filter(has_text="확인")
    try:
        if confirm.count() > 0 and confirm.first.is_visible():
            log("[step] Dismiss OZ form dialog (확인)")
            confirm.first.click()
    except PlaywrightTimeoutError:
        return


def _wait_for_oz_form_ready(popup: Page) -> None:
    """OZ 뷰어는 양식 본문을 canvas로 그리므로 DOM 텍스트 대신 canvas·제출 버튼을 확인한다."""
    log("[step] Verify OZ form viewer ready (document canvas + signature pad)")
    popup.wait_for_load_state("load", timeout=OZ_POPUP_TIMEOUT_MS)
    popup.locator(OZ_SUBMIT_BUTTON).wait_for(
        state="visible",
        timeout=OZ_POPUP_TIMEOUT_MS,
    )
    document_canvas = popup.locator("canvas").nth(OZ_DOCUMENT_CANVAS_INDEX)
    signature_canvas = popup.locator("canvas").nth(SIGNATURE_CANVAS_INDEX)
    document_canvas.wait_for(state="visible", timeout=OZ_POPUP_TIMEOUT_MS)
    signature_canvas.wait_for(state="visible", timeout=OZ_POPUP_TIMEOUT_MS)

    for attempt in range(1, OZ_CANVAS_POLL_MAX + 1):
        doc_box = document_canvas.bounding_box()
        sig_box = signature_canvas.bounding_box()
        if (
            doc_box
            and doc_box["width"] > 100
            and doc_box["height"] > 100
            and sig_box
            and sig_box["width"] > 20
            and sig_box["height"] > 10
        ):
            log(
                "[wait] OZ canvases ready: "
                f"doc {int(doc_box['width'])}x{int(doc_box['height'])}, "
                f"sign {int(sig_box['width'])}x{int(sig_box['height'])}"
            )
            return
        if attempt == OZ_CANVAS_POLL_MAX:
            raise RuntimeError("정보보호서약서 양식 canvas가 로드되지 않았습니다.")
        popup.wait_for_timeout(OZ_CANVAS_POLL_INTERVAL_MS)


def _verify_oz_signature_registered(popup: Page) -> None:
    state = popup.evaluate(OZ_READ_SIGN_STATE_JS)
    sign_len = int(state.get("signLen") or 0)
    validity = str(state.get("validity") or "")
    if validity == "valid" and sign_len > 0:
        log(f"[wait] OZ signature registered (validity=valid, signLen={sign_len})")
        return
    raise RuntimeError(
        "정보보호서약서 서명이 OZ 뷰어에 등록되지 않았습니다. "
        f"validity={validity!r}, signLen={sign_len}"
    )


def _draw_circle_signature(popup: Page) -> None:
    """OZ 서명란은 overlay canvas(index 2)에 trusted mouse 로 그려야 INPUT_JSON.sign 이 채워진다."""
    signature_canvas = popup.locator("canvas").nth(SIGNATURE_CANVAS_INDEX)
    log("[step] Scroll OZ signature pad into view")
    signature_canvas.scroll_into_view_if_needed()
    popup.wait_for_timeout(500)
    box = signature_canvas.bounding_box()
    if not box:
        raise RuntimeError("정보보호서약서 서명란 canvas를 찾지 못했습니다.")
    center_x = box["width"] / 2
    center_y = box["height"] / 2
    radius = min(box["width"], box["height"]) * OZ_SIGNATURE_RADIUS_RATIO
    log(
        "[step] Draw O-shaped signature on OZ signature pad "
        f"(viewport {int(box['x'])},{int(box['y'])} {int(box['width'])}x{int(box['height'])})"
    )
    signature_canvas.focus()
    popup.mouse.move(box["x"] + center_x + radius, box["y"] + center_y)
    popup.mouse.down()
    steps = max(16, int((2 * math.pi) / 0.2))
    for step in range(steps + 1):
        angle = step * (2 * math.pi / steps)
        popup.mouse.move(
            box["x"] + center_x + radius * math.cos(angle),
            box["y"] + center_y + radius * math.sin(angle),
        )
    popup.mouse.up()
    popup.wait_for_timeout(500)
    _verify_oz_signature_registered(popup)


def _resolve_information_security_pledge_row(page: Page) -> tuple[Locator, Locator]:
    """양식명으로 계약서 작성 목록 행을 찾고 양식보기·상태 셀을 반환한다."""
    log(f"[step] Find form row by label: {INFORMATION_SECURITY_PLEDGE_FORM_LABEL!r}")
    target_row = page.locator("tr").filter(has_text=INFORMATION_SECURITY_PLEDGE_FORM_LABEL).first
    try:
        target_row.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        raise RuntimeError(
            f"{INFORMATION_SECURITY_PLEDGE_FORM_LABEL!r} 양식 행을 찾지 못했습니다."
        ) from None

    view_button = target_row.locator("[id^='btnGroup']").first
    status_cell = target_row.locator("[id^='check']").first
    try:
        view_button.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
        status_cell.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        raise RuntimeError(
            f"{INFORMATION_SECURITY_PLEDGE_FORM_LABEL!r} 행에서 "
            "양식보기 버튼 또는 상태 셀을 찾지 못했습니다."
        ) from None

    btn_id = view_button.get_attribute("id") or ""
    check_id = status_cell.get_attribute("id") or ""
    log(f"[wait] Resolved form row controls: view={btn_id!r}, status={check_id!r}")
    return view_button, status_cell


def _open_and_submit_information_security_pledge(page: Page) -> None:
    view_button, _ = _resolve_information_security_pledge_row(page)
    log(f"[step] Open form view: {INFORMATION_SECURITY_PLEDGE_FORM_LABEL!r}")
    view_button.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)

    with page.context.expect_page(timeout=OZ_POPUP_TIMEOUT_MS) as popup_info:
        view_button.click()
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=OZ_POPUP_TIMEOUT_MS)
    log(f"[wait] Settle after form view open ({OZ_POPUP_OPEN_SETTLE_MS} ms)")
    popup.wait_for_timeout(OZ_POPUP_OPEN_SETTLE_MS)
    if OZ_POPUP_URL_FRAGMENT not in popup.url:
        raise RuntimeError(f"정보보호서약서 양식 탭 URL이 예상과 다릅니다: {popup.url}")
    log(f"[wait] OZ form popup ready: {popup.url}")
    _wait_for_oz_form_ready(popup)
    _draw_circle_signature(popup)
    log("[step] Submit OZ form (제출하기)")
    popup.locator(OZ_SUBMIT_BUTTON).click()
    popup.wait_for_timeout(1500)
    _dismiss_oz_jquery_dialog(popup)

    try:
        popup.wait_for_event("close", timeout=OZ_POPUP_TIMEOUT_MS)
        log("[wait] OZ form popup closed")
    except PlaywrightTimeoutError:
        if not popup.is_closed():
            log("[warn] OZ popup still open after submit; continue on main page")
            try:
                popup.close()
            except Exception:
                pass


def _wait_for_form_complete(page: Page) -> None:
    log(f"[wait] Settle after OZ submit ({FORM_SUBMIT_SETTLE_MS} ms)")
    page.wait_for_timeout(FORM_SUBMIT_SETTLE_MS)
    _, status = _resolve_information_security_pledge_row(page)
    status.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    text = (status.text_content() or "").strip()
    log(f"[step] Verify form status cell: {text!r}")
    if FORM_COMPLETE_TEXT not in text:
        raise RuntimeError(
            f"{INFORMATION_SECURITY_PLEDGE_FORM_LABEL!r} 상태가 "
            f"{FORM_COMPLETE_TEXT!r} 가 아닙니다: {text!r}"
        )


def _open_phone_auth_section(page: Page, dialog_messages: list[str]) -> None:
    log("[step] Open phone authentication (인증하기)")
    dialog_index = len(dialog_messages)
    page.locator(AUTH_BUTTON).click()
    page.wait_for_timeout(500)
    _ensure_no_failure_dialogs(dialog_messages, dialog_index, "인증하기")
    page.locator(PHONE_CERT_SECTION).wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )
    log("[wait] Phone authentication section visible")


def _request_sms_code(page: Page, dialog_messages: list[str]) -> None:
    log("[step] Request SMS verification code")
    dialog_index = len(dialog_messages)
    sms_link = page.locator(SMS_REQUEST_LINK)
    sms_link.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    timeout_ms = browser.MAX_TIMEOUT_MS
    log(f"[wait] Start response wait: {HP_SMS_REQUEST_PATH} ({timeout_ms} ms)")
    with page.expect_response(
        lambda response: HP_SMS_REQUEST_PATH in response.url,
        timeout=timeout_ms,
    ) as sms_info:
        sms_link.click()

    sms_response = sms_info.value
    log(
        f"[wait] End response wait: {HP_SMS_REQUEST_PATH} -> "
        f"{sms_response.status} {sms_response.url}"
    )
    if not sms_response.ok:
        detail = (
            _new_dialogs(dialog_messages, dialog_index)[-1]
            if len(dialog_messages) > dialog_index
            else f"HTTP {sms_response.status}"
        )
        raise RuntimeError(f"SMS 인증번호 요청 실패({HP_SMS_REQUEST_PATH}): {detail}")

    _ensure_no_failure_dialogs(dialog_messages, dialog_index, "SMS 인증번호 요청")
    page.wait_for_timeout(1000)

    otp_input = page.locator(OTP_INPUT)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    if not otp_input.is_enabled():
        raise RuntimeError("인증번호 입력란이 비활성 상태입니다. SMS 발급을 다시 시도해 주세요.")
    log("[wait] SMS auth input ready")


def _wait_for_document_complete_page(page: Page) -> None:
    log(f"[wait] Start document complete page wait: {DOCUMENT_COMPLETE_PAGE_PATH}")
    page.wait_for_url(
        lambda url: DOCUMENT_COMPLETE_PAGE_PATH in url,
        timeout=OZ_POPUP_TIMEOUT_MS,
    )
    log(f"[wait] Document complete page ready: {page.url}")


def request_otp(
    page: Page,
    *,
    base_url: str,
    dialog_messages: list[str],
) -> str:
    """계약서 작성 화면에서 정보보호서약서 제출 후 휴대폰 인증번호를 요청한다."""
    browser.maybe_close_popup(page)
    _ensure_contract_write_page(page, base_url)
    _open_and_submit_information_security_pledge(page)
    _wait_for_form_complete(page)
    _open_phone_auth_section(page, dialog_messages)
    _request_sms_code(page, dialog_messages)
    return "휴대폰 인증문자 발송 성공"


def submit_otp_and_complete(
    page: Page,
    *,
    otp_code: str,
    dialog_messages: list[str],
) -> str:
    """인증번호 입력 후 제출하여 작성완료 화면까지 진행한다."""
    if CONTRACT_WRITE_PAGE_PATH not in page.url:
        raise RuntimeError(
            "계약서 작성 화면(/fp/loan/sales02.do)이 아닙니다. 이전 모듈부터 다시 실행해 주세요."
        )

    resolved = _resolve_otp_code(otp_code)
    log("[step] Submit SMS verification code and complete documents")
    otp_input = page.locator(OTP_INPUT)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    otp_input.fill(resolved)

    dialog_index = len(dialog_messages)
    page.locator(SUBMIT_BUTTON).click()

    try:
        _wait_for_document_complete_page(page)
    except PlaywrightTimeoutError:
        _ensure_no_failure_dialogs(dialog_messages, dialog_index, "서류 작성 제출")
        if dialog_messages:
            raise RuntimeError(f"서류 작성 제출 실패: {dialog_messages[-1]}")
        raise RuntimeError(
            f"서류 작성 완료 화면({DOCUMENT_COMPLETE_PAGE_PATH})으로 이동하지 못했습니다."
        )

    _ensure_no_failure_dialogs(dialog_messages, dialog_index, "서류 작성 제출")
    return "FP 서류작성 성공"
