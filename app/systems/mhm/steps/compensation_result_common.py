from __future__ import annotations

import re
from datetime import date

# 청구 식별 문구는 charge→result→cancel 을 결합하는 도메인 규칙이므로 시나리오 계층(SSOT)에서 가져온다.
from app.scenarios.rep_homepage.constants import TARGET_CLAIM_TEXT_TRUNCATED

from . import login_common as common

RESULT_INTRO_URL_FRAGMENT = "/cmp/dii/IbnfDmRstInq1000"
RESULT_LIST_URL_FRAGMENT = "/cmp/dii/IbnfDmRstInq1010"
RESULT_DETAIL_URL_FRAGMENT = "/cmp/dii/IbnfDmRstInq1020"
RESULT_ENTRY_MENU_SELECTOR = "#code03020300"
PROCESSING_STATUS_HINT = re.compile(r"서류\s*추가|진행중|담당자\s*배정")
RESULT_DATE_PATTERN = re.compile(r"\d{4}\.\d{2}\.\d{2}")
CLAIM_CARD_SELECTOR = 'main a:has(h3), main a[role="link"]:has(h3)'
DETAIL_PREVIEW_BUTTON_PATTERN = re.compile(r"제출서류\s*확인")
DETAIL_CANCEL_SELECTOR = 'main button:has-text("접수취소")'
DETAIL_SECTION_HEADING = "보험금청구 내용"
ING_TAB_SELECTOR = "main button.icon_filter"
FIN_TAB_SELECTOR = "main button.icon_filter"
FILTER_DIALOG_NAME = "조회 조건 설정"
CANCELLED_DETAIL_HEADING = re.compile(r"보험금청구\s*접수가\s*취소")
EMPTY_PROCESSING_MESSAGE = re.compile(r"진행\s*중인\s*보험금청구\s*내역이\s*없습니다")


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


def normalize_receipt_number(value: str) -> str:
    normalized = normalize_text(value)
    if "/" in normalized:
        return normalized.split("/", 1)[0].strip()
    return normalized


def today_display() -> str:
    return date.today().strftime("%Y.%m.%d")


def _open_hamburger_menu(page, timeout_ms: int) -> None:
    close_button = page.get_by_role("button", name=re.compile(r"전체\s*메뉴\s*닫기"))
    try:
        if close_button.is_visible(timeout=800):
            return
    except Exception:
        pass

    open_candidates = [
        page.locator("banner").get_by_text("전체메뉴 열기").first,
        page.get_by_text("전체메뉴 열기").first,
    ]
    for candidate in open_candidates:
        try:
            if candidate.is_visible(timeout=1500):
                common.click_with_log(candidate, "전체메뉴 열기")
                common.wait_timeout_with_log(page, 600, "전체메뉴 펼침 대기")
                return
        except Exception:
            continue
    raise RuntimeError("전체메뉴 열기 버튼을 찾지 못했습니다.")


def _click_result_entry_menu(page, timeout_ms: int) -> None:
    _open_hamburger_menu(page, timeout_ms)
    compensation_tab = page.get_by_role("tab", name="보상")
    common.click_with_log(compensation_tab, "전체메뉴 보상 탭")
    common.wait_timeout_with_log(page, 400, "보상 탭 전환 대기")

    entry = page.locator(RESULT_ENTRY_MENU_SELECTOR).first
    try:
        entry.scroll_into_view_if_needed(timeout=timeout_ms)
        common.click_with_log(entry, "질병/상해보험 > 보험금청구 결과 조회")
        return
    except Exception:
        pass

    fallback = page.locator("nav").get_by_text("보험금청구 결과 조회", exact=True).first
    fallback.scroll_into_view_if_needed(timeout=timeout_ms)
    common.click_with_log(fallback, "질병/상해보험 > 보험금청구 결과 조회(fallback)")


def _ensure_result_list_page(page, timeout_ms: int) -> None:
    if RESULT_LIST_URL_FRAGMENT in page.url:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return

    if RESULT_INTRO_URL_FRAGMENT in page.url:
        inquiry = page.get_by_role("button", name="조회하기")
        common.click_with_log(inquiry, "보험금청구 결과 조회: 조회하기")
        wait_url_contains(page, RESULT_LIST_URL_FRAGMENT, timeout_ms)
        return

    raise RuntimeError("보험금청구 결과 목록 화면으로 이동하지 못했습니다.")


