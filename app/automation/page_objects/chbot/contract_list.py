from __future__ import annotations

import re

from playwright.sync_api import Page

from app.systems.access_common import browser

POLICYHOLDER_BUTTON = "a[data-sinario='INS002'][data-searchkey='01']"
NORMAL_STATUS_BUTTON = "a[data-sinario='INS003'][data-searchkey='00']"
TOTAL_COUNT_PATTERN = re.compile(r"총\s*\d+\s*건")


def _scroll_chat_to_bottom(page: Page) -> None:
    page.evaluate(
        """
        () => {
            const targets = [
                document.querySelector('#cb-chatting-body'),
                document.querySelector('.cb-chatting-scroll'),
                document.querySelector('#chatting-logContainer'),
            ].filter(Boolean);
            for (const el of targets) {
                el.scrollTop = el.scrollHeight;
            }
        }
        """
    )


def _wait_for_text(page: Page, text: str, *, timeout_ms: int | None = None) -> None:
    timeout = timeout_ms or browser.MAX_TIMEOUT_MS
    print(f"[wait] Visible text: {text!r}")
    page.get_by_text(text, exact=False).last.wait_for(state="visible", timeout=timeout)
    _scroll_chat_to_bottom(page)


def _verify_contract_list(page: Page) -> str:
    print("[step] Verify contract list and total count")
    page.get_by_text("계약목록", exact=False).last.wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )
    body_text = page.evaluate("() => document.body.innerText")
    match = TOTAL_COUNT_PATTERN.search(body_text or "")
    if not match:
        raise RuntimeError("계약목록의 (총 N건) 문구를 찾지 못했습니다.")
    total_label = match.group(0).replace(" ", "")
    print(f"[step] Contract list total: {total_label}")
    return total_label


def run(page: Page) -> str:
    """간편본인인증 완료 후 계약 조회 기준·상태를 선택하고 목록을 검증한다."""
    _wait_for_text(page, "계약 조회 기준 선택")
    print("[step] Select policyholder contracts")
    page.locator(POLICYHOLDER_BUTTON).last.click()
    _scroll_chat_to_bottom(page)

    _wait_for_text(page, "계약 상태 선택")
    print("[step] Select normal contract status")
    page.locator(NORMAL_STATUS_BUTTON).last.click()
    _scroll_chat_to_bottom(page)

    total_label = _verify_contract_list(page)
    return f"계약조회 성공 ({total_label})"
