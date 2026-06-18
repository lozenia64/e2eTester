from __future__ import annotations

import asyncio

from app.core.models import SuiteEvent, SuiteRun
from app.storage.listener_registry import ListenerRegistry


class InMemorySuiteRepository:
    """``SuiteRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``SqliteSuiteRepository`` 로 교체한다(동일 포트).
    """

    def __init__(self) -> None:
        self._suites: dict[str, SuiteRun] = {}
        self._listeners: ListenerRegistry[SuiteEvent] = ListenerRegistry()
        self._lock = asyncio.Lock()

    async def create_suite(self, suite: SuiteRun) -> SuiteRun:
        async with self._lock:
            self._suites[suite.suite_id] = suite
        return suite

    async def save_suite(self, suite: SuiteRun) -> SuiteRun:
        async with self._lock:
            self._suites[suite.suite_id] = suite
        return suite

    async def get_suite(self, suite_id: str) -> SuiteRun:
        async with self._lock:
            return self._suites[suite_id]

    async def list_suites(self) -> list[SuiteRun]:
        async with self._lock:
            return list(self._suites.values())

    async def publish(self, event: SuiteEvent) -> None:
        await self._listeners.publish(event.suite_id, event)

    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]:
        return await self._listeners.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None:
        await self._listeners.unsubscribe(suite_id, queue)
