from __future__ import annotations

from collections.abc import Iterable

from app.core.enums import RecoveryTier
from app.core.system_models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.execution.results import StepExecutionResult


class CompositeExecutionGateway(ExecutionGateway):
    """여러 ``ExecutionGateway`` 어댑터를 ``execution_mode`` 로 라우팅하는 합성 게이트웨이.

    오케스트레이터는 단일 포트만 보고, 실제 실행(``WorkerExecutionGateway`` → 워커
    ``SessionServer``)과 시뮬레이션(``SimulatedExecutionGateway``)을 한 인터페이스로 다룬다.
    어느 어댑터가 어떤 모드를 담당하는지는 컴포지션 루트(``AppContainer``)가 어댑터 목록 순서로 정한다.

    - ``supports`` / ``open_session`` 은 ``execution_mode`` 인자로 담당 어댑터를 고른다.
    - 세션 수명 메서드(``run_step`` / ``submit_input`` / ``close_session``)는 핸들이 들고
      있는 ``execution_mode`` 로 고른다(핸들은 직렬화 가능한 값이라 모드를 항상 담는다).
    """

    def __init__(self, gateways: Iterable[ExecutionGateway]) -> None:
        self._gateways: list[ExecutionGateway] = list(gateways)

    def _for_mode(self, execution_mode: str) -> ExecutionGateway:
        for gateway in self._gateways:
            if gateway.supports(execution_mode):
                return gateway
        raise KeyError(f"지원하지 않는 실행 모드입니다: {execution_mode}")

    def supports(self, execution_mode: str) -> bool:
        return any(gateway.supports(execution_mode) for gateway in self._gateways)

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
        storage_state: str | None = None,
    ) -> ExecutionHandle:
        return await self._for_mode(execution_mode).open_session(
            execution_mode, input_data, run_id, module_id, storage_state
        )

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        return await self._for_mode(handle.execution_mode).run_step(handle, run_id, module, on_log)

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        await self._for_mode(handle.execution_mode).submit_input(handle, value)

    async def close_session(self, handle: ExecutionHandle) -> None:
        await self._for_mode(handle.execution_mode).close_session(handle)

    async def resume_from_step(
        self,
        handle: ExecutionHandle,
        module_index: int,
        workflow_step: str,
    ) -> None:
        await self._for_mode(handle.execution_mode).resume_from_step(
            handle, module_index, workflow_step
        )

    async def recover_session(
        self,
        handle: ExecutionHandle,
        tier: RecoveryTier,
        entry_url: str | None,
    ) -> bool:
        return await self._for_mode(handle.execution_mode).recover_session(handle, tier, entry_url)
