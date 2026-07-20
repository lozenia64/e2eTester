"""테스트용 ChannelAdapter 더블 — Playwright 없이 호출만 기록."""

from __future__ import annotations

from playwright.sync_api import Page


class FakeChannelAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def ensure_navigation_precondition(self, page: Page) -> None:
        self.calls.append(("ensure_navigation_precondition", (page,), {}))
