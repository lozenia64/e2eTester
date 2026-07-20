"""OTP 제출 후 resume 작업이 pending 컨텍스트를 복원할 수 있는지 검증."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.contexts.run.application.service import RunService
from app.contexts.run.infrastructure.in_memory_run_control_store import InMemoryRunControlStore
from app.contexts.run.infrastructure.in_memory_run_input_store import InMemoryRunInputStore
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.job_queue_port import RunJobDescriptor
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.platform.artifact_manager import ArtifactManager
from app.platform.eventing.bus import EventBus
from app.realtime.adapter import RealtimeNotificationAdapter
from app.registry.loader import ModuleRegistry


def _waiting_run() -> Run:
    return Run(
        run_id="run_otp",
        system_code="hrp",
        system_name="HRP",
        status=RunStatus.WAITING_INPUT,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hrp.main.access",
                name="메인화면 접속",
                group="access",
                order=0,
                status=ModuleStatus.PASSED,
            ),
            RunModule(
                module_id="hrp.login",
                name="로그인",
                group="login",
                order=1,
                status=ModuleStatus.WAITING_INPUT,
            ),
        ],
        selected_module_ids=["hrp.main.access", "hrp.login"],
    )


@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp("otp-resume")


async def test_submit_otp_keeps_pending_until_resume_dispatch(tmp_path):
    run = _waiting_run()
    control = InMemoryRunControlStore()
    await control.set_pending("run_otp", "sess-1", "simulated", 1, "hrp.login")
    write_repo = InMemoryRunRepository()
    await write_repo.create_run(run)
    input_store = InMemoryRunInputStore()
    await input_store.put("run_otp", {"user_id": "test", "password": "secret"})

    service = RunService(
        registry=ModuleRegistry(),
        write_repo=write_repo,
        summary_query=AsyncMock(),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([SimulatedExecutionGateway()]),
        event_bus=EventBus(),
        control_store=control,
        input_store=input_store,
        run_queue=AsyncMock(),
        artifact_manager=ArtifactManager(root_dir=tmp_path / "artifacts"),
    )
    service._execute_run = AsyncMock()  # type: ignore[method-assign]

    await service.submit_otp("run_otp", "123456")

    pending = await control.get_pending("run_otp")
    assert pending is not None
    assert pending.session_id == "sess-1"
    assert pending.resume_index == 1

    await service.dispatch_run_job(
        RunJobDescriptor(
            run_id="run_otp",
            kind="resume",
            start_index=1,
            label="run:run_otp:resume",
        )
    )

    assert await control.get_pending("run_otp") is None
    service._execute_run.assert_awaited_once()
    args = service._execute_run.await_args
    assert args.args[0] == "run_otp"
    assert args.args[2] == 1
