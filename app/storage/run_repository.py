from __future__ import annotations

import asyncio

from app.core.models import DashboardEvent, Run
from app.storage.listener_registry import ListenerRegistry
from app.storage.records import RunRecord


class InMemoryRunRepository:
    """``RunRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``SqliteRunRepository`` 로 교체한다(동일 포트). 단위 테스트나 영속이
    필요 없는 실행에서는 이 구현을 쓴다.

    SQLite 어댑터와 **동일한 값 의미(value semantics)** 를 갖는다: 저장·조회를 모두 영속 DTO
    ``RunRecord`` 매퍼로 정규화하므로(``from_domain`` → 보관, 조회 시 ``to_domain``) 저장된
    상태와 호출자가 들고 있는 객체가 공유되지 않는다(공유 가변 집합체로 인한 last-write-wins
    위험 제거). 모듈 로그는 ``RunRecord`` 스키마에 없으므로 보관 시 자연히 떨어진다 — 로그는
    ``RunLogStorePort`` 가 따로 소유한다(SQLite 어댑터와 동일 규칙·동일 매퍼).
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()
        self._lock = asyncio.Lock()

    async def create_run(self, run: Run) -> Run:
        async with self._lock:
            self._runs[run.run_id] = RunRecord.from_domain(run)
        return run

    async def save_run(self, run: Run) -> Run:
        async with self._lock:
            self._runs[run.run_id] = RunRecord.from_domain(run)
        return run

    async def get_run(self, run_id: str) -> Run:
        async with self._lock:
            return self._runs[run_id].to_domain()

    async def list_runs(self) -> list[Run]:
        async with self._lock:
            return [record.to_domain() for record in self._runs.values()]

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return [run for run in await self.list_runs() if run.created_by_user_id == user_id]

    async def delete_run(self, run_id: str) -> None:
        async with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            del self._runs[run_id]

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)
