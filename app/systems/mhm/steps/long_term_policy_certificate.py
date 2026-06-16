from __future__ import annotations

from pathlib import Path
import re
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from . import login_common as common

PROOF_TAB_SELECTOR = '[id="05000000"]'
PROOF_ENTRY_MENU_SELECTOR = "#code05010000"
CERT_LIST_HEADING_TEXT = "필요한 증명서를 선택하세요"
POLICY_CERT_LINK_TEXT = "보험증권(장기/자동차)"
POLICY_PAGE_HEADING_TEXT = "보험증권(장기/자동차)을 발급하실 수 있습니다"
CONTRACT_DIALOG_SELECTOR = ".dialog.full.show"
ALERT_DIALOG_SELECTOR = ".dialog.modal.alert.show, .dialog.show"
SUCCESS_DIALOG_TEXT = re.compile(r"PDF\s*파일\s*다운로드가\s*완료되었습니다")
FAILURE_DIALOG_PATTERNS: tuple[str, ...] = (
    "PDF 파일 다운로드를 실패하였습니다.",
    "PDF 파일 다운로드 중 오류가 발생했습니다.",
    "발급 신청 건이 없습니다.",
    "선택된 건이 없습니다.",
    "증권발행이 불가합니다.",
    "갱신보험료 미확정으로 증권발행이 제한됩니다.",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _close_gnb_menu_if_open(page) -> None:
    try:
        gnb_open = page.evaluate(
            """
            () => {
                const gnb = document.querySelector('#gnb.mhm_gnb');
                return !!(gnb && gnb.getAttribute('aria-hidden') === 'false');
            }
            """
        )
    except Exception:
        return
    if not gnb_open:
        return

    close_button = page.locator("#gnb a.btn_gnb_close").first
    try:
        common.click_with_log(close_button, "전체메뉴 닫기")
    except Exception:
        page.evaluate(
            """
            () => {
                const closeButton = document.querySelector('#gnb a.btn_gnb_close');
                if (closeButton) {
                    closeButton.click();
                }
            }
            """
        )
    common.wait_timeout_with_log(page, 400, "전체메뉴 닫힘 대기")


def _open_hamburger_menu(page, timeout_ms: int) -> None:
    try:
        close_button = page.get_by_role("button", name=re.compile(r"전체\s*메뉴\s*닫기"))
        if close_button.is_visible(timeout=800):
            return
    except Exception:
        pass

    open_candidates = [
        page.locator("#btnGnb").first,
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


def _click_alert_dialog_button(
    page,
    dialog_text: str | re.Pattern[str],
    button_name: str,
    log_label: str,
    timeout_ms: int,
) -> None:
    dialog = page.locator(ALERT_DIALOG_SELECTOR).filter(has_text=dialog_text).first
    common.wait_locator_visible_with_log(dialog, timeout_ms, log_label)
    button = dialog.get_by_role("button", name=button_name, exact=True).first
    common.click_with_log(button, log_label)


def _scroll_gnb_item_into_view(page, selector: str) -> None:
    page.evaluate(
        """
        (selector) => {
            const item = document.querySelector(`#gnb ${selector}`);
            if (!item) {
                return false;
            }
            item.scrollIntoView({ block: 'center', inline: 'center' });
            const scrollHost = item.closest('.nav_area')
                || item.closest('.menu_area')
                || item.closest('.mhm_gnb_body');
            if (!scrollHost) {
                return true;
            }
            const rect = item.getBoundingClientRect();
            const hostRect = scrollHost.getBoundingClientRect();
            if (rect.left < hostRect.left || rect.right > hostRect.right) {
                scrollHost.scrollLeft += rect.left - hostRect.left - (hostRect.width / 2) + (rect.width / 2);
            }
            if (rect.top < hostRect.top || rect.bottom > hostRect.bottom) {
                scrollHost.scrollTop += rect.top - hostRect.top - (hostRect.height / 2) + (rect.height / 2);
            }
            return true;
        }
        """,
        selector,
    )


def _click_gnb_item(page, selector: str, log_label: str, timeout_ms: int) -> None:
    locator = page.locator(f"#gnb {selector}").first
    common.wait_locator_visible_with_log(locator, timeout_ms, log_label)
    _scroll_gnb_item_into_view(page, selector)
    common.wait_timeout_with_log(page, 200, f"{log_label} GNB 스크롤 안정화")

    try:
        common.click_with_log(locator, log_label)
        return
    except Exception as exc:
        print(f"[warn] {log_label} 일반 클릭 실패: {exc}")

    clicked = page.evaluate(
        """
        (selector) => {
            const item = document.querySelector(`#gnb ${selector}`);
            if (!item) {
                return false;
            }
            item.scrollIntoView({ block: 'center', inline: 'center' });
            item.click();
            return true;
        }
        """,
        selector,
    )
    if clicked:
        print(f"[click] {log_label} (JS fallback)")
        common.wait_timeout_with_log(page, 400, f"{log_label} 후 안정화")
        return

    print(f"[warn] {log_label} JS 클릭 실패, force 클릭 재시도")
    locator.click(force=True, timeout=min(timeout_ms, 5000))
    common.wait_timeout_with_log(page, 400, f"{log_label} 후 안정화")


def _navigate_to_certificate_list(page, timeout_ms: int) -> None:
    common.maybe_close_post_login_popup(page, timeout_ms)
    _close_gnb_menu_if_open(page)
    _open_hamburger_menu(page, timeout_ms)

    _click_gnb_item(page, PROOF_TAB_SELECTOR, "전체메뉴 증명서발급 탭", timeout_ms)
    common.wait_timeout_with_log(page, 400, "증명서발급 탭 전환 대기")

    _click_gnb_item(page, PROOF_ENTRY_MENU_SELECTOR, "전체메뉴 증명서발급 메뉴", timeout_ms)
    _close_gnb_menu_if_open(page)

    heading = page.get_by_role("heading", name=CERT_LIST_HEADING_TEXT).first
    common.wait_locator_visible_with_log(heading, timeout_ms, "증명서 선택 화면")


def _open_long_term_policy_certificate(page, timeout_ms: int) -> None:
    policy_link = (
        page.locator(".cert_select_2")
        .locator("a[title='페이지 이동'], a[role='button']")
        .filter(has_text=POLICY_CERT_LINK_TEXT)
        .first
    )
    common.click_with_log(policy_link, "공통 > 보험증권(장기/자동차) 선택")

    heading = page.get_by_role("heading", name=POLICY_PAGE_HEADING_TEXT).first
    common.wait_locator_visible_with_log(heading, timeout_ms, "보험증권(장기/자동차) 발급 화면")
    long_term_tab = page.locator("#ltins").first
    common.wait_locator_visible_with_log(long_term_tab, timeout_ms, "장기보험증권 탭")


def _select_first_contract(page, timeout_ms: int) -> str:
    contract_button = page.locator(".certificate_list a.btn").filter(has_text="계약 선택").first
    common.click_with_log(contract_button, "계약 선택 열기")

    dialog = page.locator(CONTRACT_DIALOG_SELECTOR).filter(has_text="계약 선택").first
    common.wait_locator_visible_with_log(dialog, timeout_ms, "계약 선택 시트")

    contract_items = dialog.locator(".list.box a.btn.inner")
    if contract_items.count() < 1:
        raise RuntimeError("계약 선택 시트에 발급 가능한 계약이 없습니다.")

    contract = contract_items.first
    contract_text = _normalize_text(contract.inner_text(timeout=1000))
    policy_number_match = re.search(r"(LA|FA)\d[\d*]+", contract_text)
    policy_number = policy_number_match.group(0) if policy_number_match else contract_text[:40]
    common.click_with_log(contract, f"계약 선택: {policy_number}")

    confirm = dialog.get_by_role("button", name="확인", exact=True).first
    common.click_with_log(confirm, "계약 선택 시트 확인")
    common.wait_timeout_with_log(page, 400, "계약 선택 반영 대기")
    print(f"[step] Selected contract for certificate issue: {policy_number}")
    return policy_number


def _select_download_method(page, timeout_ms: int) -> None:
    download_tab = page.locator("#issueMtdDownload").first
    common.click_with_log(download_tab, "발급방법 다운로드 선택")
    page.wait_for_function(
        """
        () => {
            const tab = document.querySelector('#issueMtdDownload');
            return !!tab && tab.getAttribute('aria-selected') === 'true';
        }
        """,
        timeout=timeout_ms,
    )


def _wait_for_issue_button_enabled(page, timeout_ms: int) -> None:
    issue_button = page.locator(".fixed_bottom_button button.btn.s1.c1").first
    common.wait_locator_visible_with_log(issue_button, timeout_ms, "증명서 발급 버튼")
    page.wait_for_function(
        """
        () => {
            const button = document.querySelector('.fixed_bottom_button button.btn.s1.c1');
            return !!button && !button.disabled;
        }
        """,
        timeout=timeout_ms,
    )


def _wait_for_issue_result(page, dialog_messages: list[str], start_index: int, timeout_ms: int) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        try:
            success_dialog = page.locator(ALERT_DIALOG_SELECTOR).filter(has_text=SUCCESS_DIALOG_TEXT).first
            if success_dialog.is_visible(timeout=400):
                print("[step] PDF download success alert detected")
                return
        except Exception:
            pass

        for message in dialog_messages[start_index:]:
            normalized = _normalize_text(message)
            if SUCCESS_DIALOG_TEXT.search(normalized):
                print(f"[step] Download success dialog detected: {normalized}")
                return
            for pattern in FAILURE_DIALOG_PATTERNS:
                if pattern in normalized:
                    raise RuntimeError(f"장기보험증권 발급 실패: {normalized}")
        page.wait_for_timeout(250)

    raise RuntimeError("장기보험증권 PDF 다운로드 완료 알림을 확인하지 못했습니다.")


def _issue_certificate(page, dialog_messages: list[str], timeout_ms: int, artifact_dir: Path) -> str:
    _wait_for_issue_button_enabled(page, timeout_ms)
    issue_button = page.locator(".fixed_bottom_button button.btn.s1.c1").first

    dialog_index = len(dialog_messages)
    download = None
    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            common.click_with_log(issue_button, "증명서 발급 버튼 클릭")
        download = download_info.value
        print(f"[step] Playwright download event captured: {download.suggested_filename}")
    except PlaywrightTimeoutError as exc:
        print(f"[warn] Playwright download event 미포착, UI 알림 기반으로 검증 계속: {exc}")

    _wait_for_issue_result(page, dialog_messages, dialog_index, timeout_ms)

    try:
        _click_alert_dialog_button(
            page,
            SUCCESS_DIALOG_TEXT,
            "확인",
            "PDF 다운로드 완료 알림 확인",
            timeout_ms,
        )
    except Exception as exc:
        print(f"[warn] PDF 다운로드 완료 UI 알림 닫기 실패: {exc}")

    if download is not None:
        filename = download.suggested_filename or "long_term_policy_certificate.pdf"
        target_path = artifact_dir / filename
        download.save_as(str(target_path))
        print(f"[artifact] Download saved to {target_path}")
        return filename

    return "browser-managed download"


def run(page, config: common.LoginConfig, dialog_messages: list[str], artifact_dir: Path) -> str:
    _navigate_to_certificate_list(page, config.timeout_ms)
    _open_long_term_policy_certificate(page, config.timeout_ms)
    selected_policy = _select_first_contract(page, config.timeout_ms)
    _select_download_method(page, config.timeout_ms)
    download_result = _issue_certificate(
        page,
        dialog_messages,
        config.timeout_ms,
        artifact_dir,
    )
    return f"장기보험증권 증명서 발급 성공: {selected_policy} ({download_result})"
