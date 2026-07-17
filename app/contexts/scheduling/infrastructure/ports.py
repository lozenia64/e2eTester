"""Scheduling BC storage ports."""

from __future__ import annotations

from typing import Protocol

from app.core.schedule_models import Schedule


class ScheduleRepositoryPort(Protocol):
    async def save(self, schedule: Schedule) -> Schedule: ...
    async def get(self, schedule_id: str) -> Schedule: ...
    async def list(self) -> list[Schedule]: ...
    async def delete(self, schedule_id: str) -> None: ...
