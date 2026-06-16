from __future__ import annotations

import re

from . import compensation_result_common as result_common
from . import login_common as common

CANCEL_CONFIRM_TEXT = "접수를 취소하시겠습니까?"
CANCEL_SUCCESS_TEXT = re.compile(r"정상\s*처리\s*되었습니다")
ALERT_DIALOG_SELECTOR = ".dialog.modal.alert.show, .dialog.show"
FORBIDDEN_CANCELLED_DETAIL_BUTTONS = (
    re.compile(r"접수\s*취소"),
)


def _click_alert_dialog_button(
    page,
    dialog_text: str | re.Pattern[str],
    button_name: str,
    log_label: str,
    timeout_ms: int,
) -> None:
    dialog = page.locator(ALERT_DIALOG_SELECTOR).filter(has_text=dialog_text).first
    common.wait_locator_visible_with_log(dialog, timeout_ms, log_label)
    button = dialog.get_by_role("button", name=button_name, exact=True).first
    common.click_with_log(button, log_label)


def _cancel_claim_and_return_list(page, timeout_ms: int) -> None:
    cancel_button = common.first_visible_locator(
        page.locator(result_common.DETAIL_CANCEL_SELECTOR),
        "상세 화면 접수취소",
    )
    common.click_with_log(cancel_button, "상세 화면 접수취소 클릭")

    _click_alert_dialog_button(page, CANCEL_CONFIRM_TEXT, "예", "접수취소 확인(예)", timeout_ms)
    _click_alert_dialog_button(page, CANCEL_SUCCESS_TEXT, "확인", "접수취소 완료 확인", timeout_ms)

    result_common.wait_url_contains(page, result_common.RESULT_LIST_URL_FRAGMENT, timeout_ms)


def _assert_receipt_absent_in_processing(page, timeout_ms: int, receipt_number: str) -> None:
    result_common.select_results_tab(page, result_common.ING_TAB_SELECTOR, "진행중", timeout_ms)
    cards = result_common.claim_cards(page)

    for _ in range(max(1, timeout_ms // 400)):
        present = False
        for index in range(cards.count()):
            card = cards.nth(index)
            try:
                if not card.is_visible(timeout=400):
                    continue
                card_text = result_common.normalize_text(card.inner_text(timeout=400))
            except Exception:
                continue
            if receipt_number in card_text:
                present = True
                break

        if not present:
            try:
                empty_message = page.get_by_text(result_common.EMPTY_PROCESSING_MESSAGE).first
                if empty_message.is_visible(timeout=400):
                    print(f"[step] 진행중 탭 빈 목록 확인 (접수번호 {receipt_number} 없음)")
                    return
            except Exception:
                pass
            print(f"[step] 진행중 탭에서 취소된 접수번호 제거 확인: {receipt_number}")
            return

        common.wait_timeout_with_log(page, 400, "진행중 탭 반영 대기")
    raise RuntimeError(f"진행중 탭에 취소된 접수번호가 여전히 남아 있습니다: {receipt_number}")


def _assert_cancelled_detail(page, timeout_ms: int) -> None:
    heading = page.get_by_role("heading", name=result_common.CANCELLED_DETAIL_HEADING).first
    common.wait_locator_visible_with_log(heading, timeout_ms, "취소된 청구 상세")

    for pattern in FORBIDDEN_CANCELLED_DETAIL_BUTTONS:
        button = page.get_by_role("button", name=pattern).first
        try:
            if button.is_visible(timeout=500):
                label = result_common.normalize_text(button.inner_text(timeout=500))
                raise RuntimeError(f"취소된 상세에 {label} 버튼이 노출됩니다")
        except RuntimeError:
            raise
        except Exception:
            continue

    common.wait_locator_visible_with_log(
        page.get_by_role("button", name=result_common.DETAIL_PREVIEW_BUTTON_PATTERN),
        timeout_ms,
        "취소된 청구 상세 제출서류 확인하기",
    )
    common.wait_locator_visible_with_log(
        page.get_by_role("button", name="동일내용 다시청구"),
        timeout_ms,
        "취소된 청구 상세 동일내용 다시청구",
    )
    print("[step] 취소된 청구 상세 화면 검증 완료")


def _assert_cancelled_in_finished_tab(page, timeout_ms: int, receipt_number: str) -> None:
    result_common.select_results_tab(page, result_common.FIN_TAB_SELECTOR, "완료", timeout_ms)
    card = result_common.find_card_by_receipt_number(page, receipt_number, timeout_ms)
    card_text = result_common.normalize_text(card.inner_text(timeout=1000))
    if result_common.TARGET_CLAIM_TEXT_TRUNCATED not in card_text:
        raise RuntimeError(f"완료 탭 청구내용이 예상과 다릅니다: {card_text}")
    if not result_common.card_has_cancelled_status(card):
        raise RuntimeError(f"완료 탭 상태값이 취소가 아닙니다: {card_text}")

    result_common.open_claim_detail(page, card, timeout_ms)
    _assert_cancelled_detail(page, timeout_ms)


def run(page, config: common.LoginConfig) -> str:
    result_common.goto_result01(page, config)
    result_common.select_results_tab(page, result_common.ING_TAB_SELECTOR, "진행중", config.timeout_ms)
    row = result_common.find_processing_claim_row(page, config.timeout_ms)
    receipt_number = result_common.receipt_number_from_row(row)
    result_common.open_claim_detail(page, row, config.timeout_ms)
    result_common.wait_for_result02_detail_ready(page, config.timeout_ms, receipt_number)
    _cancel_claim_and_return_list(page, config.timeout_ms)
    _assert_receipt_absent_in_processing(page, config.timeout_ms, receipt_number)
    _assert_cancelled_in_finished_tab(page, config.timeout_ms, receipt_number)
    return f"보험금청구 취소 성공 ({receipt_number})"
