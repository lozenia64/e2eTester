from __future__ import annotations

from app.core.schedule_models import Schedule
from app.platform.db import JsonTableStore


class SqliteScheduleRepository:
    """예약(Schedule)을 SQLite 에 영속하는 ``ScheduleRepositoryPort`` 어댑터.

    재기동 후에도 cron 예약과 마지막 실행 메타데이터가 남는다. 단, 서버 다운 동안 지나간
    예약이 시작 직후 한꺼번에 실행되지 않도록 ``SchedulerService`` 가 기동 시 과거로 밀린
    ``next_run_at`` 을 다음 cron 시각으로 재계산한다.
    """

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "schedules")

    async def save(self, schedule: Schedule) -> Schedule:
        await self._store.upsert(schedule.schedule_id, schedule.model_dump_json())
        return schedule

    async def get(self, schedule_id: str) -> Schedule:
        data = await self._store.get(schedule_id)
        if data is None:
            raise KeyError(schedule_id)
        return Schedule.model_validate_json(data)

    async def list(self) -> list[Schedule]:
        return [Schedule.model_validate_json(data) for data in await self._store.list_all()]

    async def delete(self, schedule_id: str) -> None:
        await self._store.delete(schedule_id)
