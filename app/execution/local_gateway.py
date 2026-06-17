from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from app.core.models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_common import StepExecutionResult
from app.systems.loader import load_workflow_executors


class LocalExecutionGateway(ExecutionGateway):
    """브라우저 실행을 현재 프로세스 안에서 수행하는 in-process 어댑터.

    Playwright sync API 객체는 자신을 만든 스레드에서만 써야 하므로, 세션마다 단일
    스레드 풀(``max_workers=1``)을 만들고 build/step/input/close 를 모두 그 스레드에서
    돌린다. 이벤트 루프 ↔ 실행 스레드 사이의 로그 브리지(``run_coroutine_threadsafe``)도
    여기서 캡슐화하므로, 오케스트레이터는 스레드/런타임/Playwright 의 존재를 전혀 모른다.

    이 클래스가 곧 "워커 경계"의 in-process 구현이다. 같은 ``ExecutionGateway`` 포트로
    별도 프로세스/원격 워커 구현체를 끼워 넣으면 오케스트레이터를 손대지 않고 실행을
    격리할 수 있다.
    """

    def __init__(self, artifact_manager: ArtifactManager, system_codes: Iterable[str]) -> None:
        self._executors = load_workflow_executors(system_codes, artifact_manager)

    def supports(self, execution_mode: str) -> bool:
        return execution_mode in self._executors

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
    ) -> ExecutionHandle:
        executor = self._require_executor(execution_mode)
        prefix = execution_mode.replace("_workflow_step", "")
        thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{prefix}-runtime-{run_id}")
        try:
            runtime = await asyncio.get_running_loop().run_in_executor(
                thread_pool,
                executor.build_runtime,
                input_data,
                run_id,
                module_id,
            )
        except Exception:
            thread_pool.shutdown(wait=False, cancel_futures=True)
            raise
        runtime.executor = thread_pool
        return ExecutionHandle(execution_mode=execution_mode, runtime=runtime)

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        executor = self._require_executor(handle.execution_mode)
        runtime = handle.runtime
        loop = asyncio.get_running_loop()

        # 실행 스레드에서 찍힌 로그를 이벤트 루프의 async 콜백으로 동기 브리지한다.
        def emit_from_thread(line: str) -> None:
            asyncio.run_coroutine_threadsafe(on_log(line), loop).result()

        return await self._run_on_session_thread(
            runtime,
            executor.execute_step,
            runtime,
            run_id,
            module,
            emit_from_thread,
        )

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        executor = self._require_executor(handle.execution_mode)
        runtime = handle.runtime
        await self._run_on_session_thread(runtime, executor.update_otp_code, runtime, value)

    async def close_session(self, handle: ExecutionHandle) -> None:
        executor = self._executors.get(handle.execution_mode)
        runtime = handle.runtime
        if executor is None or runtime is None:
            return
        thread_pool = runtime.executor
        try:
            await self._run_on_session_thread(runtime, executor.close_runtime, runtime)
        finally:
            if thread_pool is not None:
                thread_pool.shutdown(wait=True, cancel_futures=True)
                runtime.executor = None

    @staticmethod
    async def _run_on_session_thread(runtime, fn, *args):
        """세션 전용 스레드(있으면)에서 호출을 수행한다. 없으면 임시 스레드로 폴백."""
        thread_pool = getattr(runtime, "executor", None)
        if thread_pool is None:
            return await asyncio.to_thread(fn, *args)
        return await asyncio.get_running_loop().run_in_executor(thread_pool, fn, *args)

    def _require_executor(self, execution_mode: str):
        executor = self._executors.get(execution_mode)
        if executor is None:
            raise KeyError(f"Unsupported workflow execution mode: {execution_mode}")
        return executor
