"""Phase C: RunService 가 세션 체크포인트를 저장하는 배선 검증(SIM, 브라우저 없음).

``_save_checkpoint`` 는 게이트웨이의 ``capture_storage_state`` 로 세션 상태를 캡처해
체크포인트 스토어에 저장한다. 스토어 미주입/게이트웨이 미지원이면 no-op(기존 흐름 무변경).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.contexts.run.application.service import RunService
from app.contexts.run.domain.aggregate import RunAggregate
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.events.bus import EventBus
from app.execution.gateway import ExecutionHandle
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.run_queue import RunExecutionQueue
from app.execution.session_checkpoint import InMemorySessionCheckpointStore
from app.execution.simulated_gateway import SimulatedExecutionGateway
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


def _sim_module(module_id: str, order: int) -> ModuleDefinition:
    return ModuleDefinition(
        module_id=module_id,
        system_code="sim",
        name=module_id,
        description="",
        group="test",
        order=order,
        execution_mode="simulated",
        simulated_duration_ms=1,
        simulated_outcome="PASSED",
    )


async def _make_service(tmp_path, checkpoint_store, *, module_ids=("sim.mod",)):
    system = SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[_sim_module(mid, 10 * (i + 1)) for i, mid in enumerate(module_ids)],
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
                module_id=mid,
                name=mid,
                group="test",
                order=10 * (i + 1),
                status=ModuleStatus.RUNNING,
            )
            for i, mid in enumerate(module_ids)
        ],
        selected_module_ids=list(module_ids),
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


@pytest.mark.asyncio
async def test_checkpoint_resume_restores_storage_state_into_new_session(tmp_path):
    """재기동 후 체크포인트 재개(pending 없음) → 새 세션을 storage_state 로 복원한다(WP-C2 복원 배선).

    dispatch_run_job(kind="resume") 이 pending 없이 들어오면 라이브 세션이 없는 재기동 재개로
    보고 handle=None 으로 새 세션을 연다. 이때 체크포인트의 storage_state 가 open_session 을
    거쳐 게이트웨이까지 흘러야 로그인 세션이 이어진다(SIM 게이트웨이가 수신을 기록).
    """
    from app.execution.job_queue_port import RunJobDescriptor
    from app.execution.session_checkpoint import SessionCheckpoint

    store = InMemorySessionCheckpointStore()
    service, run = await _make_service(tmp_path, store, module_ids=("sim.first", "sim.second"))
    await service._input_store.put(run.run_id, {"auth_method": "phone"})
    marker = '{"cookies": [{"name": "SID", "value": "restored-42"}]}'
    await store.save(
        SessionCheckpoint(
            run_id=run.run_id,
            system_code=run.system_code,
            execution_mode="simulated",
            module_index=0,
            session_id="dead-session",
            storage_state=marker,
        )
    )

    # 체크포인트 다음 모듈(index 1)부터 재개 — pending 이 없으므로 새 세션 경로.
    await service.dispatch_run_job(
        RunJobDescriptor(run_id=run.run_id, kind="resume", start_index=1)
    )

    # open_session 이 체크포인트 storage_state 를 그대로 게이트웨이까지 전달했다.
    assert marker in service._gateway.restored_storage_states.values()


@pytest.mark.asyncio
async def test_fresh_run_does_not_restore_storage_state(tmp_path):
    """start_index==0 신규 실행은 복원할 체크포인트가 없다(restore 배선이 오작동하지 않음)."""
    from app.execution.job_queue_port import RunJobDescriptor

    store = InMemorySessionCheckpointStore()
    service, run = await _make_service(tmp_path, store, module_ids=("sim.only",))
    await service._input_store.put(run.run_id, {"auth_method": "phone"})

    await service.dispatch_run_job(
        RunJobDescriptor(run_id=run.run_id, kind="execute", start_index=0)
    )

    assert service._gateway.restored_storage_states == {}


async def _noop() -> None:
    return None
