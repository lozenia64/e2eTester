from __future__ import annotations

from pathlib import Path
import re
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from . import login_common as common


PROOF_LIST_FRAGMENT = "/fplaza/proof/list.do"
LONG_TERM_POLICY_FRAGMENT = "/fplaza/proof/ioltrh070.do"
POLICY_TABLE_CAPTION = "보험계약 선택"
DOWNLOAD_IFRAME_SELECTOR = "iframe#filedownload"
DOWNLOAD_IFRAME_FRAGMENT = "/fileDownloadAndViiew.json"
SUCCESS_DIALOG_TEXT = "PDF 파일 다운로드가 완료되었습니다."
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


def _wait_url_contains(page, fragment: str, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "fragment => window.location.href.includes(fragment)",
        arg=fragment,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def _first_visible_candidate(candidates, description: str):
    for candidate in candidates:
        try:
            if candidate.count() == 0:
                continue
            if candidate.first.is_visible(timeout=1200):
                return candidate.first
        except Exception:
            continue
    raise RuntimeError(f"표시 중인 요소를 찾지 못했습니다: {description}")


def _find_long_term_policy_link(page):
    candidates = [
        page.locator(f'a[href*="{LONG_TERM_POLICY_FRAGMENT}"]:visible'),
        page.get_by_role("link", name=re.compile(r"장기보험\s*증권")),
        page.locator('a:has-text("장기보험증권")'),
    ]

    for candidate in candidates:
        try:
            if candidate.count() == 0:
                continue
            if candidate.first.is_visible(timeout=1200):
                return candidate.first
        except Exception:
            continue

    return None


def _open_proof_menu(page, timeout_ms: int) -> None:
    menu = _first_visible_candidate(
        [
            page.get_by_role("link", name=re.compile(r"^증명서\s*발급$")),
            page.locator("header").get_by_text("증명서 발급", exact=True),
            page.get_by_text("증명서 발급", exact=True),
        ],
        "증명서 발급 GNB 메뉴",
    )

    print("[step] Open 증명서 발급 GNB menu")
    try:
        menu.hover(timeout=timeout_ms)
        common.wait_timeout_with_log(page, 600, "증명서 발급 메뉴 펼침 대기")
    except Exception as exc:
        print(f"[warn] 증명서 발급 메뉴 hover 실패, 목록 페이지 직접 이동으로 대체: {exc}")


def _navigate_to_long_term_policy(page, config: common.LoginConfig) -> None:
    common.maybe_close_post_login_popup(page, config.timeout_ms)

    policy_link = _find_long_term_policy_link(page)
    if policy_link is None:
        try:
            _open_proof_menu(page, config.timeout_ms)
        except Exception as exc:
            print(f"[warn] 증명서 발급 메뉴 접근 실패: {exc}")
        policy_link = _find_long_term_policy_link(page)

    if policy_link is None:
        base_url = config.base_url.rstrip("/")
        common.open_url(page, f"{base_url}{PROOF_LIST_FRAGMENT}")
        _wait_url_contains(page, PROOF_LIST_FRAGMENT, config.timeout_ms)
        policy_link = _find_long_term_policy_link(page)

    if policy_link is None:
        raise RuntimeError("장기보험증권 메뉴 링크를 찾지 못했습니다.")

    common.click_with_log(policy_link, "증명서 발급 > 장기보험증권 이동")
    _wait_url_contains(page, LONG_TERM_POLICY_FRAGMENT, config.timeout_ms)
    common.wait_timeout_with_log(page, 3000, "장기보험증권 화면 진입 후 계약 조회 안정화 대기")


def _find_visible_table_by_caption(page, caption_text: str, description: str):
    tables = page.locator("table")
    normalized_caption = _normalize_text(caption_text)

    for index in range(tables.count()):
        table = tables.nth(index)
        try:
            if not table.is_visible(timeout=800):
                continue
            caption = table.locator("caption").first
            if caption.count() == 0:
                continue
            if normalized_caption in _normalize_text(caption.inner_text(timeout=800)):
                return table
        except Exception:
            continue

    raise RuntimeError(f"표시 중인 표를 찾지 못했습니다: {description}")


def _click_radio_with_fallback(page, radio, description: str, timeout_ms: int) -> None:
    radio_id = radio.get_attribute("id") or ""
    try:
        print(f"[click] {description}: input 직접 클릭")
        radio.click(force=True, timeout=timeout_ms)
    except Exception as exc:
        if not radio_id:
            raise RuntimeError(f"{description} 클릭에 실패했습니다: {exc}") from exc

        label = page.locator(f'label[for="{radio_id}"]').first
        if label.count() == 0:
            raise RuntimeError(f"{description} 클릭에 실패했고 연결된 라벨도 찾지 못했습니다: {exc}") from exc

        print(f"[warn] {description}: input 클릭 실패, 라벨 클릭으로 재시도: {exc}")
        common.click_with_log(label, f"{description} 라벨 클릭")


def _select_first_contract(page, timeout_ms: int) -> str:
    table = _find_visible_table_by_caption(page, POLICY_TABLE_CAPTION, "보험계약 선택 표")
    rows = table.locator("tbody tr")
    row_count = rows.count()
    print(f"[step] 보험계약 선택 표 행 수: {row_count}")
    if row_count < 1:
        raise RuntimeError("보험계약 선택 테이블에 발급 가능한 항목이 없습니다.")

    radio = common.first_visible_locator(table.get_by_role("radio"), "보험계약 선택 라디오")
    policy_value = radio.get_attribute("value") or ""
    policy_name = radio.get_attribute("name") or "contract_no"

    print(f"[step] Select first contract for certificate issue: {policy_value}")
    _click_radio_with_fallback(page, radio, "보험계약 선택 라디오", timeout_ms)
    page.wait_for_function(
        """
        ({name, value}) => {
            const radios = Array.from(document.querySelectorAll(`input[name="${name}"]`));
            return radios.some((radio) => radio.value === value && radio.checked);
        }
        """,
        arg={"name": policy_name, "value": policy_value},
        timeout=timeout_ms,
    )
    return policy_value


def _select_download_method(page, timeout_ms: int) -> None:
    radio = _first_visible_candidate(
        [
            page.locator('input[name="chk_type"][value="1"]'),
            page.get_by_role("radio", name=re.compile(r"^다운로드$")),
        ],
        "다운로드 발급방법 라디오",
    )
    print("[step] Select download issue method")
    _click_radio_with_fallback(page, radio, "다운로드 발급방법 라디오", timeout_ms)
    page.wait_for_function(
        """
        () => {
            const radio = document.querySelector('input[name="chk_type"][value="1"]');
            return !!radio && radio.checked;
        }
        """,
        timeout=timeout_ms,
    )


def _wait_for_download_trigger(page, timeout_ms: int) -> bool:
    try:
        page.wait_for_function(
            """
            ({selector, fragment}) => {
                const iframe = document.querySelector(selector);
                if (!iframe) {
                    return false;
                }
                return (iframe.getAttribute('src') || '').includes(fragment);
            }
            """,
            arg={"selector": DOWNLOAD_IFRAME_SELECTOR, "fragment": DOWNLOAD_IFRAME_FRAGMENT},
            timeout=timeout_ms,
        )
        print("[step] Hidden iframe download trigger detected")
        return True
    except PlaywrightTimeoutError:
        print("[warn] Hidden iframe download trigger를 확인하지 못했습니다.")
        return False


def _wait_for_issue_dialog(page, dialog_messages: list[str], start_index: int, timeout_ms: int) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        for message in dialog_messages[start_index:]:
            normalized = _normalize_text(message)
            if SUCCESS_DIALOG_TEXT in normalized:
                print(f"[step] Download success dialog detected: {normalized}")
                return normalized
            for pattern in FAILURE_DIALOG_PATTERNS:
                if pattern in normalized:
                    raise RuntimeError(f"장기보험증권 발급 실패: {normalized}")
        page.wait_for_timeout(250)

    raise RuntimeError("장기보험증권 PDF 다운로드 완료 알림을 확인하지 못했습니다.")


def _issue_certificate(page, dialog_messages: list[str], timeout_ms: int, artifact_dir: Path) -> str:
    issue_button = _first_visible_candidate(
        [
            page.locator('a[onclick*="reqIssue"]'),
            page.get_by_role("link", name=re.compile(r"^증명서발급$")),
        ],
        "증명서발급 버튼",
    )

    dialog_index = len(dialog_messages)
    download = None
    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            common.click_with_log(issue_button, "증명서발급 버튼 클릭")
        download = download_info.value
        print(f"[step] Playwright download event captured: {download.suggested_filename}")
    except PlaywrightTimeoutError as exc:
        print(f"[warn] Playwright download event 미포착, DOM/알림 기반으로 검증 계속: {exc}")

    iframe_detected = _wait_for_download_trigger(page, timeout_ms)
    _wait_for_issue_dialog(page, dialog_messages, dialog_index, timeout_ms)

    if download is not None:
        filename = download.suggested_filename or "long_term_policy_certificate.pdf"
        target_path = artifact_dir / filename
        download.save_as(str(target_path))
        print(f"[artifact] Download saved to {target_path}")
        return filename

    if iframe_detected:
        return "browser-managed download"

    raise RuntimeError("PDF 다운로드 성공 여부를 확인하지 못했습니다.")


def run(page, config: common.LoginConfig, artifact_dir: Path, dialog_messages: list[str]) -> str:
    _navigate_to_long_term_policy(page, config)
    selected_policy = _select_first_contract(page, config.timeout_ms)
    _select_download_method(page, config.timeout_ms)
    download_result = _issue_certificate(page, dialog_messages, config.timeout_ms, artifact_dir)
    return f"장기보험증권 증명서 발급 성공: {selected_policy} ({download_result})"