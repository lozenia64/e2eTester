from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.models import DashboardEvent, Run
from app.storage.listener_registry import ListenerRegistry
from app.storage.sqlite_support import JsonTableStore


class SqliteRunRepository:
    """Run 을 SQLite 에 영속하는 ``RunRepositoryPort`` 어댑터.

    - Run 본체는 ``runs`` 테이블에 JSON 으로 저장돼 재기동 후에도 이력/상태가 남는다.
    - 모듈 로그의 라인 단위 버퍼(``append_module_log``)는 실행 중에만 쓰는 휘발성 작업
      상태라 인메모리로 둔다. 모듈 종료 시 ``RunService`` 가 이 버퍼를 ``module.logs`` 로
      복사해 Run 과 함께 저장하므로, 완료된 Run 의 로그는 Run JSON 안에 영속된다.
    - WebSocket 리스너 큐도 프로세스-로컬(휘발성)이다.
    """

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "runs")
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()
        self._logs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._log_lock = asyncio.Lock()

    async def create_run(self, run: Run) -> Run:
        await self._store.upsert(run.run_id, run.model_dump_json())
        return run

    async def save_run(self, run: Run) -> Run:
        await self._store.upsert(run.run_id, run.model_dump_json())
        return run

    async def append_module_log(self, run_id: str, module_id: str, line: str) -> None:
        async with self._log_lock:
            self._logs[run_id][module_id].append(line)

    async def get_module_logs(self, run_id: str, module_id: str) -> list[str]:
        async with self._log_lock:
            return list(self._logs[run_id][module_id])

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
