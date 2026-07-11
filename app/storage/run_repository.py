from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.enums import RunStatus
from app.core.models import DashboardEvent, Run
from app.core.status_labels import RUN_TERMINAL_OUTCOME_STATUSES
from app.domain.events import DomainEvent
from app.storage.listener_registry import ListenerRegistry
from app.storage.records import RunRecord


class InMemoryRunRepository:
    """``RunRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``CompositeRunRepository`` + SQLite 어댑터로 교체한다(동일 포트).
    단위 테스트나 영속이 필요 없는 실행에서는 이 구현을 쓴다.
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

    async def get_run(self, run_id: str) -> Run:
        async with self._lock:
            return self._runs[run_id].to_domain()

    async def list_all_runs(self) -> list[Run]:
        async with self._lock:
            runs = [record.to_domain() for record in self._runs.values()]
        runs.sort(key=lambda run: run.requested_at, reverse=True)
        return runs

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return [run for run in await self.list_all_runs() if run.created_by_user_id == user_id]

    async def list_runs_by_system(self, system_code: str) -> list[Run]:
        return [run for run in await self.list_all_runs() if run.system_code == system_code]

    async def list_runs_by_schedule(self, schedule_id: str, limit: int = 30) -> list[Run]:
        runs = [run for run in await self.list_all_runs() if run.schedule_id == schedule_id]
        return runs[:limit]

    async def list_schedule_tagged_runs(self) -> list[Run]:
        return [run for run in await self.list_all_runs() if run.schedule_id]

    async def list_runs_since(self, since: datetime) -> list[Run]:
        since_utc = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
        return [
            run
            for run in await self.list_all_runs()
            if (
                run.requested_at
                if run.requested_at.tzinfo
                else run.requested_at.replace(tzinfo=UTC)
            )
            >= since_utc
        ]

    async def list_runs_with_statuses(self, statuses: frozenset) -> list[Run]:
        return [run for run in await self.list_all_runs() if run.status in statuses]

    async def list_waiting_input_runs(self) -> list[Run]:
        return await self.list_runs_with_statuses(frozenset({RunStatus.WAITING_INPUT}))

    async def last_finished_at_by_system(self) -> dict[str, datetime]:
        latest: dict[str, datetime] = {}
        for run in await self.list_all_runs():
            if run.status not in RUN_TERMINAL_OUTCOME_STATUSES or run.status == RunStatus.CANCELLED:
                continue
            moment = run.ended_at or run.requested_at
            moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
            current = latest.get(run.system_code)
            if current is None or moment > current:
                latest[run.system_code] = moment
        return latest

    async def find_previous_finished_run(self, run: Run) -> Run | None:
        baseline: Run | None = None
        for other in await self.list_all_runs():
            if other.run_id == run.run_id or other.system_code != run.system_code:
                continue
            if other.status not in RUN_TERMINAL_OUTCOME_STATUSES:
                continue
            if other.requested_at >= run.requested_at:
                continue
            if baseline is None or other.requested_at > baseline.requested_at:
                baseline = other
        return baseline

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
