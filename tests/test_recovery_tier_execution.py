"""복구 등급 실행(되감기) 배선 테스트."""

from __future__ import annotations

from app.core.enums import RecoveryTier
from app.execution.gateway import ExecutionGateway, ExecutionHandle


class _MinimalGateway(ExecutionGateway):
    """recover_session 을 구현하지 않은 어댑터 — 기본 구현이 False 여야 한다."""

    def supports(self, execution_mode: str) -> bool:
        return True

    async def open_session(self, execution_mode, input_data, run_id, module_id, storage_state=None):
        raise NotImplementedError

    async def run_step(self, handle, run_id, module, on_log):
        raise NotImplementedError

    async def submit_input(self, handle, value):
        raise NotImplementedError

    async def close_session(self, handle):
        raise NotImplementedError

    async def resume_from_step(self, handle, module_index, workflow_step):
        raise NotImplementedError


async def test_recover_session_defaults_to_unsupported():
    """되감기를 지원하지 않는 어댑터는 조용히 False 를 돌려준다(기존 어댑터 무변경)."""
    gateway = _MinimalGateway()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    supported = await gateway.recover_session(
        handle, RecoveryTier.RESET_TO_MODULE_ENTRY, "https://example.com/entry"
    )

    assert supported is False


async def test_simulated_gateway_records_recovery_calls():
    from app.execution.simulated_gateway import SimulatedExecutionGateway

    gateway = SimulatedExecutionGateway()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    await gateway.recover_session(handle, RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert gateway.recovery_calls == [(RecoveryTier.REPLAY_FROM_LOGIN, None)]


async def test_tier_zero_never_calls_recover_session():
    """tier 0 은 현행 동작 — 되감기 호출이 없어야 한다."""
    from app.execution.simulated_gateway import SimulatedExecutionGateway

    gateway = SimulatedExecutionGateway()
    assert gateway.recovery_calls == []
