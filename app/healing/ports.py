"""자가 치유 기록 포트 — 오케스트레이터(RunService)가 의존하는 최소 계약.

``RunCommandPort`` 와 같은 의존 역전 패턴: ``RunService`` 는 구체 ``HealingService`` 가
아니라 이 Protocol 에만 의존하고, ``HealingService`` 가 구조적으로 만족한다(배선은
컴포지션 루트가 독점).
"""

from __future__ import annotations

from typing import Protocol

from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition
from app.healing.models import HealingAttempt


class HealingRecorderPort(Protocol):
    async def record_step_healing(
        self,
        run: Run,
        module: RunModule,
        definition: ModuleDefinition,
        attempts: list[HealingAttempt],
    ) -> None: ...
