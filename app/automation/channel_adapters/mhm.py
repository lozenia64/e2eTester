"""MHM(모바일) 채널 어댑터 — main_access 사전 조건(모바일 모드 적용 검증)."""

from __future__ import annotations

from playwright.sync_api import Page


class MhmChannelAdapter:
    def ensure_navigation_precondition(self, page: Page) -> None:
        if not getattr(page, "_mhm_mobile_mode_applied", False):
            raise RuntimeError(
                "m.hwgeneralins.com 접속 전에 모바일 디바이스 모드가 적용되어야 합니다. "
                "브라우저 기동 → 모바일 모드 전환 → 접속 순서를 지키세요."
            )