def goto_result01(page, config: common.LoginConfig) -> None:
    common.maybe_close_post_login_popup(page, config.timeout_ms)
    if RESULT_LIST_URL_FRAGMENT in page.url:
        page.wait_for_load_state("domcontentloaded", timeout=config.timeout_ms)
        return

    try:
        _click_result_entry_menu(page, config.timeout_ms)
        wait_url_contains(page, RESULT_INTRO_URL_FRAGMENT, config.timeout_ms)
        _ensure_result_list_page(page, config.timeout_ms)
        return
    except Exception as exc:
        print(f"[warn] 메뉴로 결과 조회 진입 실패, 직접 URL 시도: {exc}")

    common.open_url(page, f"{config.base_url.rstrip('/')}{RESULT_INTRO_URL_FRAGMENT}")
    wait_url_contains(page, RESULT_INTRO_URL_FRAGMENT, config.timeout_ms)
    _ensure_result_list_page(page, config.timeout_ms)


def _current_filter_status(page) -> str:
    chip = page.locator("main").get_by_text(re.compile(r"^(진행중|완료)\s+본인")).first
    try:
        chip_text = normalize_text(chip.inner_text(timeout=800))
    except Exception:
        return ""
    if chip_text.startswith("완료"):
        return "완료"
    if chip_text.startswith("진행중"):
        return "진행중"
    return ""


def select_results_tab(page, selector: str, label: str, timeout_ms: int) -> None:
    del selector
    if RESULT_LIST_URL_FRAGMENT not in page.url:
        _ensure_result_list_page(page, timeout_ms)

    status = label if label in {"진행중", "완료"} else ""
    if not status:
        print(f"[step] {label} 탭 선택 생략(모바일 목록 기본 필터 사용)")
        return

    if _current_filter_status(page) == status:
        print(f"[step] {label} 필터 이미 선택됨")
        return

    filter_button = page.locator("main button.icon_filter").first
    common.wait_locator_visible_with_log(filter_button, timeout_ms, "결과 목록 필터")
    common.click_with_log(filter_button, f"결과 목록 필터 열기({label})")

    dialog = page.get_by_role("dialog", name=FILTER_DIALOG_NAME)
    common.wait_locator_visible_with_log(dialog, timeout_ms, FILTER_DIALOG_NAME)
    common.click_with_log(dialog.get_by_role("tab", name=status), f"청구 진행 상태 {status}")
    common.click_with_log(dialog.get_by_role("button", name="확인"), f"조회 조건 {status} 확인")
    common.wait_timeout_with_log(page, 600, f"{status} 필터 반영 대기")
    print(f"[step] {label} 필터 선택 완료")


def claim_cards(page):
    return page.locator(CLAIM_CARD_SELECTOR)


def row_button_names(row) -> list[str]:
    try:
        return [
            normalize_text(value)
            for value in row.locator("button").all_inner_texts()
            if normalize_text(value)
        ]
    except Exception:
        return []


