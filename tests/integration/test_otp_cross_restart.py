"""OTP 교차 재기동 — 세션 리스가 살아 있으면 WAITING_INPUT Run 을 봉인하지 않는다."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.run.application.service import RunService
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.events.bus import EventBus
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.realtime.adapter import RealtimeNotificationAdapter
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.storage.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.storage.run_control_store import InMemoryRunControlStore
from app.storage.run_input_store import InMemoryRunInputStore
from app.storage.run_log_store import InMemoryRunLogStore
from app.storage.run_repository import InMemoryRunRepository


class _FakeSessionRegistry:
    def __init__(self, alive_sessions: set[str]) -> None:
        self._alive = alive_sessions

    async def is_alive(self, session_id: str) -> bool:
        return session_id in self._alive


class _NoopQueue:
    async def submit(self, *_args, **_kwargs) -> None:
        pass

    async def enqueue_run_job(self, *_args, **_kwargs) -> None:
        pass


def _waiting_run(session_id: str = "sess-alive") -> Run:
    return Run(
        run_id="run_wait",
        system_code="hom",
        system_name="HOM",
        status=RunStatus.WAITING_INPUT,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="login",
                name="로그인",
                group="auth",
                order=0,
                status=ModuleStatus.WAITING_INPUT,
            )
        ],
    )


@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp("otp-restart")


async def test_reconcile_preserves_waiting_input_when_session_alive(tmp_path):
    run = _waiting_run("sess-alive")
    control = InMemoryRunControlStore()
    await control.set_pending("run_wait", "sess-alive", "hom_workflow_step", 1, "login")
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run)

    service = RunService(
        registry=ModuleRegistry(),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([SimulatedExecutionGateway()]),
        event_bus=EventBus(),
        control_store=control,
        input_store=InMemoryRunInputStore(),
        run_queue=_NoopQueue(),
        artifact_manager=ArtifactManager(root_dir=tmp_path / "artifacts"),
        session_registry=_FakeSessionRegistry({"sess-alive"}),
    )

    sealed = await service.reconcile_interrupted_runs()
    assert sealed == 0
    preserved = await write_repo.get_run("run_wait")
    assert preserved.status == RunStatus.WAITING_INPUT
    pending = await control.get_pending("run_wait")
    assert pending is not None
    assert pending.session_id == "sess-alive"


async def test_reconcile_seals_waiting_input_when_session_dead(tmp_path):
    run = _waiting_run("sess-dead")
    control = InMemoryRunControlStore()
    await control.set_pending("run_wait", "sess-dead", "hom_workflow_step", 1, "login")
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run)

    service = RunService(
        registry=ModuleRegistry(),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([SimulatedExecutionGateway()]),
        event_bus=EventBus(),
        control_store=control,
        input_store=InMemoryRunInputStore(),
        run_queue=_NoopQueue(),
        artifact_manager=ArtifactManager(root_dir=tmp_path / "artifacts"),
        session_registry=_FakeSessionRegistry(set()),
    )

    sealed = await service.reconcile_interrupted_runs()
    assert sealed == 1
    cancelled = await write_repo.get_run("run_wait")
    assert cancelled.status == RunStatus.CANCELLED
    assert await control.get_pending("run_wait") is None
