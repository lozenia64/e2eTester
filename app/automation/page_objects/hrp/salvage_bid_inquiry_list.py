from __future__ import annotations

from playwright.sync_api import Page

from app.automation.page_objects.hrp import salvage_bid_inquiry_common as common
from app.systems.access_common import browser


def run(page: Page, *, base_url: str) -> str:
    """잔존물 입찰조회 메뉴 진입 후 목록(총 N건·순번 1)을 확인한다."""
    common.ensure_main_page(page, base_url)
    common.open_bid_inquiry_menu(page)
    common.assert_bottom_tab(page, common.BID_INQUIRY_MENU)

    frame = common.list_frame(page)
    total_count = frame.get_by_text(common.TOTAL_COUNT_PATTERN)
    total_count.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    total_text = total_count.inner_text().strip()
    print(f"[step] List total count: {total_text}")

    receipt_number = common.receipt_number_for_row_one(page)
    print(f"[step] List row sequence 1 confirmed (receipt: {receipt_number})")
    return f"잔존물 입찰 조회(목록) 성공: {total_text}, 순번 1 접수번호 {receipt_number}"