def find_processing_claim_row(page, timeout_ms: int):
    _ensure_result_list_page(page, timeout_ms)
    cards = claim_cards(page)
    today = today_display()

    for _ in range(max(1, timeout_ms // 400)):
        card_count = cards.count()
        for index in range(card_count):
            card = cards.nth(index)
            try:
                if not card.is_visible(timeout=800):
                    continue
                card_text = normalize_text(card.inner_text(timeout=800))
            except Exception:
                continue
            if today not in card_text:
                continue
            if TARGET_CLAIM_TEXT_TRUNCATED not in card_text:
                continue
            if not PROCESSING_STATUS_HINT.search(card_text):
                continue
            print(f"[step] 결과 목록 대상 카드 선택: {card_text}")
            return card
        common.wait_timeout_with_log(page, 400, "결과 조회 목록 대상 카드 대기")
    raise RuntimeError("오늘 접수된 취소 대상 보험금청구 결과 카드를 찾지 못했습니다.")


def card_has_cancelled_status(card) -> bool:
    try:
        return card.locator('span.tag.c3:has-text("취소")').first.is_visible(timeout=800)
    except Exception:
        card_text = normalize_text(card.inner_text(timeout=800))
        return bool(re.search(r"기타비용\s*취소|질병\s*취소|일반상해\s*취소", card_text))


def find_card_by_receipt_number(page, receipt_number: str, timeout_ms: int):
    _ensure_result_list_page(page, timeout_ms)
    cards = claim_cards(page)
    for _ in range(max(1, timeout_ms // 400)):
        for index in range(cards.count()):
            card = cards.nth(index)
            try:
                if not card.is_visible(timeout=400):
                    continue
                card_text = normalize_text(card.inner_text(timeout=400))
            except Exception:
                continue
            if receipt_number in card_text:
                return card
        common.wait_timeout_with_log(page, 400, "결과 목록 카드 대기")
    raise RuntimeError(f"결과 목록에서 접수번호 카드를 찾지 못했습니다: {receipt_number}")


def receipt_number_from_row(row) -> str:
    row_text = normalize_text(row.inner_text(timeout=1000))
    match = re.search(r"접수번호\s*([0-9]+)", row_text)
    if match:
        return match.group(1)
    raise RuntimeError("결과 목록 카드에서 접수번호를 읽지 못했습니다.")


def open_claim_detail(page, row, timeout_ms: int) -> None:
    common.click_with_log(row, "결과 목록 청구 카드 상세 조회")
    wait_url_contains(page, RESULT_DETAIL_URL_FRAGMENT, timeout_ms)


def detail_section(page):
    heading = page.get_by_role("heading", name=DETAIL_SECTION_HEADING).first
    common.wait_locator_visible_with_log(heading, common.MAX_TIMEOUT_MS, "보험금청구 내용 섹션")
    return heading.locator(
        "xpath=ancestor::article[1] | ancestor::div[contains(@class,'article')][1]"
    )


def detail_value(page, _table, header_name: str, cell_index: int = 0) -> str:
    del cell_index
    value = page.evaluate(
        """
        (label) => {
            const normalize = (input) => (input || '').replace(/\\s+/g, ' ').trim();
            const isVisible = (element) => {
                if (!element) {
                    return false;
                }
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            };
            const items = Array.from(document.querySelectorAll('main li')).filter((element) => isVisible(element));
            for (const item of items) {
                const text = normalize(item.innerText);
                if (!text.startsWith(label)) {
                    continue;
                }
                const cells = Array.from(item.querySelectorAll(':scope > *')).map((element) => normalize(element.innerText));
                if (cells.length >= 2 && cells[0] === label) {
                    return cells[1];
                }
                return normalize(text.slice(label.length));
            }
            return '';
        }
        """,
        header_name,
    )
    normalized = normalize_text(value)
    if not normalized:
        raise RuntimeError(f"상세 화면에서 '{header_name}' 값을 찾지 못했습니다.")
    return normalized


def wait_for_result02_detail_ready(page, timeout_ms: int, expected_receipt_number: str):
    wait_url_contains(page, RESULT_DETAIL_URL_FRAGMENT, timeout_ms)
    initial_wait_ms = min(2000, timeout_ms)
    common.wait_timeout_with_log(page, initial_wait_ms, "결과 상세 데이터 초기 안정화")
    expected = normalize_receipt_number(expected_receipt_number)

    for _ in range(max(1, timeout_ms // 400)):
        try:
            receipt_number = normalize_receipt_number(detail_value(page, None, "접수번호"))
        except Exception:
            receipt_number = ""
        if receipt_number == expected:
            return detail_section(page)
        common.wait_timeout_with_log(page, 400, "결과 상세 데이터 반영 대기")

    raise RuntimeError(
        f"결과 상세 화면 접수번호 데이터가 기대값으로 채워지지 않았습니다: expected={expected_receipt_number}"
    )


def result_table(page):
    _ensure_result_list_page(page, common.MAX_TIMEOUT_MS)
    return claim_cards(page)
