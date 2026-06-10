from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import hom_login_common as common

RESULT01_FRAGMENT = "/fplaza/compensation/result01.do"
RESULT02_FRAGMENT = "/fplaza/compensation/result02.do"
PREVIEW_POPUP_FRAGMENT = "/fplaza/compensation/pop-result04.do"
PREVIEW_HEADING_PATTERN = re.compile(r"제출서류확인")
PROCESSING_STATUS = "처리중"
CANCELLED_STATUS = "취소"
TARGET_CLAIM_TEXT = "IT직원 테스트입니다. 바로 취소할 예정입니다."
TARGET_CLAIM_TEXT_TRUNCATED = "IT직원 테스트입니다. 바로 취소할"
ING_TAB_SELECTOR = "#ing"
FIN_TAB_SELECTOR = "#fin"
DETAIL_PREVIEW_SELECTOR = "#btn3"
DETAIL_CANCEL_SELECTOR = "#btn4"
PREVIEW_LIST_ITEM_SELECTOR = "#listCont li"
PREVIEW_IMAGE_SELECTOR = "img[alt='등록파일']"
PREVIEW_ZIP_DOWNLOAD_SELECTOR = 'a[onclick="return zipDown();"]'
RESULT_DATE_PATTERN = re.compile(r"\d{4}\.\d{2}\.\d{2}")
RESULT_TABLE_CAPTION = "상해/질병/화재보험금 청구내역 목록"
DETAIL_TABLE_CAPTION = "사고접수내용 상세"
RESULT02_DETAIL_STABILIZE_MS = 2000
PREVIEW_POPUP_TIMEOUT_MS = 20000


