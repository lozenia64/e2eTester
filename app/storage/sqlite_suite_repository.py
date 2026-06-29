from __future__ import annotations

import asyncio

from app.core.models import SuiteEvent, SuiteRun
from app.storage.listener_registry import ListenerRegistry
from app.storage.records import SuiteRecord
from app.storage.sqlite_support import JsonTableStore


class SqliteSuiteRepository:
    """SuiteRun 을 SQLite 에 영속하는 ``SuiteRepositoryPort`` 어댑터.

    Suite 본체는 ``suites`` 테이블에 JSON 으로 저장된다(도메인 엔티티를 직접 직렬화하지 않고
    영속 DTO ``SuiteRecord`` 매퍼를 거친다 — Run 쪽과 동일한 영속/도메인 분리 seam). WebSocket
    리스너 큐는 프로세스-로컬(휘발성)이라 영속화하지 않는다.
    """

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "suites")
        self._listeners: ListenerRegistry[SuiteEvent] = ListenerRegistry()

    async def create_suite(self, suite: SuiteRun) -> SuiteRun:
        await self._store.upsert(suite.suite_id, SuiteRecord.serialize(suite))
        return suite

    async def save_suite(self, suite: SuiteRun) -> SuiteRun:
        await self._store.upsert(suite.suite_id, SuiteRecord.serialize(suite))
        return suite

    async def get_suite(self, suite_id: str) -> SuiteRun:
        data = await self._store.get(suite_id)
        if data is None:
            raise KeyError(suite_id)
        return SuiteRecord.deserialize(data)

    async def list_suites(self) -> list[SuiteRun]:
        return [SuiteRecord.deserialize(data) for data in await self._store.list_all()]

    async def list_suites_by_user(self, user_id: str) -> list[SuiteRun]:
        return [suite for suite in await self.list_suites() if suite.created_by_user_id == user_id]

    async def publish(self, event: SuiteEvent) -> None:
        await self._listeners.publish(event.suite_id, event)

    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]:
        return await self._listeners.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None:
        await self._listeners.unsubscribe(suite_id, queue)
