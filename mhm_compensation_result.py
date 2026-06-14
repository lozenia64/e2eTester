from __future__ import annotations

from pathlib import Path
import re

import mhm_login_common as common
import mhm_compensation_result_common as result_common

PREVIEW_POPUP_FRAGMENT = "/fplaza/compensation/pop-result04.do"
PREVIEW_HEADING_PATTERN = re.compile(r"제출서류확인")
PREVIEW_LIST_ITEM_SELECTOR = "#listCont li"
PREVIEW_IMAGE_SELECTOR = "img[alt='등록파일']"
PREVIEW_ZIP_DOWNLOAD_SELECTOR = 'a[onclick="return zipDown();"]'
PREVIEW_POPUP_TIMEOUT_MS = 20000


def _assert_result02_detail(page, timeout_ms: int, expected_receipt_number: str) -> None:
    result_common.wait_url_contains(page, "result02.do", timeout_ms)
    detail_table = result_common.wait_for_result02_detail_ready(page, timeout_ms, expected_receipt_number)

    receipt_number = result_common.detail_value(page, detail_table, "접수번호")
    claim_date = result_common.detail_value(page, detail_table, "보험청구일자")
    accident_date = result_common.detail_value(page, detail_table, "사고(진단)일자")
    claim_type = result_common.detail_value(page, detail_table, "청구유형")
    claim_content = result_common.detail_value(page, detail_table, "청구내용")

    if receipt_number != expected_receipt_number:
        raise RuntimeError(f"상세 화면 접수번호 불일치: expected={expected_receipt_number}, actual={receipt_number}")
    if claim_date != result_common.today_display():
        raise RuntimeError(f"상세 화면 보험청구일자가 오늘 날짜가 아닙니다: {claim_date}")
    if not result_common.RESULT_DATE_PATTERN.fullmatch(accident_date):
        raise RuntimeError(f"상세 화면 사고(진단)일자를 확인하지 못했습니다: {accident_date}")
    if "기타" not in claim_type:
        raise RuntimeError(f"상세 화면 청구유형이 예상과 다릅니다: {claim_type}")
    if claim_content != result_common.TARGET_CLAIM_TEXT:
        raise RuntimeError(f"상세 화면 청구내용 불일치: {claim_content}")

    common.wait_locator_visible_with_log(
        page.locator(result_common.DETAIL_PREVIEW_SELECTOR), timeout_ms, "상세 화면 제출서류확인(#btn3)"
    )
    common.wait_locator_visible_with_log(
        page.locator(result_common.DETAIL_CANCEL_SELECTOR), timeout_ms, "상세 화면 접수취소(#btn4)"
    )


def _verify_preview_popup(page, receipt_number: str, timeout_ms: int) -> None:
    popup_timeout_ms = max(timeout_ms, PREVIEW_POPUP_TIMEOUT_MS)
    preview_button = common.first_visible_locator(
        page.locator(result_common.DETAIL_PREVIEW_SELECTOR), "상세 화면 제출서류확인(#btn3)"
    )
    with page.context.expect_page(timeout=popup_timeout_ms) as popup_info:
        common.click_with_log(preview_button, "상세 화면 제출서류확인 클릭")
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=popup_timeout_ms)
    result_common.wait_url_contains(popup, PREVIEW_POPUP_FRAGMENT, popup_timeout_ms)

    if PREVIEW_POPUP_FRAGMENT not in popup.url or f"conRcpNo={receipt_number}" not in popup.url:
        raise RuntimeError(f"제출서류확인 팝업 URL이 예상과 다릅니다: {popup.url}")

    heading = popup.get_by_role("heading", name=PREVIEW_HEADING_PATTERN).first
    common.wait_locator_visible_with_log(heading, popup_timeout_ms, "제출서류확인 팝업 heading")

    items = popup.locator(PREVIEW_LIST_ITEM_SELECTOR)
    item_count = items.count()
    if item_count < 2:
        raise RuntimeError(f"제출서류확인 팝업 파일 개수가 부족합니다: {item_count}")

    for index in range(2):
        item = items.nth(index)
        file_name = result_common.normalize_text(item.locator("strong").inner_text(timeout=1000))
        reg_date = result_common.normalize_text(item.locator("span").last.inner_text(timeout=1000))
        if not file_name:
            raise RuntimeError(f"팝업 파일명 확인 실패: index={index}")
        if "등록일" not in reg_date:
            raise RuntimeError(f"팝업 등록일 표시 확인 실패: index={index}, value={reg_date}")

        image = item.locator(PREVIEW_IMAGE_SELECTOR).first
        preview_meta = image.evaluate(
            """
            (element) => ({
                src: element.getAttribute('src') || '',
                naturalWidth: element.naturalWidth || 0,
                naturalHeight: element.naturalHeight || 0,
            })
            """
        )
        if "download-file.do" not in preview_meta["src"]:
            raise RuntimeError(f"이미지 미리보기 src가 예상과 다릅니다: {preview_meta['src']}")
        if preview_meta["naturalWidth"] <= 0 or preview_meta["naturalHeight"] <= 0:
            raise RuntimeError(
                f"이미지 미리보기를 확인하지 못했습니다: {file_name} ({preview_meta['naturalWidth']}x{preview_meta['naturalHeight']})"
            )

        with popup.expect_download(timeout=popup_timeout_ms) as download_info:
            common.click_with_log(item.locator("a").first, f"제출서류 다운로드 확인: {file_name}")
        download = download_info.value
        if not download.suggested_filename:
            raise RuntimeError(f"제출서류 다운로드 파일명을 확인하지 못했습니다: {file_name}")

    common.wait_locator_visible_with_log(
        popup.locator(PREVIEW_ZIP_DOWNLOAD_SELECTOR),
        popup_timeout_ms,
        "제출서류확인 팝업 전체 다운로드 버튼",
    )
    print("[step] 제출서류확인 팝업 검증 완료")
    popup.close()


def run(page, config: common.LoginConfig, screenshot_path: Path) -> str:
    try:
        result_common.goto_result01(page, config)
        result_common.select_results_tab(page, result_common.ING_TAB_SELECTOR, "진행중", config.timeout_ms)
        row = result_common.find_processing_claim_row(page, config.timeout_ms)
        receipt_number = result_common.receipt_number_from_row(row)
        result_common.open_claim_detail(page, row, config.timeout_ms)
        _assert_result02_detail(page, config.timeout_ms, receipt_number)
        _verify_preview_popup(page, receipt_number, config.timeout_ms)
        common.save_screenshot(page, screenshot_path)
        return f"보험금청구 결과 조회 성공 ({receipt_number})"
    except Exception:
        common.save_screenshot(page, screenshot_path)
        raise
