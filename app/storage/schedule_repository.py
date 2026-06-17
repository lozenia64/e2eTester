from __future__ import annotations

import asyncio

from app.core.models import Schedule


class InMemoryScheduleRepository:
    """``ScheduleRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    영속이 필요하면 ``SqliteScheduleRepository`` 로 교체한다(동일 포트).
    """

    def __init__(self) -> None:
        self._schedules: dict[str, Schedule] = {}
        self._lock = asyncio.Lock()

    async def save(self, schedule: Schedule) -> Schedule:
        async with self._lock:
            self._schedules[schedule.schedule_id] = schedule
        return schedule

    async def get(self, schedule_id: str) -> Schedule:
        async with self._lock:
            return self._schedules[schedule_id]

    async def list(self) -> list[Schedule]:
        async with self._lock:
            return list(self._schedules.values())

    async def delete(self, schedule_id: str) -> None:
        async with self._lock:
            self._schedules.pop(schedule_id, None)
