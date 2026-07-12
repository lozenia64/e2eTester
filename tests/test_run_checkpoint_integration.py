"""Phase C: RunService 가 세션 체크포인트를 저장하는 배선 검증(SIM, 브라우저 없음).

``_save_checkpoint`` 는 게이트웨이의 ``capture_storage_state`` 로 세션 상태를 캡처해
체크포인트 스토어에 저장한다. 스토어 미주입/게이트웨이 미지원이면 no-op(기존 흐름 무변경).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.domain.run_aggregate import RunAggregate
from app.events.bus import EventBus
from app.execution.gateway import ExecutionHandle
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.run_queue import RunExecutionQueue
from app.execution.session_checkpoint import InMemorySessionCheckpointStore
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.orchestrator.run_service import RunService
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


class _RealtimeSink:
    async def publish(self, event) -> None:
        return None


async def _make_service(tmp_path, checkpoint_store):
    system = SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[
            ModuleDefinition(
                module_id="sim.mod",
                system_code="sim",
                name="Mod",
                description="",
                group="test",
                order=10,
                execution_mode="simulated",
                simulated_duration_ms=1,
                simulated_outcome="PASSED",
            )
        ],
        execution_profile="light",
    )
    run = Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.RUNNING,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="sim.mod", name="Mod", group="test", order=10, status=ModuleStatus.RUNNING
            )
        ],
        selected_module_ids=["sim.mod"],
    )
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run, events=RunAggregate.for_new_run(run).pull_events())
    queue = RunExecutionQueue(worker_count=1, backend=InMemoryJobQueue())
    service = RunService(
        registry=_FakeRegistry(system),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=_RealtimeSink(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=SimulatedExecutionGateway(),
        event_bus=EventBus(),
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=InMemoryRunInputStore(),
        run_queue=queue,
        session_checkpoint_store=checkpoint_store,
    )
    return service, run


@pytest.mark.asyncio
async def test_save_checkpoint_captures_and_stores_session_state(tmp_path):
    store = InMemorySessionCheckpointStore()
    service, run = await _make_service(tmp_path, store)
    handle = ExecutionHandle(execution_mode="simulated", session_id="sess-xyz")

    await service._save_checkpoint(run, module_index=1, handle=handle)

    cp = await store.get(run.run_id)
    assert cp is not None
    assert cp.module_index == 1
    assert cp.session_id == "sess-xyz"
    # SIM 게이트웨이가 세션 식별 가능한 결정적 상태를 캡처했다.
    assert "sess-xyz" in cp.storage_state


@pytest.mark.asyncio
async def test_save_checkpoint_noop_without_store(tmp_path):
    service, run = await _make_service(tmp_path, None)
    handle = ExecutionHandle(execution_mode="simulated", session_id="sess-none")
    # 스토어 미주입이면 조용히 no-op(예외 없음).
    await service._save_checkpoint(run, module_index=0, handle=handle)


@pytest.mark.asyncio
async def test_reconcile_seals_run_without_checkpoint(tmp_path):
    """체크포인트가 없으면 재기동 시 진행 중 Run 을 봉인한다(로컬/시뮬 모드 종전 동작)."""
    store = InMemorySessionCheckpointStore()
    service, run = await _make_service(tmp_path, store)
    sealed = await service.reconcile_interrupted_runs()
    assert sealed == 1
    reloaded = await service._write_repo.get_run(run.run_id)
    assert reloaded.status == RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_reconcile_skips_sealing_when_checkpoint_present(tmp_path):
    """체크포인트가 있으면 봉인하지 않고 재개 잡을 재발행한다(임의 워커가 이어받음)."""
    from app.execution.session_checkpoint import SessionCheckpoint

    store = InMemorySessionCheckpointStore()
    service, run = await _make_service(tmp_path, store)
    # 재개 잡 재발행만 관측한다(실행하지 않는 기록용 핸들러).
    dispatched: list = []
    service._run_queue.set_run_job_handler(lambda d: dispatched.append(d) or _noop())
    service._run_queue.start()
    await store.save(
        SessionCheckpoint(
            run_id=run.run_id,
            system_code=run.system_code,
            execution_mode="simulated",
            module_index=0,
            session_id="sess",
            storage_state="{}",
        )
    )
    sealed = await service.reconcile_interrupted_runs()
    await service._run_queue.join()
    assert sealed == 0
    reloaded = await service._write_repo.get_run(run.run_id)
    assert reloaded.status != RunStatus.CANCELLED  # 봉인되지 않고 재개 대상으로 남는다.
    assert [d.kind for d in dispatched] == ["resume"]
    assert dispatched[0].start_index == 1  # checkpoint.module_index + 1


async def _noop() -> None:
    return None
