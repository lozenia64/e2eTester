from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.models import DashboardEvent, Run
from app.storage.listener_registry import ListenerRegistry


class InMemoryRunRepository:
    """``RunRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``SqliteRunRepository`` 로 교체한다(동일 포트). 단위 테스트나 영속이
    필요 없는 실행에서는 이 구현을 쓴다.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()
        self._logs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()

    async def create_run(self, run: Run) -> Run:
        async with self._lock:
            self._runs[run.run_id] = run
        return run

    async def save_run(self, run: Run) -> Run:
        async with self._lock:
            self._runs[run.run_id] = run
        return run

    async def append_module_log(self, run_id: str, module_id: str, line: str) -> None:
        async with self._lock:
            self._logs[run_id][module_id].append(line)

    async def get_module_logs(self, run_id: str, module_id: str) -> list[str]:
        async with self._lock:
            return list(self._logs[run_id][module_id])

    async def get_run(self, run_id: str) -> Run:
        async with self._lock:
            return self._runs[run_id]

    async def list_runs(self) -> list[Run]:
        async with self._lock:
            return list(self._runs.values())

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return [run for run in await self.list_runs() if run.created_by_user_id == user_id]

    async def publish(self, event: DashboardEvent) -> None:
        await self._listeners.publish(event.run_id, event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        return await self._listeners.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        await self._listeners.unsubscribe(run_id, queue)
