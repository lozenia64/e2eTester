from __future__ import annotations

import asyncio

from app.core.models import Schedule


class InMemoryScheduleRepository:
    """메모리 기반 예약(Schedule) 저장소.

    RunRepository 와 마찬가지로 서버 재시작 시 사라진다. 영구 저장소가 도입되면
    동일 인터페이스로 교체할 수 있도록 분리해 두었다.
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
