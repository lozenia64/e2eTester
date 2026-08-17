from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from app.contexts.healing.models import HealingAction, HealingAttempt
from app.core.system_models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.execution.protocol import (
    CloseSessionRequest,
    HeartbeatRequest,
    OpenSessionRequest,
    OpenSessionResponse,
    ResumeFromStepRequest,
    RunStepRequest,
    RunStepResponse,
    SubmitInputRequest,
)
from app.execution.redis_session_registry import RedisSessionRegistry
from app.execution.results import StepExecutionResult

# 원격 게이트웨이가 지원하는 워크플로 실행 모드 접미사.
_WORKFLOW_MODE_SUFFIX = "_workflow_step"


_REDIS_PY_CONNECT_RE = re.compile(r"error\s+\d+\s+connecting\s+to\s+", re.IGNORECASE)


def _looks_like_redis_infra_error(detail: str) -> bool:
    lowered = detail.lower()
    if "redis" in lowered:
        return True
    return bool(_REDIS_PY_CONNECT_RE.search(detail))


def _format_remote_error(code: int, detail: str) -> str:
    if _looks_like_redis_infra_error(detail):
        return (
            f"인프라 오류 {code}: Redis 에 연결할 수 없습니다. "
            "scripts/run_local.py 로 기동하거나 Redis 를 먼저 실행하세요. "
            f"상세: {detail}"
        )
    return f"원격 실행 오류 {code}: {detail}"


class WorkerExecutionGateway(ExecutionGateway):
    """원격 워커 HTTP API 를 호출하는 ExecutionGateway 클라이언트.

    API 프로세스의 오케스트레이터가 브라우저 실행을 워커 프로세스에 위임할 때 쓴다.
    세션 리스는 ``RedisSessionRegistry`` 로 워커와 공유해 OTP 교차 재기동을 지원한다.
    """

    REMOTE_MODE = "remote"

    def __init__(
        self,
        worker_base_url: str,
        session_registry: RedisSessionRegistry | None = None,
    ) -> None:
        self._base_url = worker_base_url.rstrip("/")
        self._session_registry = session_registry

    def supports(self, execution_mode: str) -> bool:
        if execution_mode == self.REMOTE_MODE:
            return True
        return execution_mode.endswith(_WORKFLOW_MODE_SUFFIX)

    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
        storage_state: str | None = None,
    ) -> ExecutionHandle:
        request = OpenSessionRequest(
            execution_mode=execution_mode,
            input_data=input_data,
            run_id=run_id,
            module_id=module_id,
            storage_state=storage_state,
        )
        response = await self._post_json(
            "/sessions/open", request.model_dump(), OpenSessionResponse
        )
        return ExecutionHandle(execution_mode=execution_mode, session_id=response.session_id)

    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        request = RunStepRequest(run_id=run_id, module=module)
        response = await self._post_json(
            f"/sessions/{handle.session_id}/run-step",
            request.model_dump(mode="json"),
            RunStepResponse,
        )
        for line in response.logs:
            await on_log(line)
        healing_events = [
            HealingAttempt(
                broken_selector=event.broken_selector,
                action=HealingAction(event.action),
                healed_selector=event.healed_selector,
                confidence=event.confidence,
                strategy=event.strategy,
                candidates_considered=event.candidates_considered,
                error_excerpt=event.error_excerpt,
                page_url=event.page_url,
                duration_ms=event.duration_ms,
                retry_succeeded=event.retry_succeeded,
            )
            for event in response.healing_events
        ]
        screenshot_path = Path(response.screenshot_path) if response.screenshot_path else None
        return StepExecutionResult(
            status=response.status,
            message=response.message,
            artifacts=response.artifacts,
            current_url=response.current_url,
            dialog_messages=response.dialog_messages,
            last_error=response.last_error,
            screenshot_path=screenshot_path,
            healing_events=healing_events,
            failure_signal=response.failure_signal,
        )

    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        request = SubmitInputRequest(value=value)
        await self._post_json(
            f"/sessions/{handle.session_id}/submit-input",
            request.model_dump(),
            dict,
        )

    async def close_session(self, handle: ExecutionHandle) -> None:
        request = CloseSessionRequest(session_id=handle.session_id)
        try:
            await self._post_json("/sessions/close", request.model_dump(), dict)
        finally:
            if self._session_registry is not None:
                await self._session_registry.unregister(handle.session_id)

    async def resume_from_step(
        self,
        handle: ExecutionHandle,
        module_index: int,
        workflow_step: str,
    ) -> None:
        request = ResumeFromStepRequest(module_index=module_index, workflow_step=workflow_step)
        await self._post_json(
            f"/sessions/{handle.session_id}/resume-from-step",
            request.model_dump(),
            dict,
        )

    async def heartbeat_session(self, session_id: str, worker_id: str) -> bool:
        """세션 하트비트를 워커에 전달한다(리스 갱신)."""
        request = HeartbeatRequest(worker_id=worker_id, session_id=session_id)
        response = await self._post_json("/sessions/heartbeat", request.model_dump(), dict)
        return bool(response.get("ok"))

    async def capture_storage_state(self, handle: ExecutionHandle) -> str | None:
        """워커에서 세션 storage_state 를 받아 온다(Phase C 내구 체크포인트 캡처).

        워커가 세션 스레드에서 ``context.storage_state()`` 를 직렬화해 돌려주고, API 는 이 값을
        암호화해 ``SessionCheckpointStorePort`` 에 저장한다(워커는 DB 직접 접근 금지). 실패는
        체크포인트 생략으로 처리(``None``)해 실행을 막지 않는다.
        """
        try:
            response = await self._post_json(
                f"/sessions/{handle.session_id}/storage-state", {}, dict
            )
        except Exception:
            return None
        return response.get("storage_state")

    async def _post_json(self, path: str, payload: dict, response_type: type):
        url = f"{self._base_url}{path}"
        body = json.dumps(payload).encode("utf-8")

        def _request() -> dict:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    raw = resp.read().decode("utf-8")
                    if not raw:
                        return {}
                    data = json.loads(raw)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(_format_remote_error(exc.code, detail)) from exc
            if response_type is dict:
                return data
            return response_type.model_validate(data)

        return await asyncio.to_thread(_request)
