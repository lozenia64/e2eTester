from __future__ import annotations

import asyncio

from app.core.models import DashboardEvent, Run
from app.storage.listener_registry import ListenerRegistry
from app.storage.sqlite_support import JsonTableStore

# 영속 Run blob 에서 제외할 필드. 모듈 로그는 별도 집합체(``RunLogStorePort``)가 소유하므로
# Run 상태 blob 에는 절대 담지 않는다. 누가 (하이드레이션된) Run 을 save_run 으로 넘겨도
# 이 strip 덕에 blob 이 로그로 비대해지지 않는다.
_PERSIST_EXCLUDE = {"modules": {"__all__": {"logs"}}}


class SqliteRunRepository:
    """Run **상태** 를 SQLite 에 영속하는 ``RunRepositoryPort`` 어댑터.

    - Run 본체(status·모듈 전이·comparison 등)는 ``runs`` 테이블에 JSON 으로 저장돼 재기동
      후에도 이력/상태가 남는다. **모듈 로그는 여기 담기지 않는다** (``_PERSIST_EXCLUDE``).
      로그는 ``RunLogStorePort`` 어댑터가 append-only 로 따로 영속한다.
    - 따라서 이 어댑터의 쓰기는 더 이상 "로그 한 줄마다 Run 전체 재직렬화" 가 아니라
      상태 전이 시점에만 일어난다(핫패스 full-blob 쓰기 제거).
    - WebSocket 리스너 큐는 프로세스-로컬(휘발성)이다.
    """

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "runs")
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()

    async def create_run(self, run: Run) -> Run:
        await self._store.upsert(run.run_id, self._serialize(run))
        return run

    async def save_run(self, run: Run) -> Run:
        await self._store.upsert(run.run_id, self._serialize(run))
        return run

    @staticmethod
    def _serialize(run: Run) -> str:
        return run.model_dump_json(exclude=_PERSIST_EXCLUDE)

    async def get_run(self, run_id: str) -> Run:
        data = await self._store.get(run_id)
        if data is None:
            raise KeyError(run_id)
        return Run.model_validate_json(data)

    async def list_runs(self) -> list[Run]:
        return [Run.model_validate_json(data) for data in await self._store.list_all()]

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return [run for run in await self.list_runs() if run.created_by_user_id == user_id]

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)
