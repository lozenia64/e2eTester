"""WebSocket 리스너 레지스트리 — 저장소 계층에서 분리된 실시간 어댑터."""

from __future__ import annotations

import asyncio

from app.core.models import DashboardEvent
from app.storage.listener_registry import ListenerRegistry


class RealtimeNotificationAdapter:
    """``RealtimeNotificationPort`` 구현 — key(run_id) 별 DashboardEvent 큐 fan-out."""

    def __init__(self) -> None:
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)
