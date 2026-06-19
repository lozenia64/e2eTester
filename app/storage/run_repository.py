from __future__ import annotations

import asyncio

from app.core.models import DashboardEvent, Run
from app.storage.listener_registry import ListenerRegistry


class InMemoryRunRepository:
    """``RunRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``SqliteRunRepository`` 로 교체한다(동일 포트). 단위 테스트나 영속이
    필요 없는 실행에서는 이 구현을 쓴다.

    SQLite 어댑터와 **동일한 값 의미(value semantics)** 를 갖는다: 저장·조회 시 깊은 복사를
    하므로 저장된 상태와 호출자가 들고 있는 객체가 공유되지 않는다(공유 가변 집합체로 인한
    last-write-wins 위험 제거). 모듈 로그는 이 집합체에 속하지 않으므로 저장 시 비운다 —
    로그는 ``RunLogStorePort`` 가 따로 소유한다.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()
        self._lock = asyncio.Lock()

    @staticmethod
    def _persist_copy(run: Run) -> Run:
        stored = run.model_copy(deep=True)
        for module in stored.modules:
            module.logs = []
        return stored

    async def create_run(self, run: Run) -> Run:
        async with self._lock:
            self._runs[run.run_id] = self._persist_copy(run)
        return run

    async def save_run(self, run: Run) -> Run:
        async with self._lock:
            self._runs[run.run_id] = self._persist_copy(run)
        return run

    async def get_run(self, run_id: str) -> Run:
        async with self._lock:
            return self._runs[run_id].model_copy(deep=True)

    async def list_runs(self) -> list[Run]:
        async with self._lock:
            return [run.model_copy(deep=True) for run in self._runs.values()]

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return [run for run in await self.list_runs() if run.created_by_user_id == user_id]

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)
