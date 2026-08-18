"""tier 2(로그인 재주행) 예산이 **Run 단위**로 누적되는지 종단 검증(설계 §3.6 / R6).

``RunStateMachine.decide_post_step_failure`` 자체의 예산 판정은
``tests/test_run_state_machine.py`` 가 순수 함수로 검증한다. 이 파일은 그 판정의 입력인
``tier2_used`` 를 **누가 세는가**를 검증한다 — 모듈 루프 안에서 세면 모듈마다 0으로
리셋되어 예산이 사실상 무한해지고, R6 의 비용 가드가 무력해진다(설정·문서는 전부 "Run 당"
이라고 설명한다).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.contexts.run.application.service import RunService
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.in_memory_run_input_store import InMemoryRunInputStore
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
from app.contexts.run.infrastructure.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_control_store import SqliteRunControlStore
from app.core.enums import FailureSignal, ModuleStatus, RecoveryTier, RunStatus
from app.core.run_models import Run, RunModule
from app.core.settings import E2ESettings
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.execution.results import StepExecutionResult
from app.execution.run_queue import RunExecutionQueue
from app.platform.eventing.bus import EventBus
from app.realtime.adapter import RealtimeNotificationAdapter


class _FakeRegistry:
    def __init__(self, system: SystemDefinition) -> None:
        self._system = system

    def get_system(self, system_code: str) -> SystemDefinition:
        return self._system

    def get_execution_profile(self, system_code: str) -> str:
        return self._system.execution_profile


class _SessionLostGateway(ExecutionGateway):
    """모든 단계가 ``SESSION_LOST`` 신호와 함께 ERROR 로 끝나는 어댑터(되감기 등급 관찰용)."""

    def __init__(self) -> None:
        self.recovery_tiers: list[RecoveryTier] = []

    def supports(self, execution_mode: str) -> bool:
        return True

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
        storage_state: str | None = None,
    ) -> ExecutionHandle:
        return ExecutionHandle(execution_mode=execution_mode, session_id=uuid4().hex)

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        return StepExecutionResult(
            status=ModuleStatus.ERROR,
            message="세션이 끊겼습니다",
            artifacts=[],
            # tier 1 폴백(진입 URL 미확보 시 되감기 생략)에 걸리지 않도록 URL 을 준다.
            current_url=f"https://example.test/{module.module_id}",
            dialog_messages=[],
            failure_signal=FailureSignal.SESSION_LOST,
        )

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        return None

    async def close_session(self, handle: ExecutionHandle) -> None:
        return None

    async def resume_from_step(
        self, handle: ExecutionHandle, module_index: int, workflow_step: str
    ) -> None:
        return None

    async def recover_session(
        self, handle: ExecutionHandle, tier: RecoveryTier, entry_url: str | None
    ) -> bool:
        self.recovery_tiers.append(tier)
        return True


def _definition(module_id: str, order: int) -> ModuleDefinition:
    return ModuleDefinition(
        module_id=module_id,
        system_code="sim",
        name=module_id,
        description="",
        group="test",
        order=order,
        execution_mode="simulated",
        simulated_duration_ms=1,
        max_retries=2,
        retry_backoff_ms=0,
    )


async def _run_two_failing_modules(tmp_path) -> _SessionLostGateway:
    system = SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[_definition("mod.a", 10), _definition("mod.b", 20)],
        execution_profile="light",
    )
    run = Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[
            # mod.a 는 tier 2 를 두 번 소진할 수 있게 3회 시도, mod.b 는 1회만 재시도한다.
            RunModule(
                module_id="mod.a",
                name="mod.a",
                group="test",
                order=10,
                status=ModuleStatus.PENDING,
                max_attempts=3,
            ),
            RunModule(
                module_id="mod.b",
                name="mod.b",
                group="test",
                order=20,
                status=ModuleStatus.PENDING,
                max_attempts=2,
            ),
        ],
        selected_module_ids=["mod.a", "mod.b"],
        triggered_by="manual",
    )
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run, events=RunAggregate.for_new_run(run).pull_events())
    input_store = InMemoryRunInputStore()
    await input_store.put(run.run_id, {})

    gateway = _SessionLostGateway()
    service = RunService(
        registry=_FakeRegistry(system),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=gateway,
        event_bus=EventBus(),
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=input_store,
        run_queue=RunExecutionQueue(worker_count=1),
        settings=E2ESettings(_env_file=None),  # recovery_tier2_budget 기본값 2
    )

    await service._execute_run(run.run_id, {}, start_index=0, handle=None)
    return gateway


@pytest.mark.asyncio
@pytest.mark.spec("SPEC-RUN-006", "AC-007")
async def test_tier_two_budget_is_shared_across_modules_in_one_run(tmp_path):
    """모듈 A 가 예산(2)을 다 쓰면, 다음 모듈 B 의 첫 tier 2 시도는 강등돼야 한다.

    예산 카운터가 모듈 루프 안에 있으면 B 에서 0으로 리셋되어 tier 2 가 또 허용된다
    (되감기 등급이 ``[2, 2, 2]``). Run 단위로 세면 B 는 tier 1 로 강등된다(``[2, 2, 1]``).
    """
    gateway = await _run_two_failing_modules(tmp_path)

    assert gateway.recovery_tiers == [
        RecoveryTier.REPLAY_FROM_LOGIN,  # mod.a 재시도 1 — 예산 0/2 사용
        RecoveryTier.REPLAY_FROM_LOGIN,  # mod.a 재시도 2 — 예산 1/2 사용
        RecoveryTier.RESET_TO_MODULE_ENTRY,  # mod.b 재시도 1 — Run 예산 소진 → 강등
    ]