def _wait_url_contains(page, fragment: str, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "f => window.location.href.includes(f)",
        arg=fragment,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _today_display() -> str:
    return date.today().strftime("%Y.%m.%d")


def _find_visible_table_by_caption(page, caption_text: str, description: str):
    tables = page.locator("table")
    table_count = tables.count()
    normalized_caption_text = _normalize_text(caption_text)

    for index in range(table_count):
        table = tables.nth(index)
        try:
            if not table.is_visible(timeout=800):
                continue
            caption = table.locator("caption").first
            if caption.count() == 0:
                continue
            actual_caption = _normalize_text(caption.inner_text(timeout=800))
        except Exception:
            continue
        if normalized_caption_text in actual_caption:
            return table

    raise RuntimeError(f"표시 중인 표를 찾지 못했습니다: {description}")


def _open_result01_from_menu(page, timeout_ms: int) -> bool:
    common.maybe_close_post_login_popup(page, timeout_ms)
    try:
        bosang = page.get_by_role("link", name=re.compile(r"^보상$")).first
        if not bosang.is_visible(timeout=2000):
            return False
        print("[step] Hover GNB 보상")
        bosang.hover(timeout=timeout_ms)
        common.wait_timeout_with_log(page, 600, "보상 메뉴 펼침 대기")
        link = common.first_visible_locator(
            page.locator(f'a[href*="{RESULT01_FRAGMENT}"]'),
            "보상 메뉴의 result01 링크",
        )
        with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
            common.click_with_log(link, "보상 > 보험금청구 결과 조회(result01) 메뉴 클릭")
        _wait_url_contains(page, "result01.do", timeout_ms)
        return True
    except Exception as exc:
        print(f"[warn] 메뉴로 result01 이동 실패, 직접 URL 시도: {exc}")
        return False


def _goto_result01(page, config: common.LoginConfig) -> None:
    if not _open_result01_from_menu(page, config.timeout_ms):
        common.maybe_close_post_login_popup(page, config.timeout_ms)
        base = config.base_url.rstrip("/")
        common.open_url(page, f"{base}{RESULT01_FRAGMENT}")
        _wait_url_contains(page, "result01.do", config.timeout_ms)


def _is_tab_active(page, selector: str) -> bool:
    return bool(
        page.evaluate(
            """
            (tabSelector) => {
                const tab = document.querySelector(tabSelector);
                if (!tab) {
                    return false;
                }
                return tab.closest('li')?.classList.contains('on') ?? false;
            }
            """,
            selector,
        )
    )


def _select_results_tab(page, selector: str, label: str, timeout_ms: int) -> None:
    tab = common.first_visible_locator(page.locator(selector), f"{label} 탭")
    if _is_tab_active(page, selector):
        print(f"[step] {label} 탭이 이미 활성 상태")
        return
    common.click_with_log(tab, f"{label} 탭 클릭")
    page.wait_for_function(
        """
        (tabSelector) => {
            const tab = document.querySelector(tabSelector);
            return !!tab && (tab.closest('li')?.classList.contains('on') ?? false);
        }
        """,
        arg=selector,
        timeout=timeout_ms,
    )
    common.wait_timeout_with_log(page, 400, f"{label} 탭 전환 반영 대기")


def _result_table(page):
    return _find_visible_table_by_caption(page, RESULT_TABLE_CAPTION, "상해/질병/화재보험금 청구내역 목록 표")


def _row_button_names(row) -> list[str]:
    try:
        return [_normalize_text(value) for value in row.locator("button").all_inner_texts() if _normalize_text(value)]
    except Exception:
        return []


def _find_processing_claim_row(page, timeout_ms: int):
    result_table = _result_table(page)
    rows = result_table.locator("tbody tr")
    today = _today_display()

    for _ in range(max(1, timeout_ms // 400)):
        row_count = rows.count()
        for index in range(row_count):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=800):
                    continue
                row_text = _normalize_text(row.inner_text(timeout=800))
            except Exception:
                continue
            if today not in row_text:
                continue
            if TARGET_CLAIM_TEXT_TRUNCATED not in row_text:
                continue
            if PROCESSING_STATUS not in row_text:
                continue
            button_names = set(_row_button_names(row))
            if {"제출서류확인", "접수취소"} - button_names:
                continue
            print(f"[step] 결과 목록 대상 행 선택: {row_text}")
            return row
        common.wait_timeout_with_log(page, 400, "결과 조회 목록 대상 행 대기")
    raise RuntimeError("오늘 접수된 취소 대상 보험금청구 결과 행을 찾지 못했습니다.")


def _receipt_number_from_row(row) -> str:
    link = common.first_visible_locator(row.get_by_role("link"), "결과 목록 접수번호 링크")
    receipt_number = _normalize_text(link.inner_text(timeout=1000))
    if not receipt_number:
        raise RuntimeError("결과 목록 행에서 접수번호를 읽지 못했습니다.")
    return receipt_number


def _open_claim_detail(page, row, timeout_ms: int) -> None:
    detail_link = common.first_visible_locator(row.get_by_role("link"), "결과 목록 상세 링크")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        common.click_with_log(detail_link, "결과 목록 접수번호 상세 조회")
    _wait_url_contains(page, "result02.do", timeout_ms)


def _detail_table(page):
    return _find_visible_table_by_caption(page, DETAIL_TABLE_CAPTION, "사고접수내용 상세 표")


def _detail_value(page, table, header_name: str, cell_index: int = 0) -> str:
    row = table.get_by_role("row").filter(
        has=page.get_by_role("rowheader", name=re.compile(rf"^{re.escape(header_name)}$")),
    ).first
    cell = row.locator("td").nth(cell_index)
    return _normalize_text(cell.inner_text(timeout=1000))


def _wait_for_result02_detail_ready(page, timeout_ms: int, expected_receipt_number: str):
    detail_table = _detail_table(page)
    initial_wait_ms = min(RESULT02_DETAIL_STABILIZE_MS, timeout_ms)
    common.wait_timeout_with_log(page, initial_wait_ms, "result02 상세 데이터 초기 안정화")

    for _ in range(max(1, timeout_ms // 400)):
        try:
            receipt_number = _detail_value(page, detail_table, "접수번호")
        except Exception:
            receipt_number = ""
        if receipt_number == expected_receipt_number:
            return detail_table
        common.wait_timeout_with_log(page, 400, "result02 상세 데이터 반영 대기")

    raise RuntimeError(
        f"result02 상세 화면 접수번호 데이터가 기대값으로 채워지지 않았습니다: expected={expected_receipt_number}"
    )


def _assert_result02_detail(page, timeout_ms: int, expected_receipt_number: str) -> None:
    _wait_url_contains(page, "result02.do", timeout_ms)
    detail_table = _wait_for_result02_detail_ready(page, timeout_ms, expected_receipt_number)

    receipt_number = _detail_value(page, detail_table, "접수번호")
    claim_date = _detail_value(page, detail_table, "보험청구일자")
    accident_date = _detail_value(page, detail_table, "사고(진단)일자")
    claim_type = _detail_value(page, detail_table, "청구유형")
    claim_content = _detail_value(page, detail_table, "청구내용")

    if receipt_number != expected_receipt_number:
        raise RuntimeError(f"상세 화면 접수번호 불일치: expected={expected_receipt_number}, actual={receipt_number}")
    if claim_date != _today_display():
        raise RuntimeError(f"상세 화면 보험청구일자가 오늘 날짜가 아닙니다: {claim_date}")
    if not RESULT_DATE_PATTERN.fullmatch(accident_date):
        raise RuntimeError(f"상세 화면 사고(진단)일자를 확인하지 못했습니다: {accident_date}")
    if "기타" not in claim_type:
        raise RuntimeError(f"상세 화면 청구유형이 예상과 다릅니다: {claim_type}")
    if claim_content != TARGET_CLAIM_TEXT:
        raise RuntimeError(f"상세 화면 청구내용 불일치: {claim_content}")

    common.wait_locator_visible_with_log(page.locator(DETAIL_PREVIEW_SELECTOR), timeout_ms, "상세 화면 제출서류확인(#btn3)")
    common.wait_locator_visible_with_log(page.locator(DETAIL_CANCEL_SELECTOR), timeout_ms, "상세 화면 접수취소(#btn4)")


def _attach_dialog_recorder(page) -> list[tuple[str, str]]:
    seen_dialogs: list[tuple[str, str]] = []

    def _record(dialog) -> None:
        seen_dialogs.append((dialog.type, dialog.message))

    page.on("dialog", _record)
    return seen_dialogs


def _verify_preview_popup(page, receipt_number: str, timeout_ms: int) -> None:
    popup_timeout_ms = max(timeout_ms, PREVIEW_POPUP_TIMEOUT_MS)
    preview_button = common.first_visible_locator(page.locator(DETAIL_PREVIEW_SELECTOR), "상세 화면 제출서류확인(#btn3)")
    with page.context.expect_page(timeout=popup_timeout_ms) as popup_info:
        common.click_with_log(preview_button, "상세 화면 제출서류확인 클릭")
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=popup_timeout_ms)
    _wait_url_contains(popup, PREVIEW_POPUP_FRAGMENT, popup_timeout_ms)

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
        file_name = _normalize_text(item.locator("strong").inner_text(timeout=1000))
        reg_date = _normalize_text(item.locator("span").last.inner_text(timeout=1000))
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


def _cancel_claim_and_return_result01(page, timeout_ms: int, seen_dialogs: list[tuple[str, str]]) -> None:
    cancel_button = common.first_visible_locator(page.locator(DETAIL_CANCEL_SELECTOR), "상세 화면 접수취소(#btn4)")
    common.click_with_log(cancel_button, "상세 화면 접수취소 클릭")

    for _ in range(max(1, timeout_ms // 400)):
        if "result01.do" in page.url:
            break
        common.wait_timeout_with_log(page, 400, "접수취소 처리 대기")
    _wait_url_contains(page, "result01.do", timeout_ms)

    if not any(dialog_type == "confirm" and "접수를 취소하시겠습니까?" in message for dialog_type, message in seen_dialogs):
        raise RuntimeError(f"접수취소 confirm 대화상자를 확인하지 못했습니다: {seen_dialogs}")
    if not any(dialog_type == "alert" and "정상적으로 처리 되었습니다." in message for dialog_type, message in seen_dialogs):
        raise RuntimeError(f"접수취소 완료 alert를 확인하지 못했습니다: {seen_dialogs}")


def _assert_receipt_absent_in_processing(page, timeout_ms: int, receipt_number: str) -> None:
    _select_results_tab(page, ING_TAB_SELECTOR, "진행중", timeout_ms)
    result_table = _result_table(page)
    rows = result_table.locator("tbody tr")

    for _ in range(max(1, timeout_ms // 400)):
        present = False
        for index in range(rows.count()):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=400):
                    continue
                row_text = _normalize_text(row.inner_text(timeout=400))
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
    result_table = _result_table(page)
    rows = result_table.locator("tbody tr")
    for _ in range(max(1, timeout_ms // 400)):
        for index in range(rows.count()):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=400):
                    continue
                row_text = _normalize_text(row.inner_text(timeout=400))
            except Exception:
                continue
            if receipt_number in row_text:
                return row
        common.wait_timeout_with_log(page, 400, "완료 탭 결과 행 대기")
    raise RuntimeError(f"완료 탭에서 접수번호를 찾지 못했습니다: {receipt_number}")


def _assert_cancelled_in_finished_tab(page, timeout_ms: int, receipt_number: str) -> None:
    _select_results_tab(page, FIN_TAB_SELECTOR, "완료", timeout_ms)
    row = _find_row_by_receipt_number(page, receipt_number, timeout_ms)
    row_text = _normalize_text(row.inner_text(timeout=1000))
    if TARGET_CLAIM_TEXT_TRUNCATED not in row_text:
        raise RuntimeError(f"완료 탭 청구내용이 예상과 다릅니다: {row_text}")
    if CANCELLED_STATUS not in row_text:
        raise RuntimeError(f"완료 탭 상태값이 취소가 아닙니다: {row_text}")

    button_names = _row_button_names(row)
    if button_names != ["제출서류확인"]:
        raise RuntimeError(f"완료 탭 이용가능 서비스가 예상과 다릅니다: {button_names}")


def run(page, config: common.LoginConfig, screenshot_path: Path) -> str:
    try:
        _goto_result01(page, config)
        _select_results_tab(page, ING_TAB_SELECTOR, "진행중", config.timeout_ms)
        row = _find_processing_claim_row(page, config.timeout_ms)
        receipt_number = _receipt_number_from_row(row)
        _open_claim_detail(page, row, config.timeout_ms)
        _assert_result02_detail(page, config.timeout_ms, receipt_number)
        dialog_messages = _attach_dialog_recorder(page)
        _verify_preview_popup(page, receipt_number, config.timeout_ms)
        _cancel_claim_and_return_result01(page, config.timeout_ms, dialog_messages)
        _assert_receipt_absent_in_processing(page, config.timeout_ms, receipt_number)
        _assert_cancelled_in_finished_tab(page, config.timeout_ms, receipt_number)
        common.save_screenshot(page, screenshot_path)
        return f"보험금청구 결과 조회 및 취소 성공 ({receipt_number})"
    except Exception:
        common.save_screenshot(page, screenshot_path)
        raise
