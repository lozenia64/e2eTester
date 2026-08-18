from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.core.enums import RecoveryTier
from app.core.system_models import ModuleDefinition
from app.execution.results import StepExecutionResult
from app.platform.artifact_manager import ArtifactManager
from app.systems.loader import load_workflow_executors


def _storage_state_of(runtime: Any) -> str | None:
    """세션 스레드에서 실행: runtime.page.context.storage_state() → JSON(없으면 None)."""
    page = getattr(runtime, "page", None)
    context = getattr(page, "context", None)
    if context is None:
        return None
    return json.dumps(context.storage_state())


@dataclass
class _Session:
    """워커 내부 라이브 세션(Playwright 런타임 + 단일 스레드 풀)."""

    execution_mode: str
    runtime: Any
    executor: ThreadPoolExecutor
    run_id: str
    # tier 2 되감기(런타임 재생성)에 필요한 최초 개설 인자.
    input_data: dict[str, str]
    module_id: str
    resume_module_index: int | None = None
    resume_workflow_step: str | None = None


class SessionServer:
    """Playwright 세션을 워커 프로세스 안에서 관리한다.

    Playwright sync 객체의 스레드 어피니티(세션 전용 단일 스레드 풀)와 스레드↔이벤트 루프
    로그 브리지 규약을 따르는 **유일한 in-process 브라우저 호스트**다(구 ``LocalExecutionGateway``
    폐기). 원격 HTTP API(``worker/http_server``)가 이 클래스를 호출하며, 자가 치유 엔진은
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
        storage_state: str | None = None,
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
                storage_state,
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
            input_data=input_data,
            module_id=module_id,
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

    async def capture_storage_state(self, session_id: str) -> str | None:
        """세션 브라우저 컨텍스트의 Playwright ``storage_state``(쿠키+localStorage) JSON(Phase C).

        Playwright sync API 는 세션 스레드에서만 호출 가능하므로 세션 전용 풀에서 실행한다.
        모듈 경계·OTP 일시정지 시 API 가 이 값을 받아 내구 체크포인트에 암호화 저장한다.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return await self._run_on_session_thread(
            session.executor, _storage_state_of, session.runtime
        )

    async def recover(
        self,
        session_id: str,
        tier: RecoveryTier,
        entry_url: str | None,
    ) -> bool:
        """재시도 전에 세션을 ``tier`` 만큼 되감는다. 되감았으면 True.

        되감기 실패는 예외로 전파하지 않는다 — 호출자는 실패 시 제자리 재시도로 진행한다.
        """
        try:
            session = self._require_session(session_id)
        except Exception:
            return False

        if tier is RecoveryTier.RESET_TO_MODULE_ENTRY:
            if entry_url is None:
                return False
            return await self._reset_to_entry(session, entry_url)
        if tier is RecoveryTier.REPLAY_FROM_LOGIN:
            return await self._reopen_session(session)
        return False

    async def _reset_to_entry(self, session: _Session, entry_url: str) -> bool:
        """열린 다이얼로그 기록을 끊고 진입 URL 로 재이동한다."""

        def _navigate() -> bool:
            page = session.runtime.page
            # 되감기 이후의 스텝이 과거 다이얼로그를 자기 것으로 오해하지 않도록 경계를 끊는다.
            dialogs = getattr(session.runtime, "dialog_messages", None)
            if dialogs is not None:
                dialogs.clear()
            page.goto(entry_url)
            page.wait_for_load_state("domcontentloaded")
            return True

        try:
            # Playwright sync 객체의 스레드 어피니티 때문에 세션 전용 풀에서 실행한다.
            return await self._run_on_session_thread(session.executor, _navigate)
        except Exception:
            return False

    async def _reopen_session(self, session: _Session) -> bool:
        """런타임을 폐기하고 같은 session_id 로 다시 만든다.

        **주의 — 이름(`REPLAY_FROM_LOGIN`)과 달리 로그인 모듈을 다시 주행하지는 않는다.**
        여기서 하는 일은 브라우저 런타임 재구축까지다. 따라서 공용 `user_data_dir` 을 쓰는
        레거시 시스템에서는 Chromium 프로필 잠금으로 재구축이 실패해 tier 0 으로 안전하게
        폴백하고, 그 외 시스템에서는 새 컨텍스트에 쿠키가 없어 재시도가 미인증으로 실패한다 —
        현재 tier 2 에 실질적 복구 이득이 없는 이유다. 재개설 성공 후 로그인 모듈을 다시
        태우는 것은 후속 작업이다(SPEC-RUN-006 FR-004 의 '현행 구현 한계' 참고).
        """
        workflow_executor = self._executors[session.execution_mode]

        def _rebuild():
            # 세션을 폐기하므로 쿠키/storage_state 를 복원하지 않는다.
            # 새 런타임을 먼저 만들고, 실패하면 옛 런타임을 닫지 않는다(제자리 재시도).
            new_runtime = workflow_executor.build_runtime(
                session.input_data, session.run_id, session.module_id, None
            )
            try:
                workflow_executor.close_runtime(session.runtime)
            except Exception:
                # 새 런타임이 있으면 옛 런타임 누수가 닫힌 현재 세션보다 낫다.
                pass
            return new_runtime

        try:
            session.runtime = await self._run_on_session_thread(session.executor, _rebuild)
        except Exception:
            return False
        return True

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
