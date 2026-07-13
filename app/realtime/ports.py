"""실시간 알림(WebSocket fan-out) 포트."""

from __future__ import annotations

import asyncio
from typing import Protocol

from app.core.run_models import DashboardEvent
from app.core.suite_models import SuiteEvent


class RealtimeNotificationPort(Protocol):
    """Run 대시보드 WebSocket 이벤트의 fan-out 경계."""

    async def publish(self, event: DashboardEvent) -> None: ...
    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]: ...
    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None: ...


class SuiteRealtimeNotificationPort(Protocol):
    """Suite WebSocket 이벤트의 fan-out 경계."""

    async def publish(self, event: SuiteEvent) -> None: ...
    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]: ...
    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None: ...


class RealtimeFanOutPort(Protocol):
    """크로스 인스턴스 실시간 이벤트 브로드캐스트 경계."""

    async def publish(self, channel: str, payload: str) -> None: ...
    async def subscribe(self, channel: str, handler) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
