from __future__ import annotations

import re

from . import contract_list
from . import login_common as common


CONTRACT_DETAIL_URL_FRAGMENT = "/fplaza/inquiry/contract02.do"
DETAIL_SECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("계약일반정보", re.compile(r"계약\s*일반정보")),
    ("수익자정보", re.compile(r"수익자\s*정보")),
    ("자동이체현황", re.compile(r"자동이체\s*현황")),
    ("우편물 수령지/연락처", re.compile(r"우편물\s*수령지\s*/\s*연락처")),
    ("담당자정보", re.compile(r"담당자\s*정보")),
    ("계약자정보", re.compile(r"계약자\s*정보")),
)
DETAIL_LINK_SELECTORS: tuple[str, ...] = (
    'a[href*="contract02.do"]',
    'a[href*="contract02"]',
)
POLICY_NUMBER_PATTERN = re.compile(r"\d[\d-]{5,}")


def _ensure_contract_list_context(page, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {contract_list.CONTRACT_LIST_URL_FRAGMENT} ({timeout_ms} ms)")
    page.wait_for_function(
        "fragment => window.location.href.includes(fragment)",
        arg=contract_list.CONTRACT_LIST_URL_FRAGMENT,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    common.maybe_close_post_login_popup(page, timeout_ms)
    print(f"[wait] End URL contains wait: {contract_list.CONTRACT_LIST_URL_FRAGMENT}")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _find_contract_entry_in_row(row):
    for selector in DETAIL_LINK_SELECTORS:
        candidate = row.locator(selector).first
        try:
            if candidate.count() == 0 or not candidate.is_visible(timeout=1000):
                continue
        except Exception as exc:
            print(f"[warn] Failed to inspect contract detail link candidate: {exc}")
            continue

        label = _normalize_text(candidate.inner_text(timeout=1000))
        if label and POLICY_NUMBER_PATTERN.search(label):
            return candidate

    anchors = row.locator("a")
    anchor_count = anchors.count()
    for index in range(anchor_count):
        candidate = anchors.nth(index)
        try:
            if not candidate.is_visible(timeout=1000):
                continue
            label = _normalize_text(candidate.inner_text(timeout=1000))
        except Exception:
            continue

        if label and POLICY_NUMBER_PATTERN.search(label):
            return candidate

    return None


def _select_first_contract_detail(page) -> None:
    rows = page.locator("table tbody tr")
    row_count = rows.count()
    print(f"[step] Contract table rows found: {row_count}")

    for index in range(row_count):
        row = rows.nth(index)
        try:
            if not row.is_visible(timeout=1000):
                continue
        except Exception:
            continue

        detail_link = _find_contract_entry_in_row(row)
        if detail_link is None:
            continue

        detail_link.scroll_into_view_if_needed(timeout=2000)
        common.click_with_log(detail_link, f"Open first selectable contract row: {index + 1}")
        return

    raise RuntimeError("선택 가능한 계약이 없어 계약상세 조회를 진행할 수 없습니다.")


def _wait_for_contract_detail(page, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {CONTRACT_DETAIL_URL_FRAGMENT} ({timeout_ms} ms)")
    page.wait_for_function(
        "fragment => window.location.href.includes(fragment)",
        arg=CONTRACT_DETAIL_URL_FRAGMENT,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {CONTRACT_DETAIL_URL_FRAGMENT}")


def _wait_for_detail_sections(page, timeout_ms: int) -> list[str]:
    attempts = max(1, timeout_ms // 500)
    missing_sections = [label for label, _pattern in DETAIL_SECTION_RULES]

    for _ in range(attempts):
        body_text = re.sub(r"\s+", " ", page.locator("body").inner_text()).strip()
        missing_sections = [label for label, pattern in DETAIL_SECTION_RULES if not pattern.search(body_text)]
        if not missing_sections:
            return []
        common.wait_timeout_with_log(page, 500, "Wait for contract detail sections")

    return missing_sections


def run(page, config: common.LoginConfig) -> str:
    _ensure_contract_list_context(page, config.timeout_ms)
    _select_first_contract_detail(page)
    _wait_for_contract_detail(page, config.timeout_ms)
    missing_sections = _wait_for_detail_sections(page, config.timeout_ms)
    if missing_sections:
        joined = ", ".join(missing_sections)
        raise RuntimeError(f"계약상세 화면의 필수 정보영역을 확인하지 못했습니다: {joined}")

    return "계약상세 조회 성공"
