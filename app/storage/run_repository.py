from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.models import DashboardEvent, Run


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._listeners: dict[str, list[asyncio.Queue[DashboardEvent]]] = defaultdict(list)
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

    async def publish(self, event: DashboardEvent) -> None:
        listeners = list(self._listeners.get(event.run_id, []))
        for queue in listeners:
            await queue.put(event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]:
        queue: asyncio.Queue[DashboardEvent] = asyncio.Queue()
        self._listeners[run_id].append(queue)
        return queue

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None:
        listeners = self._listeners.get(run_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and run_id in self._listeners:
            del self._listeners[run_id]
