from __future__ import annotations

from datetime import date
import re

import mhm_login_common as common

RESULT01_FRAGMENT = "/fplaza/compensation/result01.do"
RESULT02_FRAGMENT = "/fplaza/compensation/result02.do"
PROCESSING_STATUS = "처리중"
TARGET_CLAIM_TEXT = "IT직원 테스트입니다. 바로 취소할 예정입니다."
TARGET_CLAIM_TEXT_TRUNCATED = "IT직원 테스트입니다. 바로 취소할"
ING_TAB_SELECTOR = "#ing"
FIN_TAB_SELECTOR = "#fin"
DETAIL_PREVIEW_SELECTOR = "#btn3"
DETAIL_CANCEL_SELECTOR = "#btn4"
RESULT_DATE_PATTERN = re.compile(r"\d{4}\.\d{2}\.\d{2}")
RESULT_TABLE_CAPTION = "상해/질병/화재보험금 청구내역 목록"
DETAIL_TABLE_CAPTION = "사고접수내용 상세"
RESULT02_DETAIL_STABILIZE_MS = 2000


def wait_url_contains(page, fragment: str, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "f => window.location.href.includes(f)",
        arg=fragment,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def today_display() -> str:
    return date.today().strftime("%Y.%m.%d")


def find_visible_table_by_caption(page, caption_text: str, description: str):
    tables = page.locator("table")
    table_count = tables.count()
    normalized_caption_text = normalize_text(caption_text)

    for index in range(table_count):
        table = tables.nth(index)
        try:
            if not table.is_visible(timeout=800):
                continue
            caption = table.locator("caption").first
            if caption.count() == 0:
                continue
            actual_caption = normalize_text(caption.inner_text(timeout=800))
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
        wait_url_contains(page, "result01.do", timeout_ms)
        return True
    except Exception as exc:
        print(f"[warn] 메뉴로 result01 이동 실패, 직접 URL 시도: {exc}")
        return False


def goto_result01(page, config: common.LoginConfig) -> None:
    if not _open_result01_from_menu(page, config.timeout_ms):
        common.maybe_close_post_login_popup(page, config.timeout_ms)
        base = config.base_url.rstrip("/")
        common.open_url(page, f"{base}{RESULT01_FRAGMENT}")
        wait_url_contains(page, "result01.do", config.timeout_ms)


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


def select_results_tab(page, selector: str, label: str, timeout_ms: int) -> None:
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


def result_table(page):
    return find_visible_table_by_caption(page, RESULT_TABLE_CAPTION, "상해/질병/화재보험금 청구내역 목록 표")


def row_button_names(row) -> list[str]:
    try:
        return [normalize_text(value) for value in row.locator("button").all_inner_texts() if normalize_text(value)]
    except Exception:
        return []


def find_processing_claim_row(page, timeout_ms: int):
    table = result_table(page)
    rows = table.locator("tbody tr")
    today = today_display()

    for _ in range(max(1, timeout_ms // 400)):
        row_count = rows.count()
        for index in range(row_count):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=800):
                    continue
                row_text = normalize_text(row.inner_text(timeout=800))
            except Exception:
                continue
            if today not in row_text:
                continue
            if TARGET_CLAIM_TEXT_TRUNCATED not in row_text:
                continue
            if PROCESSING_STATUS not in row_text:
                continue
            button_names = set(row_button_names(row))
            if {"제출서류확인", "접수취소"} - button_names:
                continue
            print(f"[step] 결과 목록 대상 행 선택: {row_text}")
            return row
        common.wait_timeout_with_log(page, 400, "결과 조회 목록 대상 행 대기")
    raise RuntimeError("오늘 접수된 취소 대상 보험금청구 결과 행을 찾지 못했습니다.")


def receipt_number_from_row(row) -> str:
    link = common.first_visible_locator(row.get_by_role("link"), "결과 목록 접수번호 링크")
    receipt_number = normalize_text(link.inner_text(timeout=1000))
    if not receipt_number:
        raise RuntimeError("결과 목록 행에서 접수번호를 읽지 못했습니다.")
    return receipt_number


def open_claim_detail(page, row, timeout_ms: int) -> None:
    detail_link = common.first_visible_locator(row.get_by_role("link"), "결과 목록 상세 링크")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        common.click_with_log(detail_link, "결과 목록 접수번호 상세 조회")
    wait_url_contains(page, "result02.do", timeout_ms)


def detail_table(page):
    return find_visible_table_by_caption(page, DETAIL_TABLE_CAPTION, "사고접수내용 상세 표")


def detail_value(page, table, header_name: str, cell_index: int = 0) -> str:
    row = table.get_by_role("row").filter(
        has=page.get_by_role("rowheader", name=re.compile(rf"^{re.escape(header_name)}$")),
    ).first
    cell = row.locator("td").nth(cell_index)
    return normalize_text(cell.inner_text(timeout=1000))


def wait_for_result02_detail_ready(page, timeout_ms: int, expected_receipt_number: str):
    table = detail_table(page)
    initial_wait_ms = min(RESULT02_DETAIL_STABILIZE_MS, timeout_ms)
    common.wait_timeout_with_log(page, initial_wait_ms, "result02 상세 데이터 초기 안정화")

    for _ in range(max(1, timeout_ms // 400)):
        try:
            receipt_number = detail_value(page, table, "접수번호")
        except Exception:
            receipt_number = ""
        if receipt_number == expected_receipt_number:
            return table
        common.wait_timeout_with_log(page, 400, "result02 상세 데이터 반영 대기")

    raise RuntimeError(
        f"result02 상세 화면 접수번호 데이터가 기대값으로 채워지지 않았습니다: expected={expected_receipt_number}"
    )
