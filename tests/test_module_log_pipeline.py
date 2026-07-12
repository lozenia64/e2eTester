"""WP-B5: 로그는 도메인 이벤트가 아니다 — 로그 스토어 + 실시간 채널 직행, 이벤트 스토어 미경유.

``_handle_module_log`` 는 로그 한 줄을 (1) 로그 스토어에 적재하고 (2) ``module_log``
DashboardEvent 로 실시간 채널에 직접 발행하되, **도메인 이벤트/아웃박스/프로젝션은 전혀
건드리지 않는다**(쓰기 핫패스 경량화). 모듈 최신 메시지는 애그리거트(유일 변이자)로 갱신한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import ModuleDefinition, Run, RunModule, SystemDefinition
from app.domain.run_aggregate import RunAggregate
from app.events.bus import EventBus
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.run_queue import RunExecutionQueue
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


class _RecordingRealtime:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


async def _make_service(tmp_path):
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
    module = RunModule(
        module_id="sim.mod", name="Mod", group="test", order=10, status=ModuleStatus.RUNNING
    )
    run = Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.RUNNING,
        requested_at=datetime.now(UTC),
        modules=[module],
        selected_module_ids=["sim.mod"],
    )
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run, events=RunAggregate.for_new_run(run).pull_events())
    realtime = _RecordingRealtime()
    queue = RunExecutionQueue(worker_count=1, backend=InMemoryJobQueue())
    service = RunService(
        registry=_FakeRegistry(system),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=realtime,
        log_store=InMemoryRunLogStore(),
        execution_gateway=SimulatedExecutionGateway(),
        event_bus=EventBus(),
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=InMemoryRunInputStore(),
        run_queue=queue,
    )
    return service, run, module, realtime, write_repo


@pytest.mark.asyncio
async def test_log_goes_to_store_and_realtime_without_domain_events(tmp_path):
    service, run, module, realtime, write_repo = await _make_service(tmp_path)
    # 로그 경로가 이벤트 스토어를 건드리지 않음을 감시하기 위해 append_events 를 계수한다.
    appended: list = []
    original = write_repo.append_events

    async def _spy(events):
        appended.append(list(events))
        return await original(events)

    write_repo.append_events = _spy  # type: ignore[method-assign]

    await service._handle_module_log(run, module, "  진행 로그 한 줄  ")

    # (1) 로그 스토어에 적재됐다.
    logs = await service._log_store.get(run.run_id, module.module_id)
    assert logs == ["진행 로그 한 줄"]

    # (2) 실시간 채널로 module_log 이벤트가 발행됐다.
    assert len(realtime.events) == 1
    event = realtime.events[0]
    assert event.event_type == "module_log"
    assert event.run_id == run.run_id
    assert event.payload == {"module_id": "sim.mod", "message": "진행 로그 한 줄"}

    # (3) 모듈 최신 메시지가 갱신됐다(애그리거트 경로).
    assert module.message == "진행 로그 한 줄"

    # (4) 도메인 이벤트는 산출/적재되지 않았다(로그 ≠ 도메인 이벤트).
    assert appended == []


@pytest.mark.asyncio
async def test_blank_log_line_is_ignored(tmp_path):
    service, run, module, realtime, _ = await _make_service(tmp_path)
    await service._handle_module_log(run, module, "   ")
    assert realtime.events == []
    assert await service._log_store.get(run.run_id, module.module_id) == []
