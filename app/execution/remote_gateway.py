from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

from app.core.models import ModuleDefinition
from app.execution.gateway import ExecutionGateway, ExecutionHandle, LogSink
from app.execution.protocol import (
    CloseSessionRequest,
    HeartbeatRequest,
    OpenSessionRequest,
    OpenSessionResponse,
    RunStepRequest,
    RunStepResponse,
    SubmitInputRequest,
)
from app.execution.redis_session_registry import RedisSessionRegistry
from app.healing.models import HealingAction, HealingAttempt
from app.runner.workflow_common import StepExecutionResult

# 원격 게이트웨이가 지원하는 워크플로 실행 모드 접미사.
_WORKFLOW_MODE_SUFFIX = "_workflow_step"


class RemoteExecutionGateway(ExecutionGateway):
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
    ) -> ExecutionHandle:
        request = OpenSessionRequest(
            execution_mode=execution_mode,
            input_data=input_data,
            run_id=run_id,
            module_id=module_id,
        )
        response = await self._post_json("/sessions/open", request.model_dump(), OpenSessionResponse)
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

    async def heartbeat_session(self, session_id: str, worker_id: str) -> bool:
        """세션 하트비트를 워커에 전달한다(리스 갱신)."""
        request = HeartbeatRequest(worker_id=worker_id, session_id=session_id)
        response = await self._post_json("/sessions/heartbeat", request.model_dump(), dict)
        return bool(response.get("ok"))

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
                raise RuntimeError(f"원격 실행 오류 {exc.code}: {detail}") from exc
            if response_type is dict:
                return data
            return response_type.model_validate(data)

        return await asyncio.to_thread(_request)
