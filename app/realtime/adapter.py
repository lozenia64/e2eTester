"""WebSocket 리스너 레지스트리 — 저장소 계층에서 분리된 실시간 어댑터."""

from __future__ import annotations

import asyncio

from app.core.models import DashboardEvent, SuiteEvent
from app.realtime.ports import RealtimeFanOutPort
from app.realtime.redis_fanout import (
    deserialize_dashboard_event,
    deserialize_suite_event,
    serialize_dashboard_event,
    serialize_suite_event,
)
from app.storage.listener_registry import ListenerRegistry


class RealtimeNotificationAdapter:
    """``RealtimeNotificationPort`` 구현 — 로컬 + 선택적 Redis fan-out."""

    def __init__(self, fanout: RealtimeFanOutPort | None = None) -> None:
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()
        self._fanout = fanout

    async def start(self) -> None:
        if self._fanout is None:
            return
        await self._fanout.subscribe("runs", self._on_remote_run_event)

    async def stop(self) -> None:
        pass

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)
        if self._fanout is not None:
            await self._fanout.publish(
                "runs",
                serialize_dashboard_event(event),
            )

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)

    async def _on_remote_run_event(self, payload: str) -> None:
        event = deserialize_dashboard_event(payload)
        await self._listeners.publish(event.run_id, event)


class SuiteRealtimeNotificationAdapter:
    """``SuiteRealtimeNotificationPort`` 구현 — 로컬 + 선택적 Redis fan-out."""

    def __init__(self, fanout: RealtimeFanOutPort | None = None) -> None:
        self._listeners: ListenerRegistry[SuiteEvent] = ListenerRegistry()
        self._fanout = fanout

    async def start(self) -> None:
        if self._fanout is None:
            return
        await self._fanout.subscribe("suites", self._on_remote_suite_event)

    async def stop(self) -> None:
        pass

    async def publish(self, event: SuiteEvent) -> None:
        await self._listeners.publish(event.suite_id, event)
        if self._fanout is not None:
            await self._fanout.publish(
                "suites",
                serialize_suite_event(event),
            )

    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]:
        return await self._listeners.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None:
        await self._listeners.unsubscribe(suite_id, queue)

    async def _on_remote_suite_event(self, payload: str) -> None:
        event = deserialize_suite_event(payload)
        await self._listeners.publish(event.suite_id, event)
