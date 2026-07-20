"""메인화면 접속 워크플로 — 채널 어댑터 + 채널 무관 L2 로직."""

from __future__ import annotations

import re

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.automation.channel_adapters.protocol import ChannelAdapter
from app.runner.step_logging import log

MAIN_ACCESS_TIMEOUT_MS = 20_000


class MainAccessWorkflow:
    def run(self, adapter: ChannelAdapter, page: Page, base_url: str) -> str:
        adapter.ensure_navigation_precondition(page)
        log(f"[wait] Start direct navigation: {base_url} ({MAIN_ACCESS_TIMEOUT_MS} ms main access)")
        page.goto(base_url, wait_until="domcontentloaded", timeout=MAIN_ACCESS_TIMEOUT_MS)
        log(f"[wait] End direct navigation: {base_url} -> {page.url}")
        _close_home_popup(page)
        return "메인화면 접속 성공"


def _close_home_popup(page: Page) -> None:
    # app/automation/page_objects/{hom,mhm}/login_common.py:maybe_close_home_popup 과 동일.
    close_button = page.get_by_role("button", name=re.compile("닫기"))
    try:
        if close_button.first.is_visible(timeout=3000):
            log("[click] Close landing popup")
            close_button.first.click()
            log("[step] Closed landing popup")
    except PlaywrightTimeoutError:
        return
