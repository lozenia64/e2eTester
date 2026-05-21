from __future__ import annotations

import re
from pathlib import Path

import hom_login_common as common

CHARGE00_FRAGMENT = "/fplaza/compensation/charge00.do"
CHARGE01_FRAGMENT = "/fplaza/compensation/charge01.do"
CHARGE02_FRAGMENT = "/fplaza/compensation/charge02.do"
POPUP_CONFIRM_PATTERN = re.compile(r"보험금청구를 위한 필요서류는 확인하셨나요")
READY_LINK_PATTERN = re.compile(r"준비가 된 상태")
STEP02_HEADING_PATTERN = re.compile(r"청구대상자\s*선택|질병/상해\s*보험금청구")


def _wait_url_contains(page, fragment: str, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "f => window.location.href.includes(f)",
        arg=fragment,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def _open_charge00_from_menu(page, timeout_ms: int) -> bool:
    common.maybe_close_post_login_popup(page, timeout_ms)
    try:
        bosang = page.get_by_role("link", name=re.compile(r"^보상$")).first
        if not bosang.is_visible(timeout=2000):
            return False
        print("[step] Hover GNB 보상")
        bosang.hover(timeout=timeout_ms)
        common.wait_timeout_with_log(page, 600, "보상 메뉴 펼침 대기")
        link = common.first_visible_locator(
            page.locator(f'a[href*="{CHARGE00_FRAGMENT}"]'),
            "보상 메뉴의 charge00 링크",
        )
        common.click_with_log(link, "보상 > … > 보험금청구 접수(charge00) 메뉴 클릭")
        _wait_url_contains(page, "charge00.do", timeout_ms)
        return True
    except Exception as exc:
        print(f"[warn] 메뉴로 charge00 이동 실패, 직접 URL 시도: {exc}")
        return False


def _goto_charge00(page, config: common.LoginConfig) -> None:
    if not _open_charge00_from_menu(page, config.timeout_ms):
        common.maybe_close_post_login_popup(page, config.timeout_ms)
        base = config.base_url.rstrip("/")
        common.open_url(page, f"{base}{CHARGE00_FRAGMENT}")
        _wait_url_contains(page, "charge00.do", config.timeout_ms)


def _click_first_visible_href(page, href_substring: str, description: str, timeout_ms: int) -> None:
    link = common.first_visible_locator(
        page.locator(f'a[href*="{href_substring}"]'),
        description,
    )
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        common.click_with_log(link, description)


def _open_document_check_popup(page, timeout_ms: int) -> None:
    apply_link = common.first_visible_locator(
        page.get_by_role("link", name=re.compile(r"보험금청구\s*신청")),
        "보험금청구신청(팝업 호출)",
    )
    common.click_with_log(apply_link, "보험금청구신청 클릭 (문서확인 팝업)")
    popup_marker = page.get_by_text(POPUP_CONFIRM_PATTERN).first
    common.wait_locator_visible_with_log(popup_marker, timeout_ms, "필요서류 확인 팝업")


def _confirm_ready_and_go_charge02(page, timeout_ms: int) -> None:
    ready = common.first_visible_locator(
        page.get_by_role("link", name=READY_LINK_PATTERN),
        "팝업: 준비가 된 상태입니다 링크",
    )
    print("[click] 팝업에서 서류 준비 완료 확인(준비가 된 상태)")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        try:
            ready.click(timeout=timeout_ms)
        except Exception:
            ready.click(force=True, timeout=timeout_ms)
    _wait_url_contains(page, "charge02.do", timeout_ms)


def _assert_charge02_landed(page, timeout_ms: int) -> None:
    for _ in range(max(1, timeout_ms // 500)):
        url_ok = "charge02.do" in page.url
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        text_ok = bool(STEP02_HEADING_PATTERN.search(body_text))
        if url_ok and text_ok:
            return
        common.wait_timeout_with_log(page, 400, "charge02 화면 요소 대기")
    raise RuntimeError(
        "보험금청구 charge02 화면(청구대상자 선택 등)을 확인하지 못했습니다.",
    )


def run(page, config: common.LoginConfig, screenshot_path: Path) -> str:
    try:
        _goto_charge00(page, config)
        _click_first_visible_href(
            page,
            "charge01.do",
            "charge00 → charge01 (보험금청구신청 단계 진입)",
            config.timeout_ms,
        )
        _open_document_check_popup(page, config.timeout_ms)
        _confirm_ready_and_go_charge02(page, config.timeout_ms)
        _assert_charge02_landed(page, config.timeout_ms)
        common.save_screenshot(page, screenshot_path)
        return f"보험금청구 접수 프로세스 charge02 도달 성공 ({page.url})"
    except Exception:
        common.save_screenshot(page, screenshot_path)
        raise
