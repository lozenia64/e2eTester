from __future__ import annotations

from pathlib import Path
import re

from . import login_common as common


CONTRACT_LIST_URL_FRAGMENT = "/myh/ciq/PsnCrInq1010"
CONTRACT_LIST_URL_PATTERN = re.compile(r"/myh/ciq/PsnCrInq1010")
MAIN_SUB_MAIN_URL_FRAGMENT = "/myh/mai/MySubMain"
CONTRACT_COUNT_PATTERN = re.compile(r"총\s*([0-9,]+)\s*건")
CONTRACT_STATUS_BUTTON_SELECTOR = 'main button.btn.s3.c4:has-text("계약현황조회")'
CONTRACT_CARD_SELECTOR = (
    'main [role="tabpanel"] button:has(h3), '
    'main [role="tabpanel"] a[role="button"]:has(h3), '
    'main button:has(h3), '
    'main a[role="button"]:has(h3)'
)


def _wait_for_contract_list_page(page, timeout_ms: int) -> None:
    common.wait_url_with_log(page, CONTRACT_LIST_URL_PATTERN, timeout_ms, "보험계약 조회 목록")
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)


def _is_on_contract_list_page(page) -> bool:
    return bool(CONTRACT_LIST_URL_PATTERN.search(page.url))


def _open_myhanwha_menu(page, timeout_ms: int) -> None:
    menu_candidates = [
        page.get_by_role("button", name=re.compile(r"전체\s*메뉴")),
        page.locator('button:has-text("전체메뉴")').first,
        page.get_by_role("link", name=re.compile(r"^MY한화$")),
        page.locator("header").get_by_text("MY한화", exact=True),
        page.get_by_text("MY한화", exact=True),
    ]

    for candidate in menu_candidates:
        try:
            menu = candidate.first
            if not menu.is_visible(timeout=2000):
                continue
            print("[step] Open MY한화 mobile menu")
            common.click_with_log(menu, "Open MY한화 mobile menu")
            common.wait_timeout_with_log(page, 600, "MY한화 menu expand delay")
            return
        except Exception:
            continue

    raise RuntimeError("MY한화 모바일 메뉴를 찾지 못했습니다.")


def _find_main_contract_status_button(page):
    candidates = [
        page.locator(CONTRACT_STATUS_BUTTON_SELECTOR).first,
        page.get_by_role("button", name=re.compile(r"계약\s*현황\s*조회")).first,
    ]

    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=1500):
                return candidate
        except Exception:
            continue
    return None


def _find_contract_menu_link(page):
    candidates = [
        page.get_by_role("link", name=re.compile(r"개인계약\s*조회")).first,
        page.locator('nav a:has-text("개인계약 조회")').first,
        page.locator('a:has-text("개인계약 조회")').first,
    ]

    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=1500):
                return candidate
        except Exception:
            continue
    return None


def _navigate_to_contract_list(page, timeout_ms: int, base_url: str) -> None:
    common.maybe_close_post_login_popup(page, timeout_ms)

    if _is_on_contract_list_page(page):
        _wait_for_contract_list_page(page, timeout_ms)
        return

    entry = _find_main_contract_status_button(page)
    if entry is not None:
        common.click_with_log(entry, "메인화면 계약현황조회")
        _wait_for_contract_list_page(page, timeout_ms)
        return

    if MAIN_SUB_MAIN_URL_FRAGMENT not in page.url:
        common.open_url(page, f"{base_url.rstrip('/')}{MAIN_SUB_MAIN_URL_FRAGMENT}")
        common.maybe_close_post_login_popup(page, timeout_ms)
        entry = _find_main_contract_status_button(page)
        if entry is not None:
            common.click_with_log(entry, "메인화면 계약현황조회")
            _wait_for_contract_list_page(page, timeout_ms)
            return

    _open_myhanwha_menu(page, timeout_ms)
    common.maybe_close_post_login_popup(page, timeout_ms)
    menu_link = _find_contract_menu_link(page)
    if menu_link is not None:
        common.click_with_log(menu_link, "전체메뉴 개인계약 조회")
        _wait_for_contract_list_page(page, timeout_ms)
        return

    common.open_url(page, f"{base_url.rstrip('/')}{CONTRACT_LIST_URL_FRAGMENT}")
    _wait_for_contract_list_page(page, timeout_ms)


def _read_contract_count(page, timeout_ms: int) -> int:
    heading_candidates = [
        page.get_by_role("heading", name=re.compile(r"보험계약\s*조회")),
        page.get_by_role("heading", name=re.compile(r"상세\s*조회하실\s*계약을\s*선택")),
    ]
    for candidate in heading_candidates:
        try:
            common.wait_locator_visible_with_log(candidate, timeout_ms, "보험계약 조회 목록 제목")
            break
        except Exception:
            continue

    for _ in range(5):
        body_text = page.locator("body").inner_text().replace(",", "")
        match = CONTRACT_COUNT_PATTERN.search(body_text)
        if match:
            return int(match.group(1))

        cards = page.locator(CONTRACT_CARD_SELECTOR)
        if cards.count() > 0:
            return cards.count()

        common.wait_timeout_with_log(page, 400, "Wait for contract count text")

    cards = page.locator(CONTRACT_CARD_SELECTOR)
    card_count = cards.count()
    if card_count > 0:
        return card_count

    raise RuntimeError("계약목록 건수를 확인하지 못했습니다.")


def run(page, config: common.LoginConfig, screenshot_path: Path) -> str:
    _navigate_to_contract_list(page, config.timeout_ms, config.base_url)
    contract_count = _read_contract_count(page, config.timeout_ms)
    common.save_screenshot(page, screenshot_path)
    return f"계약목록 조회 성공: {contract_count}건 확인 ({page.url})"
