"""Run 저장소 복합 어댑터 — 쓰기·이력 조회·실시간 알림을 한 ``RunRepositoryPort`` 로 노출."""

from __future__ import annotations

from app.core.models import DashboardEvent, Run
from app.domain.events import DomainEvent
from app.realtime.ports import RealtimeNotificationPort
from app.storage.ports import RunHistoryQueryPort, RunWriteRepositoryPort


class CompositeRunRepository:
    """하위 호환용 ``RunRepositoryPort`` 합성 구현."""

    def __init__(
        self,
        write_repo: RunWriteRepositoryPort,
        history_query: RunHistoryQueryPort,
        realtime: RealtimeNotificationPort,
    ) -> None:
        self._write_repo = write_repo
        self._history_query = history_query
        self._realtime = realtime

    async def create_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run:
        return await self._write_repo.create_run(run, events=events)

    async def save_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run:
        return await self._write_repo.save_run(run, events=events)

    async def get_run(self, run_id: str) -> Run:
        return await self._write_repo.get_run(run_id)

    async def delete_run(self, run_id: str) -> None:
        await self._write_repo.delete_run(run_id)

    async def list_all_runs(self) -> list[Run]:
        return await self._history_query.list_all_runs()

    async def list_runs_by_user(self, user_id: str) -> list[Run]:
        return await self._history_query.list_runs_by_user(user_id)

    async def list_runs_by_system(self, system_code: str) -> list[Run]:
        return await self._history_query.list_runs_by_system(system_code)

    async def list_runs_by_schedule(self, schedule_id: str, limit: int = 30) -> list[Run]:
        return await self._history_query.list_runs_by_schedule(schedule_id, limit=limit)

    async def list_schedule_tagged_runs(self) -> list[Run]:
        return await self._history_query.list_schedule_tagged_runs()

    async def list_runs_since(self, since):
        return await self._history_query.list_runs_since(since)

    async def list_runs_with_statuses(self, statuses):
        return await self._history_query.list_runs_with_statuses(statuses)

    async def list_waiting_input_runs(self) -> list[Run]:
        return await self._history_query.list_waiting_input_runs()

    async def last_finished_at_by_system(self):
        return await self._history_query.last_finished_at_by_system()

    async def find_previous_finished_run(self, run: Run):
        return await self._history_query.find_previous_finished_run(run)

    async def publish(self, event: DashboardEvent) -> None:
        await self._realtime.publish(event)

    async def subscribe(self, run_id: str):
        return await self._realtime.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue) -> None:
        await self._realtime.unsubscribe(run_id, queue)
