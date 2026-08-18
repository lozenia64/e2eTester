"""RunService 의 OTP 안전장치(설계 R3) 테스트.

tier 2(REPLAY_FROM_LOGIN) 로그인 재주행은 로그인 모듈을 다시 태워 사람의 OTP 입력을 다시
요구할 수 있다. OTP SMS 중계가 설정돼 있지 않으면 그 되감기는 무인 실행을 영원히
멈추게 하므로, ``RunService._recover_session_for_retry`` 는 되감기 자체를 생략해야 한다
(제자리 재시도로 폴백 — 결국 실패가 빠르게 확정된다).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.contexts.run.application.service import RunService
from app.contexts.run.infrastructure.in_memory_run_input_store import InMemoryRunInputStore
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
from app.contexts.run.infrastructure.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_control_store import SqliteRunControlStore
from app.core.enums import ModuleStatus, RecoveryTier, RunStatus
from app.core.run_models import Run, RunModule
from app.core.settings import E2ESettings
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.gateway import ExecutionHandle
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


def _build_service(
    *,
    inner_gateway: SimulatedExecutionGateway,
    requires_user_input: bool,
    settings: E2ESettings,
    tmp_path,
) -> RunService:
    module_def = ModuleDefinition(
        module_id="login",
        system_code="sim",
        name="Login",
        description="",
        group="auth",
        order=1,
        requires_user_input=requires_user_input,
    )
    system = SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[module_def],
        execution_profile="light",
    )
    write_repo = InMemoryRunRepository()
    return RunService(
        registry=_FakeRegistry(system),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([inner_gateway]),
        event_bus=EventBus(),
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=InMemoryRunInputStore(),
        run_queue=RunExecutionQueue(worker_count=1),
        settings=settings,
    )


def _run() -> Run:
    return Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.RUNNING,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="login", name="Login", group="auth", order=1, status=ModuleStatus.RUNNING
            )
        ],
    )


@pytest.mark.asyncio
async def test_replay_from_login_skipped_when_otp_relay_missing_and_input_required(tmp_path):
    settings = E2ESettings(_env_file=None)  # otp_relay_token 미설정(기본값)
    inner_gateway = SimulatedExecutionGateway()
    service = _build_service(
        inner_gateway=inner_gateway, requires_user_input=True, settings=settings, tmp_path=tmp_path
    )
    run = _run()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    await service._recover_session_for_retry(
        run, run.modules[0], handle, RecoveryTier.REPLAY_FROM_LOGIN, "https://example.com/login"
    )

    assert inner_gateway.recovery_calls == []


@pytest.mark.asyncio
async def test_replay_from_login_proceeds_when_otp_relay_configured(tmp_path):
    settings = E2ESettings(_env_file=None, E2E_OTP_RELAY_TOKEN="relay-token-123")
    inner_gateway = SimulatedExecutionGateway()
    service = _build_service(
        inner_gateway=inner_gateway, requires_user_input=True, settings=settings, tmp_path=tmp_path
    )
    run = _run()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    await service._recover_session_for_retry(
        run, run.modules[0], handle, RecoveryTier.REPLAY_FROM_LOGIN, "https://example.com/login"
    )

    assert inner_gateway.recovery_calls == [
        (RecoveryTier.REPLAY_FROM_LOGIN, "https://example.com/login")
    ]


@pytest.mark.asyncio
async def test_replay_from_login_proceeds_when_no_module_requires_input(tmp_path):
    """R3 는 사람 입력이 필요한 모듈이 있을 때만 적용된다 — 그런 모듈이 없으면 OTP 중계
    미설정이라도 되감기를 막을 이유가 없다."""
    settings = E2ESettings(_env_file=None)
    inner_gateway = SimulatedExecutionGateway()
    service = _build_service(
        inner_gateway=inner_gateway, requires_user_input=False, settings=settings, tmp_path=tmp_path
    )
    run = _run()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    await service._recover_session_for_retry(
        run, run.modules[0], handle, RecoveryTier.REPLAY_FROM_LOGIN, "https://example.com/login"
    )

    assert inner_gateway.recovery_calls == [
        (RecoveryTier.REPLAY_FROM_LOGIN, "https://example.com/login")
    ]


@pytest.mark.asyncio
async def test_otp_relay_token_blank_after_strip_counts_as_not_configured(tmp_path):
    """공백만 있는 토큰은 설정되지 않은 것으로 취급한다(otp_relay_token_str 의 strip 규칙)."""
    settings = E2ESettings(_env_file=None, E2E_OTP_RELAY_TOKEN="   ")
    inner_gateway = SimulatedExecutionGateway()
    service = _build_service(
        inner_gateway=inner_gateway, requires_user_input=True, settings=settings, tmp_path=tmp_path
    )
    run = _run()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    await service._recover_session_for_retry(
        run, run.modules[0], handle, RecoveryTier.REPLAY_FROM_LOGIN, "https://example.com/login"
    )

    assert inner_gateway.recovery_calls == []
