from __future__ import annotations

from app.core.system_models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.execution.results import StepExecutionResult
from app.execution.session_server import SessionServer


class InProcessExecutionGateway(ExecutionGateway):
    """``SessionServer`` 를 ``ExecutionGateway`` 포트로 노출하는 local fulfillment adapter.

    Windows 단일 PC 배포(``E2E_EXECUTION_MODE=local``)에서 API 프로세스가 Playwright를
    직접 구동할 때 쓴다. 오케스트레이터는 직렬화 가능한 ``ExecutionHandle`` 만 보고,
    라이브 브라우저·스레드 풀은 ``SessionServer`` 내부에만 존재한다.
    """

    def __init__(self, session_server: SessionServer) -> None:
        self._session_server = session_server

    def supports(self, execution_mode: str) -> bool:
        return self._session_server.supports_execution_mode(execution_mode)

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
        storage_state: str | None = None,
    ) -> ExecutionHandle:
        session_id = await self._session_server.open_session(
            execution_mode,
            input_data,
            run_id,
            module_id,
            storage_state,
        )
        return ExecutionHandle(execution_mode=execution_mode, session_id=session_id)

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        result, logs = await self._session_server.run_step(handle.session_id, run_id, module)
        for line in logs:
            await on_log(line)
        return result

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        await self._session_server.submit_input(handle.session_id, value)

    async def close_session(self, handle: ExecutionHandle) -> None:
        await self._session_server.close_session(handle.session_id)

    async def resume_from_step(
        self,
        handle: ExecutionHandle,
        module_index: int,
        workflow_step: str,
    ) -> None:
        await self._session_server.resume_from_step(handle.session_id, module_index, workflow_step)

    async def capture_storage_state(self, handle: ExecutionHandle) -> str | None:
        return await self._session_server.capture_storage_state(handle.session_id)
