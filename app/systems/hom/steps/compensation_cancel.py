from __future__ import annotations

from . import compensation_result_common as result_common
from . import login_common as common

CANCELLED_STATUS = "취소"


def _attach_dialog_recorder(page) -> list[tuple[str, str]]:
    seen_dialogs: list[tuple[str, str]] = []

    def _record(dialog) -> None:
        seen_dialogs.append((dialog.type, dialog.message))

    page.on("dialog", _record)
    return seen_dialogs


def _cancel_claim_and_return_result01(
    page, timeout_ms: int, seen_dialogs: list[tuple[str, str]]
) -> None:
    cancel_button = common.first_visible_locator(
        page.locator(result_common.DETAIL_CANCEL_SELECTOR), "상세 화면 접수취소(#btn4)"
    )
    common.click_with_log(cancel_button, "상세 화면 접수취소 클릭")

    for _ in range(max(1, timeout_ms // 400)):
        if "result01.do" in page.url:
            break
        common.wait_timeout_with_log(page, 400, "접수취소 처리 대기")
    result_common.wait_url_contains(page, "result01.do", timeout_ms)

    if not any(
        dialog_type == "confirm" and "접수를 취소하시겠습니까?" in message
        for dialog_type, message in seen_dialogs
    ):
        raise RuntimeError(f"접수취소 confirm 대화상자를 확인하지 못했습니다: {seen_dialogs}")
    if not any(
        dialog_type == "alert" and "정상적으로 처리 되었습니다." in message
        for dialog_type, message in seen_dialogs
    ):
        raise RuntimeError(f"접수취소 완료 alert를 확인하지 못했습니다: {seen_dialogs}")


def _assert_receipt_absent_in_processing(page, timeout_ms: int, receipt_number: str) -> None:
    result_common.select_results_tab(page, result_common.ING_TAB_SELECTOR, "진행중", timeout_ms)
    table = result_common.result_table(page)
    rows = table.locator("tbody tr")

    for _ in range(max(1, timeout_ms // 400)):
        present = False
        for index in range(rows.count()):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=400):
                    continue
                row_text = result_common.normalize_text(row.inner_text(timeout=400))
            except Exception:
                continue
            if receipt_number in row_text:
                present = True
                break
        if not present:
            print(f"[step] 진행중 탭에서 취소된 접수번호 제거 확인: {receipt_number}")
            return
        common.wait_timeout_with_log(page, 400, "진행중 탭 반영 대기")
    raise RuntimeError(f"진행중 탭에 취소된 접수번호가 여전히 남아 있습니다: {receipt_number}")


def _find_row_by_receipt_number(page, receipt_number: str, timeout_ms: int):
    table = result_common.result_table(page)
    rows = table.locator("tbody tr")
    for _ in range(max(1, timeout_ms // 400)):
        for index in range(rows.count()):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=400):
                    continue
                row_text = result_common.normalize_text(row.inner_text(timeout=400))
            except Exception:
                continue
            if receipt_number in row_text:
                return row
        common.wait_timeout_with_log(page, 400, "완료 탭 결과 행 대기")
    raise RuntimeError(f"완료 탭에서 접수번호를 찾지 못했습니다: {receipt_number}")


def _assert_cancelled_in_finished_tab(page, timeout_ms: int, receipt_number: str) -> None:
    result_common.select_results_tab(page, result_common.FIN_TAB_SELECTOR, "완료", timeout_ms)
    row = _find_row_by_receipt_number(page, receipt_number, timeout_ms)
    row_text = result_common.normalize_text(row.inner_text(timeout=1000))
    if result_common.TARGET_CLAIM_TEXT_TRUNCATED not in row_text:
        raise RuntimeError(f"완료 탭 청구내용이 예상과 다릅니다: {row_text}")
    if CANCELLED_STATUS not in row_text:
        raise RuntimeError(f"완료 탭 상태값이 취소가 아닙니다: {row_text}")

    button_names = result_common.row_button_names(row)
    if button_names != ["제출서류확인"]:
        raise RuntimeError(f"완료 탭 이용가능 서비스가 예상과 다릅니다: {button_names}")


def run(page, config: common.LoginConfig) -> str:
    result_common.goto_result01(page, config)
    result_common.select_results_tab(
        page, result_common.ING_TAB_SELECTOR, "진행중", config.timeout_ms
    )
    row = result_common.find_processing_claim_row(page, config.timeout_ms)
    receipt_number = result_common.receipt_number_from_row(row)
    result_common.open_claim_detail(page, row, config.timeout_ms)
    result_common.wait_for_result02_detail_ready(page, config.timeout_ms, receipt_number)
    seen_dialogs = _attach_dialog_recorder(page)
    _cancel_claim_and_return_result01(page, config.timeout_ms, seen_dialogs)
    _assert_receipt_absent_in_processing(page, config.timeout_ms, receipt_number)
    _assert_cancelled_in_finished_tab(page, config.timeout_ms, receipt_number)
    return f"보험금청구 취소 성공 ({receipt_number})"
