from __future__ import annotations

from app.runner.step_logging import log

from . import browser


def run(page, base_url: str) -> str:
    """대상 시스템의 메인화면에 직접 접속하고 초기 팝업을 정리한다."""
    log(
        f"[wait] Start direct navigation: {base_url} ({browser.MAIN_ACCESS_TIMEOUT_MS} ms main access)"
    )
    page.goto(base_url, wait_until="domcontentloaded", timeout=browser.MAIN_ACCESS_TIMEOUT_MS)
    log(f"[wait] End direct navigation: {base_url} -> {page.url}")
    browser.maybe_close_popup(page)
    return "메인화면 접속 성공"
