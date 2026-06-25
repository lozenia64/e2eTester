from __future__ import annotations

from playwright.sync_api import Page

from app.systems.access_common import browser
from app.systems.hrp.steps import salvage_bid_inquiry_common as common


def _open_first_receipt_detail(page: Page, receipt_number: str) -> None:
    print(f"[step] Open bid detail for receipt: {receipt_number}")
    frame = common.list_frame(page)
    receipt_cell = (
        common.first_list_row(frame).get_by_role("cell").filter(has_text=receipt_number).first
    )
    receipt_cell.click(timeout=browser.MAX_TIMEOUT_MS)

    page.get_by_role("heading", name=common.DETAIL_HEADING, level=2).wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )
    print("[step] Bid detail screen opened")


def _verify_bid_detail(page: Page) -> None:
    common.assert_bottom_tab(page, common.BID_DETAIL_MENU)
    frame = common.detail_frame(page)

    for heading in common.DETAIL_SECTION_HEADINGS:
        section = frame.get_by_role("heading", name=heading, level=3)
        section.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
        print(f"[step] Detail section confirmed: {heading}")


def run(page: Page, *, base_url: str) -> str:
    """목록 화면에서 순번 1 접수번호를 클릭해 상세 정보를 확인한다."""
    common.ensure_bid_inquiry_list_screen(page)
    receipt_number = common.receipt_number_for_row_one(page)
    _open_first_receipt_detail(page, receipt_number)
    _verify_bid_detail(page)
    return f"잔존물 입찰 조회(상세) 성공: 접수번호 {receipt_number} 상세 확인 ({page.url})"
