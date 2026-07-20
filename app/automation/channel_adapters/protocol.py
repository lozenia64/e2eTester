"""채널별 사전 조건 어댑터 Protocol — 포팅하는 스텝이 요구하는 메서드만 점진적으로 확장."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from playwright.sync_api import Page


@runtime_checkable
class ChannelAdapter(Protocol):
    def ensure_navigation_precondition(self, page: Page) -> None:
        """이 채널로 접속하기 전에 성립해야 하는 사전 조건을 검증한다(불충족 시 예외).

        PC는 조건이 없으므로 no-op, 모바일은 디바이스 모드 적용 여부를 검증한다.
        """
        ...
