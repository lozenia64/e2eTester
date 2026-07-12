from __future__ import annotations

from typing import Protocol

from app.orchestrator.run_command_port import RunCommandPort
from app.storage.query_rows import RunSummaryRow


class ScheduleCommandPort(RunCommandPort, Protocol):
    """스케줄러가 Run/Suite 트리거에 의존하는 **명령** 포트.

    ``RunCommandPort`` 를 확장해 시스템 메타 조회를 노출한다. ``RunService`` 가 구조적으로
    이 포트를 만족하며, 스케줄러는 구체 서비스가 아닌 이 포트에만 의존한다.
    """

    def list_systems(self): ...


class ScheduleRunQueryPort(Protocol):
    """예약 관리 센터가 의존하는 Run 이력 **질의** 포트(프로젝션 행 기반).

    ``RunQueries`` 가 구조적으로 만족한다 — 스케줄러는 blob(``Run`` 엔티티)을 받지 않는다.
    """

    async def list_schedule_runs(
        self, schedule_id: str, limit: int = 30
    ) -> list[RunSummaryRow]: ...

    async def list_schedule_tagged_runs(self) -> list[RunSummaryRow]: ...

    async def last_finished_at_by_system(self) -> dict: ...
