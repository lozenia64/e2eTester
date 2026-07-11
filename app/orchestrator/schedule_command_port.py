from __future__ import annotations

from typing import Protocol

from app.core.models import Run
from app.orchestrator.run_command_port import RunCommandPort


class ScheduleCommandPort(RunCommandPort, Protocol):
    """스케줄러가 Run/Suite 트리거·조회에 의존하는 명령 포트.

    ``RunCommandPort`` 를 확장해 예약 관리 센터가 필요로 하는 Run 이력 조회·시스템 메타를
    노출한다. ``RunService`` 가 구조적으로 이 포트를 만족하며, 스케줄러는 구체 서비스가
    아닌 이 포트에만 의존한다.
    """

    def list_systems(self): ...

    async def list_runs_by_schedule(self, schedule_id: str, limit: int = 30) -> list[Run]: ...

    async def list_schedule_tagged_runs(self) -> list[Run]: ...

    async def last_finished_at_by_system(self) -> dict: ...
