"""HOM(PC) 채널 어댑터 — main_access 사전 조건(no-op)."""

from __future__ import annotations

from playwright.sync_api import Page


class HomChannelAdapter:
    def ensure_navigation_precondition(self, page: Page) -> None:
        return None
