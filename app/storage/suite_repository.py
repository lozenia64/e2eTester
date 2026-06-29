from __future__ import annotations

import asyncio

from app.core.models import SuiteEvent, SuiteRun
from app.storage.listener_registry import ListenerRegistry
from app.storage.records import SuiteRecord


class InMemorySuiteRepository:
    """``SuiteRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``SqliteSuiteRepository`` 로 교체한다(동일 포트). SQLite 어댑터와 동일한
    값 의미(value semantics)를 위해 저장·조회를 영속 DTO ``SuiteRecord`` 매퍼로 정규화한다
    (도메인 객체를 공유 참조로 보관하지 않음 — 외부 변이가 저장본에 새지 않는다).
    """

    def __init__(self) -> None:
        self._suites: dict[str, SuiteRecord] = {}
        self._listeners: ListenerRegistry[SuiteEvent] = ListenerRegistry()
        self._lock = asyncio.Lock()

    async def create_suite(self, suite: SuiteRun) -> SuiteRun:
        async with self._lock:
            self._suites[suite.suite_id] = SuiteRecord.from_domain(suite)
        return suite

    async def save_suite(self, suite: SuiteRun) -> SuiteRun:
        async with self._lock:
            self._suites[suite.suite_id] = SuiteRecord.from_domain(suite)
        return suite

    async def get_suite(self, suite_id: str) -> SuiteRun:
        async with self._lock:
            return self._suites[suite_id].to_domain()

    async def list_suites(self) -> list[SuiteRun]:
        async with self._lock:
            return [record.to_domain() for record in self._suites.values()]

    async def list_suites_by_user(self, user_id: str) -> list[SuiteRun]:
        return [suite for suite in await self.list_suites() if suite.created_by_user_id == user_id]

    async def publish(self, event: SuiteEvent) -> None:
        await self._listeners.publish(event.suite_id, event)

    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]:
        return await self._listeners.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None:
        await self._listeners.unsubscribe(suite_id, queue)
