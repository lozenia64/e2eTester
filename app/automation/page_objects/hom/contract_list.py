from __future__ import annotations

import re

from . import login_common as common

CONTRACT_LIST_URL_FRAGMENT = "/fplaza/inquiry/contract01.do"
CONTRACT_COUNT_PATTERN = re.compile(r"총\s*([0-9,]+)\s*건")
CONTRACT_DETAIL_LINK_SELECTOR = 'a[href*="contract02"]'
SERVICE_INTERRUPTION_MARKERS: tuple[str, ...] = (
    "서비스 이용 안내",
    "시스템 점검 작업",
    "연계 서비스 이용이 중단",
)


def _open_myhanwha_menu(page, timeout_ms: int) -> None:
    menu_candidates = [
        page.get_by_role("link", name=re.compile(r"^MY한화$")),
        page.locator("header").get_by_text("MY한화", exact=True),
        page.get_by_text("MY한화", exact=True),
    ]

    for candidate in menu_candidates:
        try:
            menu = candidate.first
            if not menu.is_visible(timeout=2000):
                continue
            print("[step] Open MY한화 GNB menu")
            try:
                menu.hover(timeout=timeout_ms)
            except Exception:
                common.click_with_log(menu, "Open MY한화 GNB menu")
            common.wait_timeout_with_log(page, 600, "MY한화 menu expand delay")
            return
        except Exception:
            continue

    raise RuntimeError("MY한화 GNB 메뉴를 찾지 못했습니다.")


def _find_contract_list_link(page):
    candidates = [
        page.locator('a[href*="/fplaza/inquiry/contract01.do"]:visible').first,
        page.get_by_role("link", name=re.compile(r"개인계약\s*조회")).first,
        page.locator('a:has-text("개인계약 조회")').first,
    ]

    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=1500):
                return candidate
        except Exception:
            continue
    return None


def _navigate_to_contract_list(page, timeout_ms: int) -> None:
    common.maybe_close_post_login_popup(page, timeout_ms)

    contract_link = _find_contract_list_link(page)
    if contract_link is None:
        _open_myhanwha_menu(page, timeout_ms)
        common.maybe_close_post_login_popup(page, timeout_ms)
        contract_link = _find_contract_list_link(page)

    if contract_link is None:
        raise RuntimeError("개인계약 조회 메뉴를 찾지 못했습니다.")

    common.click_with_log(contract_link, "Navigate to personal contract inquiry list")
    print(f"[wait] Start URL contains wait: {CONTRACT_LIST_URL_FRAGMENT} ({timeout_ms} ms)")
    page.wait_for_function(
        "fragment => window.location.href.includes(fragment)",
        arg=CONTRACT_LIST_URL_FRAGMENT,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {CONTRACT_LIST_URL_FRAGMENT} -> {page.url}")
    assert_inquiry_page_available(page, context="계약목록 조회")


def _page_body_text(page) -> str:
    return page.locator("body").inner_text()


def assert_inquiry_page_available(page, *, context: str) -> None:
    """URL만 맞고 본문이 시스템 점검 안내인 경우를 실패로 처리한다."""
    body_text = _page_body_text(page)
    for marker in SERVICE_INTERRUPTION_MARKERS:
        if marker in body_text:
            raise RuntimeError(
                f"{context} 실패: 시스템 점검 안내 페이지가 표시되어 조회를 진행할 수 없습니다. ({marker})"
            )


def _count_contract_detail_links(page) -> int:
    links = page.locator(CONTRACT_DETAIL_LINK_SELECTOR)
    visible_count = 0
    for index in range(links.count()):
        link = links.nth(index)
        try:
            if link.is_visible(timeout=500):
                visible_count += 1
        except Exception:
            continue
    return visible_count


def _read_contract_count(page, timeout_ms: int) -> int:
    for _ in range(5):
        assert_inquiry_page_available(page, context="계약목록 조회")

        heading_candidates = [
            page.get_by_role("heading", name=re.compile(r"개인계약\s*조회")),
            page.locator("h1, h2, h3").filter(has_text=re.compile(r"개인계약\s*조회")).first,
        ]
        for candidate in heading_candidates:
            try:
                common.wait_locator_visible_with_log(
                    candidate, timeout_ms, "Personal contract inquiry heading"
                )
                break
            except Exception:
                continue

        body_text = _page_body_text(page).replace(",", "")
        match = CONTRACT_COUNT_PATTERN.search(body_text)
        if match:
            return int(match.group(1))

        detail_link_count = _count_contract_detail_links(page)
        if detail_link_count > 0:
            return detail_link_count

        common.wait_timeout_with_log(page, 400, "Wait for contract count text")

    assert_inquiry_page_available(page, context="계약목록 조회")
    raise RuntimeError(
        "계약목록 건수를 확인하지 못했습니다. (총 N건 문구 또는 계약 상세 링크 없음)"
    )


def run(page, config: common.LoginConfig) -> str:
    _navigate_to_contract_list(page, config.timeout_ms)
    contract_count = _read_contract_count(page, config.timeout_ms)
    return f"계약목록 조회 성공: {contract_count}건 확인 ({page.url})"
