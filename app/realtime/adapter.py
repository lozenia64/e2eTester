"""WebSocket 리스너 레지스트리 — 저장소 계층에서 분리된 실시간 어댑터."""

from __future__ import annotations

import asyncio

from app.core.run_models import DashboardEvent
from app.core.suite_models import SuiteEvent
from app.realtime.listener_registry import ListenerRegistry
from app.realtime.ports import RealtimeFanOutPort
from app.realtime.redis_fanout import (
    deserialize_dashboard_event,
    deserialize_suite_event,
    serialize_dashboard_event,
    serialize_suite_event,
)


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

    def disable_fanout(self) -> None:
        """Redis 연결 실패 시 로컬-only 로 강등한다(어댑터 재할당이 아니라 내부 상태 변경).

        이 어댑터 인스턴스는 이미 run_service/suite_service/RealtimeProjector 에
        참조로 주입돼 있으므로, 컨테이너 필드를 새 인스턴스로 바꿔치기해도 그
        의존자들은 여전히 옛 인스턴스를 본다. fanout 을 여기서 끊어야 실제로 반영된다.
        """
        self._fanout = None

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

    def disable_fanout(self) -> None:
        """Redis 연결 실패 시 로컬-only 로 강등한다(어댑터 재할당이 아니라 내부 상태 변경)."""
        self._fanout = None

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
