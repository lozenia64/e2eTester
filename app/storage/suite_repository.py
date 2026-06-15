from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.models import SuiteEvent, SuiteRun


class InMemorySuiteRepository:
    def __init__(self) -> None:
        self._suites: dict[str, SuiteRun] = {}
        self._listeners: dict[str, list[asyncio.Queue[SuiteEvent]]] = defaultdict(list)
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
        listeners = list(self._listeners.get(event.suite_id, []))
        for queue in listeners:
            await queue.put(event)

    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]:
        queue: asyncio.Queue[SuiteEvent] = asyncio.Queue()
        self._listeners[suite_id].append(queue)
        return queue

    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None:
        listeners = self._listeners.get(suite_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and suite_id in self._listeners:
            del self._listeners[suite_id]
