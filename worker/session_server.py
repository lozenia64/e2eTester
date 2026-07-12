from __future__ import annotations

import asyncio
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.core.system_models import ModuleDefinition
from app.execution.results import StepExecutionResult
from app.platform.artifact_manager import ArtifactManager
from app.systems.loader import load_workflow_executors


@dataclass
class _Session:
    """워커 내부 라이브 세션(Playwright 런타임 + 단일 스레드 풀)."""

    execution_mode: str
    runtime: Any
    executor: ThreadPoolExecutor
    run_id: str
    resume_module_index: int | None = None
    resume_workflow_step: str | None = None


class SessionServer:
    """Playwright 세션을 워커 프로세스 안에서 관리한다.

    ``LocalExecutionGateway`` 와 동일한 스레드 어피니티·로그 브리지 규약을 따르며,
    원격 HTTP API(``worker/http_server``)가 이 클래스를 호출한다. 자가 치유 엔진은
    원격 모드에서 워커에만 부착된다.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        system_codes: Iterable[str],
        healing_engine=None,
    ) -> None:
        if healing_engine is None:
            self._executors = load_workflow_executors(system_codes, artifact_manager)
        else:
            self._executors = load_workflow_executors(
                system_codes, artifact_manager, healing_engine=healing_engine
            )
        self._sessions: dict[str, _Session] = {}

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
    ) -> str:
        executor = self._require_executor(execution_mode)
        prefix = execution_mode.replace("_workflow_step", "")
        thread_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"{prefix}-runtime-{run_id}"
        )
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
        session_id = uuid4().hex
        self._sessions[session_id] = _Session(
            execution_mode=execution_mode,
            runtime=runtime,
            executor=thread_pool,
            run_id=run_id,
        )
        return session_id

    async def run_step(
        self,
        session_id: str,
        run_id: str,
        module: ModuleDefinition,
    ) -> tuple[StepExecutionResult, list[str]]:
        session = self._require_session(session_id)
        executor = self._require_executor(session.execution_mode)
        runtime = session.runtime
        loop = asyncio.get_running_loop()
        log_queue: asyncio.Queue[str | None] = asyncio.Queue()
        logs: list[str] = []

        def emit_from_thread(line: str) -> None:
            loop.call_soon_threadsafe(log_queue.put_nowait, line)

        async def drain_logs() -> None:
            while True:
                line = await log_queue.get()
                if line is None:
                    return
                logs.append(line)

        drain_task = asyncio.create_task(drain_logs())
        try:
            result = await self._run_on_session_thread(
                session.executor,
                executor.execute_step,
                runtime,
                run_id,
                module,
                emit_from_thread,
            )
            return result, logs
        finally:
            loop.call_soon_threadsafe(log_queue.put_nowait, None)
            await drain_task

    async def submit_input(self, session_id: str, value: str) -> None:
        session = self._require_session(session_id)
        executor = self._require_executor(session.execution_mode)
        await self._run_on_session_thread(
            session.executor, executor.update_otp_code, session.runtime, value
        )

    async def resume_from_step(
        self,
        session_id: str,
        module_index: int,
        workflow_step: str,
    ) -> None:
        session = self._require_session(session_id)
        session.resume_module_index = module_index
        session.resume_workflow_step = workflow_step

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        executor = self._executors.get(session.execution_mode)
        try:
            if executor is not None and session.runtime is not None:
                await self._run_on_session_thread(
                    session.executor, executor.close_runtime, session.runtime
                )
        finally:
            session.executor.shutdown(wait=True, cancel_futures=True)

    def get_session_run_id(self, session_id: str) -> str | None:
        session = self._sessions.get(session_id)
        return session.run_id if session else None

    def get_session_execution_mode(self, session_id: str) -> str | None:
        session = self._sessions.get(session_id)
        return session.execution_mode if session else None

    @staticmethod
    async def _run_on_session_thread(pool: ThreadPoolExecutor, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(pool, fn, *args)

    def _require_executor(self, execution_mode: str):
        executor = self._executors.get(execution_mode)
        if executor is None:
            raise KeyError(f"Unsupported workflow execution mode: {execution_mode}")
        return executor

    def _require_session(self, session_id: str) -> _Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown execution session: {session_id}")
        return session
