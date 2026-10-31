"""Run 수준 자동 재실행 게이트의 실제 배선(RunService._finalize_run 훅) 통합 테스트.

``tests/test_auto_rerun_gate.py`` 는 ``RunStateMachine.decide_auto_rerun`` 의 순수 결정만
검증한다. 이 파일은 그 결정이 ``RunService._finalize_run`` → ``_enqueue_auto_rerun`` →
``rerun_from_module`` 로 실제로 이어지는지, 그리고 ``auto_rerun_enabled`` 기본값(False)에서는
기존 동작이 그대로인지를 시뮬레이션 게이트웨이로 종단 검증한다.
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
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.settings import E2ESettings
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.run_queue import RunExecutionQueue
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.platform.eventing.bus import EventBus
from app.realtime.adapter import RealtimeNotificationAdapter


class _FakeRegistry:
    def __init__(self, system: SystemDefinition) -> None:
        self._system = system

    def get_system(self, system_code: str) -> SystemDefinition:
        return self._system

    def get_execution_profile(self, system_code: str) -> str:
        return self._system.execution_profile


def _always_fails_module() -> ModuleDefinition:
    # SimulatedExecutionGateway 는 "ERROR" 결과를 module.max_retries 번까지만 흉내 내고 그
    # 이후 attempt 에서는 PASSED 로 뒤집는다(일시 오류 시뮬레이션용). 여기서는 RunModule 쪽
    # max_attempts=1 로 실제 재시도를 막아, 첫 attempt 의 ERROR 가 그대로 최종 결과가 되게
    # max_retries 를 넉넉히 크게 잡는다(회귀 방지: 절대 PASSED 로 뒤집히지 않아야 하는 케이스).
    return ModuleDefinition(
        module_id="sim.fail",
        system_code="sim",
        name="Always fails",
        description="",
        group="test",
        order=10,
        execution_mode="simulated",
        simulated_duration_ms=1,
        simulated_outcome="ERROR",
        max_retries=5,
    )


async def _run_to_completion(
    *, triggered_by: str, settings: E2ESettings | None, tmp_path
) -> tuple[Run, InMemoryRunRepository]:
    system = SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[_always_fails_module()],
        execution_profile="light",
    )
    module = RunModule(
        module_id="sim.fail",
        name="Always fails",
        group="test",
        order=10,
        status=ModuleStatus.PENDING,
        max_attempts=1,
    )
    run = Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[module],
        selected_module_ids=["sim.fail"],
        triggered_by=triggered_by,
    )
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run, events=RunAggregate.for_new_run(run).pull_events())
    input_store = InMemoryRunInputStore()
    await input_store.put(run.run_id, {})

    queue = RunExecutionQueue(worker_count=1, backend=InMemoryJobQueue())
    service = RunService(
        registry=_FakeRegistry(system),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([SimulatedExecutionGateway()]),
        event_bus=EventBus(),
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=input_store,
        run_queue=queue,
        settings=settings,
    )
    queue.set_run_job_handler(service.dispatch_run_job)
    queue.start()

    await service._execute_run(run.run_id, {"browser_mode": "headless"}, start_index=0, handle=None)
    await queue.join()
    await queue.stop()

    finished = await write_repo.get_run(run.run_id)
    return finished, write_repo


@pytest.mark.asyncio
@pytest.mark.spec("SPEC-RUN-006", "AC-006")
async def test_scheduled_error_run_auto_reruns_in_place_when_enabled(tmp_path):
    """auto_rerun_enabled=True 인 예약 Run 이 ERROR 로 끝나면 실패 모듈부터 1회 자동
    재실행되고, 재실행도 실패하면 auto_rerun_of 가 남아 더 이상 연쇄되지 않는다."""
    settings = E2ESettings(_env_file=None, E2E_AUTO_RERUN_ENABLED="true")

    finished, _ = await _run_to_completion(
        triggered_by="schedule", settings=settings, tmp_path=tmp_path
    )

    assert finished.status == RunStatus.ERROR
    assert finished.modules[0].status == ModuleStatus.ERROR
    # 부분 재실행은 새 Run 을 만들지 않고 같은 Run 을 되감아 재실행한다(설계상 in-place).
    # auto_rerun_of 는 자기 자신의 id 를 가리키며, 이 값이 남아 있다는 것 자체가
    # "이미 한 번 자동 재실행됐다"는 표식이자 재연쇄 차단 근거다.
    assert finished.auto_rerun_of == finished.run_id
    # 재시도 attempt 카운터도 부분 재실행으로 1로 리셋된 뒤 다시 소진되어 있어야 한다.
    assert finished.modules[0].attempt == 1
    # R4 — 재실행이 실제로 다시 돌아 끝났으면 대기 플래그는 내려가 있어야 한다. 내려가지
    # 않으면 이 두 번째(진짜 최종) ERROR 의 완료/운영자 알림이 영원히 억제된다.
    assert finished.auto_rerun_pending is False


@pytest.mark.asyncio
async def test_manual_error_run_never_auto_reruns_even_when_enabled(tmp_path):
    """사람이 수동으로 실행한 Run 은 auto_rerun_enabled=True 라도 절대 자동 재실행되지 않는다."""
    settings = E2ESettings(_env_file=None, E2E_AUTO_RERUN_ENABLED="true")

    finished, _ = await _run_to_completion(
        triggered_by="manual", settings=settings, tmp_path=tmp_path
    )

    assert finished.status == RunStatus.ERROR
    assert finished.auto_rerun_of is None


@pytest.mark.asyncio
async def test_scheduled_error_run_does_not_auto_rerun_by_default(tmp_path):
    """환경 파일 미지정(기본값 auto_rerun_enabled=False)이면 예약 ERROR Run 도 그대로 끝난다."""
    settings = E2ESettings(_env_file=None)

    finished, _ = await _run_to_completion(
        triggered_by="schedule", settings=settings, tmp_path=tmp_path
    )

    assert finished.status == RunStatus.ERROR
    assert finished.auto_rerun_of is None
