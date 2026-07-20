"""ChannelAdapter 호출 기록 데코레이터 — shadow-diff·특성화 테스트용."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import BrowserContext, Page

from app.automation.channel_adapters.protocol import ChannelAdapter


class RecordingChannelAdapter:
    """임의의 ``ChannelAdapter`` 구현을 감싸 호출 순서·인자를 기록한다.

    ``enabled=True`` 일 때만 Playwright ``context.tracing`` 을 시작한다(기본 비활성).
    """

    def __init__(
        self,
        inner: ChannelAdapter,
        *,
        enabled: bool = False,
        context: BrowserContext | None = None,
    ) -> None:
        self._inner = inner
        self._enabled = enabled
        self._context = context
        self.calls: list[tuple[str, tuple, dict]] = []

    def ensure_navigation_precondition(self, page: Page) -> None:
        self.calls.append(("ensure_navigation_precondition", (page,), {}))
        self._start_tracing_if_enabled()
        return self._inner.ensure_navigation_precondition(page)

    def _start_tracing_if_enabled(self) -> None:
        if not self._enabled:
            return
        if self._context is None:
            return
        # 실제 트레이싱은 후속 단계에서 배선 — 지금은 시그니처만 마련.
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
