from __future__ import annotations

import asyncio
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.core.system_models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.execution.results import StepExecutionResult
from app.platform.artifact_manager import ArtifactManager
from app.systems.loader import load_workflow_executors


@dataclass
class _Session:
    """게이트웨이 내부에만 존재하는 라이브 세션 상태(=워커 경계 객체). 핸들 밖으로 새지 않는다.

    실행 스레드(단일 스레드 풀)는 **세션이 명시적으로 소유**한다. 과거에는 이 풀을
    ``runtime.executor`` 로 도메인 런타임에 몽키패치해, 모든 시스템 런타임이 게이트웨이를 위해
    ``executor`` 필드를 들고 있어야 했다(인프라 관심사가 도메인 모델로 누수). 이제 풀은 여기
    세션에만 있고, 시스템 런타임은 브라우저/페이지 같은 자기 상태만 가진다.
    """

    execution_mode: str
    runtime: Any
    executor: ThreadPoolExecutor
    resume_module_index: int | None = None
    resume_workflow_step: str | None = None


class LocalExecutionGateway(ExecutionGateway):
    """브라우저 실행을 현재 프로세스 안에서 수행하는 in-process 어댑터.

    Playwright sync API 객체는 자신을 만든 스레드에서만 써야 하므로, 세션마다 단일
    스레드 풀(``max_workers=1``)을 만들고 build/step/input/close 를 모두 그 스레드에서
    돌린다. 라이브 런타임은 ``session_id`` 키의 내부 레지스트리(``_sessions``)에만 보관하고,
    오케스트레이터에는 직렬화 가능한 토큰(``ExecutionHandle``)만 돌려준다 — 라이브 객체가
    오케스트레이터/OTP 일시정지 상태로 새지 않는다.

    이벤트 루프 ↔ 실행 스레드 사이의 로그 브리지는 **논블로킹 큐**로 분리한다. 실행 스레드는
    ``loop.call_soon_threadsafe`` 로 큐에 라인을 넣기만 하고(이벤트 루프 완료를 기다리지 않음),
    이벤트 루프의 드레인 태스크가 큐를 순서대로 비우며 ``on_log`` 를 호출한다. 따라서 느린
    이벤트 루프가 더 이상 실행 스레드를 라인 단위로 블로킹하지 못한다(데이터 평면 ↔ 제어 평면
    backpressure 제거). 순서 보장은 큐의 FIFO + 드레인 태스크 직렬 처리로 유지된다.

    이 클래스가 곧 "워커 경계"의 in-process 구현이다. 같은 ``ExecutionGateway`` 포트로
    별도 프로세스/원격 워커 구현체를 끼워 넣으면 오케스트레이터를 손대지 않고 실행을
    격리할 수 있다.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        system_codes: Iterable[str],
        healing_engine=None,
    ) -> None:
        # healing_engine(선택): 스텝 실패 시 대체 셀렉터를 탐색하는 자가 치유 엔진.
        # 로더가 각 실행기에 부착하며, 미주입이면 실행기는 치유 없이 기존과 동일하게 동작한다.
        # (미주입 시 kwargs 없이 호출해 로더 시그니처 하위호환을 유지한다.)
        if healing_engine is None:
            self._executors = load_workflow_executors(system_codes, artifact_manager)
        else:
            self._executors = load_workflow_executors(
                system_codes, artifact_manager, healing_engine=healing_engine
            )
        self._sessions: dict[str, _Session] = {}

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
        # 스레드 풀은 세션이 명시적으로 소유한다(런타임에 몽키패치하지 않는다).
        session_id = uuid4().hex
        self._sessions[session_id] = _Session(
            execution_mode=execution_mode, runtime=runtime, executor=thread_pool
        )
        return ExecutionHandle(execution_mode=execution_mode, session_id=session_id)

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        session = self._require_session(handle)
        executor = self._require_executor(session.execution_mode)
        runtime = session.runtime
        loop = asyncio.get_running_loop()

        # 실행 스레드 → 이벤트 루프 로그 브리지: 블로킹 없이 큐에 넣기만 한다.
        # ``call_soon_threadsafe`` 는 스레드 안전하고 즉시 반환하므로(이벤트 루프 완료를
        # 기다리지 않음) 느린 루프가 실행 스레드를 라인 단위로 막지 못한다.
        log_queue: asyncio.Queue[str | None] = asyncio.Queue()

        def emit_from_thread(line: str) -> None:
            loop.call_soon_threadsafe(log_queue.put_nowait, line)

        # 드레인 태스크가 큐를 FIFO 로 직렬 소비하므로 로그 순서가 보존된다.
        async def drain_logs() -> None:
            while True:
                line = await log_queue.get()
                if line is None:
                    return
                await on_log(line)

        drain_task = asyncio.create_task(drain_logs())
        try:
            return await self._run_on_session_thread(
                session.executor,
                executor.execute_step,
                runtime,
                run_id,
                module,
                emit_from_thread,
            )
        finally:
            # 센티넬은 ``call_soon_threadsafe`` 로 넣어, 실행 스레드가 앞서 넣은 모든 라인
            # 뒤에 오도록(FIFO) 보장한다. 드레인 완료를 기다려, 남은 로그가 모두
            # append/publish 된 뒤에야 run_step 이 반환된다(module_finished 이벤트보다 로그가 앞섬).
            loop.call_soon_threadsafe(log_queue.put_nowait, None)
            await drain_task

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        session = self._require_session(handle)
        executor = self._require_executor(session.execution_mode)
        await self._run_on_session_thread(
            session.executor, executor.update_otp_code, session.runtime, value
        )

    async def resume_from_step(
        self,
        handle: ExecutionHandle,
        module_index: int,
        workflow_step: str,
    ) -> None:
        session = self._require_session(handle)
        session.resume_module_index = module_index
        session.resume_workflow_step = workflow_step

    async def close_session(self, handle: ExecutionHandle) -> None:
        session = self._sessions.pop(handle.session_id, None)
        if session is None:
            # 이미 닫혔거나 알 수 없는 세션이면 조용히 무시한다(idempotent).
            return
        executor = self._executors.get(session.execution_mode)
        try:
            if executor is not None and session.runtime is not None:
                await self._run_on_session_thread(
                    session.executor, executor.close_runtime, session.runtime
                )
        finally:
            # 세션이 소유한 스레드 풀은 세션 종료와 함께 정리한다(런타임에 매달려 있지 않다).
            session.executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    async def _run_on_session_thread(pool: ThreadPoolExecutor, fn, *args):
        """세션 전용 단일 스레드 풀에서 동기 호출을 수행한다(Playwright 스레드 어피니티 보존)."""
        return await asyncio.get_running_loop().run_in_executor(pool, fn, *args)

    def _require_executor(self, execution_mode: str):
        executor = self._executors.get(execution_mode)
        if executor is None:
            raise KeyError(f"Unsupported workflow execution mode: {execution_mode}")
        return executor

    def _require_session(self, handle: ExecutionHandle) -> _Session:
        session = self._sessions.get(handle.session_id)
        if session is None:
            raise KeyError(f"Unknown execution session: {handle.session_id}")
        return session
