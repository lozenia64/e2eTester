from __future__ import annotations

import re

from playwright.sync_api import FrameLocator, Locator, Page

from app.systems.access_common import browser
from app.systems.hrp.steps.login import AUTH_SUCCESS_PATH

MAIN_PAGE_PATH = AUTH_SUCCESS_PATH
SALVAGE_MENU = "잔존물"
BID_INQUIRY_MENU = "잔존물입찰조회"
BID_DETAIL_MENU = "잔존물입찰"
LIST_HEADING = "잔존물입찰조회"
DETAIL_HEADING = "잔존물입찰"

LIST_IFRAME_SELECTOR = 'iframe[name="workArea_hrpF020"]'
DETAIL_IFRAME_SELECTOR = 'iframe[name="workArea_hrpF021"]'

TOTAL_COUNT_PATTERN = re.compile(r"총\s*\d+\s*건")
RECEIPT_NUMBER_PATTERN = re.compile(r"\d{6}-\d{5}-\d{2}-\d{3}")
DETAIL_SECTION_HEADINGS = ("등록자 정보", "등록정보", "사고정보", "차량정보")


def main_url(base_url: str) -> str:
    return f"{browser.normalize_base_url(base_url, base_url)}/{MAIN_PAGE_PATH}"


def ensure_main_page(page: Page, base_url: str) -> None:
    if MAIN_PAGE_PATH in page.url:
        browser.maybe_close_popup(page)
        return
    url = main_url(base_url)
    print(f"[wait] Navigate to main page: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=browser.MAX_TIMEOUT_MS)
    browser.maybe_close_popup(page)
    if MAIN_PAGE_PATH not in page.url:
        raise RuntimeError(f"메인화면({MAIN_PAGE_PATH})으로 이동하지 못했습니다: {page.url}")
    print(f"[wait] Main page ready: {page.url}")


def bottom_tab_links(page: Page) -> Locator:
    return (
        page.locator("li")
        .filter(has=page.get_by_role("link", name="메인", exact=True))
        .locator("..")
    )


def assert_bottom_tab(page: Page, tab_name: str) -> None:
    tab = bottom_tab_links(page).get_by_role("link", name=tab_name, exact=True)
    tab.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    print(f"[step] Bottom tab confirmed: {tab_name}")


def open_bid_inquiry_menu(page: Page) -> None:
    print("[step] Open salvage bid inquiry from top menu")
    page.get_by_role("link", name=SALVAGE_MENU, exact=True).click()
    page.get_by_role("link", name=BID_INQUIRY_MENU, exact=True).click()
    page.get_by_role("heading", name=LIST_HEADING, level=2).wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )
    print("[step] Bid inquiry list screen opened")


def list_frame(page: Page) -> FrameLocator:
    page.locator(LIST_IFRAME_SELECTOR).wait_for(state="attached", timeout=browser.MAX_TIMEOUT_MS)
    return page.frame_locator(LIST_IFRAME_SELECTOR)


def detail_frame(page: Page) -> FrameLocator:
    page.locator(DETAIL_IFRAME_SELECTOR).wait_for(state="attached", timeout=browser.MAX_TIMEOUT_MS)
    return page.frame_locator(DETAIL_IFRAME_SELECTOR)


def list_data_rows(frame: FrameLocator) -> Locator:
    """목록 그리드는 검색/헤더/본문이 별도 table 로 분리되어 있다."""
    return frame.get_by_role("row").filter(has_text=RECEIPT_NUMBER_PATTERN)


def first_list_row(frame: FrameLocator) -> Locator:
    rows = list_data_rows(frame)
    rows.first.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    for index in range(min(rows.count(), 5)):
        row = rows.nth(index)
        sequence_text = row.get_by_role("cell").first.inner_text().strip()
        if sequence_text == "1":
            return row
    raise RuntimeError("목록에서 순번 1 행을 찾지 못했습니다.")


def ensure_bid_inquiry_list_screen(page: Page) -> None:
    page.get_by_role("heading", name=LIST_HEADING, level=2).wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )
    list_frame(page)
    print("[step] Bid inquiry list screen ready")


def receipt_number_for_row_one(page: Page) -> str:
    frame = list_frame(page)
    first_row = first_list_row(frame)
    sequence_text = first_row.get_by_role("cell").first.inner_text().strip()
    if sequence_text != "1":
        raise RuntimeError(f"목록 순번 1을 찾지 못했습니다 (실제: {sequence_text!r})")

    receipt_cell = first_row.get_by_role("cell").filter(has_text=RECEIPT_NUMBER_PATTERN).first
    receipt_number = receipt_cell.inner_text().strip()
    if not receipt_number:
        raise RuntimeError("순번 1 행의 접수번호가 비어 있습니다.")
    return receipt_number
