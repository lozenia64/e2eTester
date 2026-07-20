from __future__ import annotations

import asyncio

from app.contexts.run.contracts.records import RunRecord
from app.core.run_models import DashboardEvent, Run
from app.domain.events import DomainEvent
from app.realtime.listener_registry import ListenerRegistry


class InMemoryRunRepository:
    """``RunWriteRepositoryPort`` + 실시간 알림의 인메모리 어댑터(테스트 전용, 휘발).

    이력/목록 질의는 이 저장소가 아니라 ``InMemoryRunSummaryQuery``
    (``app/storage/in_memory_run_summary_query.py``)가 담당한다 — 프로덕션의
    쓰기 저장소 ↔ 프로젝션 질의 분리(CQRS)를 테스트 어댑터도 동일하게 따른다.
    ``list_all_runs`` 는 그 질의 어댑터의 행 도출용 데이터 소스로만 남겨 둔다.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._listeners: ListenerRegistry[DashboardEvent] = ListenerRegistry()
        self._lock = asyncio.Lock()

    async def create_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run:
        del events
        async with self._lock:
            self._runs[run.run_id] = RunRecord.from_domain(run)
        return run

    async def save_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run:
        del events
        async with self._lock:
            self._runs[run.run_id] = RunRecord.from_domain(run)
        return run

    async def append_events(self, events: list[DomainEvent]) -> None:
        del events  # 인메모리 어댑터는 이벤트 스토어/아웃박스를 갖지 않는다(테스트 전용).

    async def get_run(self, run_id: str) -> Run:
        async with self._lock:
            return self._runs[run_id].to_domain()

    async def list_all_runs(self) -> list[Run]:
        async with self._lock:
            runs = [record.to_domain() for record in self._runs.values()]
        runs.sort(key=lambda run: run.requested_at, reverse=True)
        return runs

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
