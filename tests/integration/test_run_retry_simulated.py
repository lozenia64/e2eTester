"""Run 재시도·부분 재실행 통합 테스트(시뮬레이션 게이트웨이)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import ModuleDefinition, Run, RunModule, SystemDefinition
from app.domain.run_aggregate import RunAggregate
from app.events.bus import EventBus
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.run_queue import RunExecutionQueue
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.orchestrator.run_service import RunService
from app.realtime.adapter import RealtimeNotificationAdapter
from app.storage.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.storage.run_input_store import InMemoryRunInputStore
from app.storage.run_log_store import InMemoryRunLogStore
from app.storage.run_repository import InMemoryRunRepository
from app.storage.sqlite_run_control_store import SqliteRunControlStore


class _FakeRegistry:
    def __init__(self, system: SystemDefinition) -> None:
        self._system = system

    def get_system(self, system_code: str) -> SystemDefinition:
        return self._system

    def get_execution_profile(self, system_code: str) -> str:
        return self._system.execution_profile


def _retry_module() -> ModuleDefinition:
    return ModuleDefinition(
        module_id="sim.retry",
        system_code="sim",
        name="Retry test",
        description="",
        group="test",
        order=10,
        execution_mode="simulated",
        simulated_duration_ms=1,
        simulated_outcome="ERROR",
        max_retries=1,
        retry_backoff_ms=10,
        retryable_on=["ERROR"],
    )


@pytest.mark.asyncio
async def test_simulated_gateway_retry_succeeds_on_second_attempt(tmp_path):
    system = SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[_retry_module()],
        execution_profile="light",
    )
    module = RunModule(
        module_id="sim.retry",
        name="Retry test",
        group="test",
        order=10,
        status=ModuleStatus.PENDING,
        max_attempts=2,
    )
    run = Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[module],
        selected_module_ids=["sim.retry"],
    )
    db_path = str(tmp_path / "control.db")
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
        control_store=SqliteRunControlStore(db_path),
        input_store=input_store,
        run_queue=queue,
    )
    queue.set_run_job_handler(service.dispatch_run_job)
    queue.start()

    await service._execute_run(run.run_id, {"browser_mode": "headless"}, start_index=0, handle=None)
    await queue.join()

    finished = await write_repo.get_run(run.run_id)
    assert finished.modules[0].status == ModuleStatus.PASSED
    assert finished.modules[0].attempt == 2
    assert finished.status == RunStatus.PASSED
