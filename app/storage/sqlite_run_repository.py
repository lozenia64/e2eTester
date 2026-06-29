from __future__ import annotations

import asyncio

from app.core.models import DashboardEvent, Run
from app.storage.listener_registry import ListenerRegistry
from app.storage.records import RunRecord
from app.storage.sqlite_support import JsonTableStore


class SqliteRunRepository:
    """Run **상태** 를 SQLite 에 영속하는 ``RunRepositoryPort`` 어댑터.

    - Run 본체(status·모듈 전이·comparison 등)는 ``runs`` 테이블에 JSON 으로 저장돼 재기동
      후에도 이력/상태가 남는다. **모듈 로그는 여기 담기지 않는다** — 영속 스키마
      ``RunRecord`` 에 ``logs`` 필드가 아예 없어(타입 수준) blob 에 들어갈 수 없다. 로그는
      ``RunLogStorePort`` 어댑터가 append-only 로 따로 영속한다.
    - 이 어댑터는 도메인 ``Run`` 을 직접 직렬화하지 않고 ``RunRecord`` 매퍼만 거친다
      (영속 스키마 ↔ 도메인 엔티티 분리). 쓰기는 상태 전이 시점에만 일어난다(핫패스 제거).
    - WebSocket 리스너 큐는 프로세스-로컬(휘발성)이다.
    """

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "runs")
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()

    async def create_run(self, run: Run) -> Run:
        await self._store.upsert(run.run_id, RunRecord.serialize(run))
        return run

    async def save_run(self, run: Run) -> Run:
        await self._store.upsert(run.run_id, RunRecord.serialize(run))
        return run

    async def get_run(self, run_id: str) -> Run:
        data = await self._store.get(run_id)
        if data is None:
            raise KeyError(run_id)
        return RunRecord.deserialize(data)

    async def list_runs(self) -> list[Run]:
        return [RunRecord.deserialize(data) for data in await self._store.list_all()]

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return [run for run in await self.list_runs() if run.created_by_user_id == user_id]

    async def delete_run(self, run_id: str) -> None:
        await self._store.delete(run_id)

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)
