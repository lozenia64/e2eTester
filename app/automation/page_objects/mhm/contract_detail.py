from __future__ import annotations

import re

from . import contract_list
from . import login_common as common

CONTRACT_DETAIL_URL_PATTERN = re.compile(r"/myh/ciq/PsnCrInq(?!1010)")
CONTRACT_CARD_SELECTOR = (
    'main [role="tabpanel"] button:has(h3), '
    'main [role="tabpanel"] a[role="button"]:has(h3), '
    "main button:has(h3), "
    'main a[role="button"]:has(h3)'
)
POLICY_NUMBER_PATTERN = re.compile(r"[FL]A\d[\d*]{5,}")
DETAIL_SECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("계약자정보", re.compile(r"계약자\s*정보")),
    ("담당자정보", re.compile(r"담당자\s*정보")),
    ("납입정보", re.compile(r"납입\s*정보")),
)


def _ensure_contract_list_context(page, timeout_ms: int) -> None:
    if contract_list.CONTRACT_LIST_URL_FRAGMENT in page.url:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        common.maybe_close_post_login_popup(page, timeout_ms)
        return

    common.wait_url_with_log(
        page,
        contract_list.CONTRACT_LIST_URL_PATTERN,
        timeout_ms,
        "보험계약 조회 목록",
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    common.maybe_close_post_login_popup(page, timeout_ms)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _find_first_contract_card(page):
    cards = page.locator(CONTRACT_CARD_SELECTOR)
    card_count = cards.count()
    print(f"[step] Contract cards found: {card_count}")

    for index in range(card_count):
        card = cards.nth(index)
        try:
            if not card.is_visible(timeout=1000):
                continue
            heading = card.locator("h3").first
            if heading.count() == 0:
                continue
            label = _normalize_text(heading.inner_text(timeout=1000))
            if label:
                return card, label
        except Exception:
            continue

    return None, ""


def _select_first_contract_detail(page) -> str:
    card, label = _find_first_contract_card(page)
    if card is None:
        raise RuntimeError("선택 가능한 계약이 없어 계약상세 조회를 진행할 수 없습니다.")

    card.scroll_into_view_if_needed(timeout=2000)
    common.click_with_log(card, f"Open first contract card: {label or 'unknown'}")
    return label


def _wait_for_contract_detail(page, timeout_ms: int) -> None:
    common.wait_url_with_log(page, CONTRACT_DETAIL_URL_PATTERN, timeout_ms, "보험계약 상세")
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)


def _read_policy_number(page, timeout_ms: int) -> str:
    attempts = max(1, timeout_ms // 500)
    for _ in range(attempts):
        body_text = re.sub(r"\s+", " ", page.locator("body").inner_text()).strip()
        match = POLICY_NUMBER_PATTERN.search(body_text)
        if match:
            return match.group(0)
        common.wait_timeout_with_log(page, 500, "Wait for policy number")

    raise RuntimeError("계약상세 화면에서 증권번호를 확인하지 못했습니다.")


def _wait_for_detail_sections(page, timeout_ms: int) -> list[str]:
    attempts = max(1, timeout_ms // 500)
    missing_sections = [label for label, _pattern in DETAIL_SECTION_RULES]

    for _ in range(attempts):
        body_text = re.sub(r"\s+", " ", page.locator("body").inner_text()).strip()
        missing_sections = [
            label for label, pattern in DETAIL_SECTION_RULES if not pattern.search(body_text)
        ]
        if not missing_sections:
            return []
        common.wait_timeout_with_log(page, 500, "Wait for contract detail sections")

    return missing_sections


def run(page, config: common.LoginConfig) -> str:
    _ensure_contract_list_context(page, config.timeout_ms)
    product_name = _select_first_contract_detail(page)
    _wait_for_contract_detail(page, config.timeout_ms)
    policy_number = _read_policy_number(page, config.timeout_ms)
    missing_sections = _wait_for_detail_sections(page, config.timeout_ms)
    if missing_sections:
        joined = ", ".join(missing_sections)
        raise RuntimeError(f"계약상세 화면의 필수 정보영역을 확인하지 못했습니다: {joined}")

    detail_label = product_name or policy_number
    return f"계약상세 조회 성공: {detail_label} ({policy_number}, {page.url})"
