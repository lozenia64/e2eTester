from __future__ import annotations

import asyncio
from uuid import uuid4

from app.core.enums import ModuleStatus
from app.core.models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.runner.workflow_common import StepExecutionResult


class SimulatedExecutionGateway(ExecutionGateway):
    """실제 워크플로 실행기가 없는 모듈을 위한 테스트 더블 어댑터.

    ``execution_mode == "simulated"`` (``ModuleDefinition.execution_mode`` 의 기본값) 인
    모듈을 브라우저 없이 매니페스트의 ``simulated_duration_ms`` 만큼 대기한 뒤
    ``simulated_outcome`` 대로 PASSED/FAILED 를 돌려준다.

    이전에는 이 시뮬레이션 로직이 ``RunService`` (코어 오케스트레이터) 안에
    ``_run_simulated_module`` 로 인라인돼 테스트 관심사가 코어에 누수돼 있었다. 이제
    실제 실행과 똑같이 ``ExecutionGateway`` 포트 뒤의 어댑터로 분리해, 오케스트레이터는
    실행/시뮬레이션을 구분하지 않고 단일 포트로만 다룬다.
    """

    SIMULATED_MODE = "simulated"

    def supports(self, execution_mode: str) -> bool:
        return execution_mode == self.SIMULATED_MODE

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
    ) -> ExecutionHandle:
        # 시뮬레이션은 라이브 런타임이 없다. 포트 계약을 만족하는 토큰만 돌려준다.
        return ExecutionHandle(execution_mode=execution_mode, session_id=uuid4().hex)

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        await asyncio.sleep(module.simulated_duration_ms / 1000)
        if module.simulated_outcome.upper() in {
            ModuleStatus.FAILED.value,
            ModuleStatus.ANOMALY.value,
        }:
            return StepExecutionResult(
                status=ModuleStatus.ANOMALY,
                message="시뮬레이션 이상징후",
                artifacts=[],
                current_url=None,
                dialog_messages=[],
            )
        return StepExecutionResult(
            status=ModuleStatus.PASSED,
            message="시뮬레이션 성공",
            artifacts=[],
            current_url=None,
            dialog_messages=[],
        )

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        # 시뮬레이션 모듈은 입력 대기가 없다(no-op).
        return None

    async def close_session(self, handle: ExecutionHandle) -> None:
        # 정리할 라이브 세션이 없다(idempotent no-op).
        return None
