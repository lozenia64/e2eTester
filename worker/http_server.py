from __future__ import annotations

import threading

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.enums import RecoveryTier
from app.execution.protocol import (
    CloseSessionRequest,
    ErrorResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    OpenSessionRequest,
    OpenSessionResponse,
    RecoverSessionRequest,
    RecoverSessionResponse,
    ResumeFromStepRequest,
    RunStepRequest,
    RunStepResponse,
    SubmitInputRequest,
    healing_attempt_to_payload,
)
from worker.health import SessionHeartbeatManager
from worker.session_server import SessionServer


def create_http_app(
    session_server: SessionServer,
    heartbeat_manager: SessionHeartbeatManager | None = None,
) -> Starlette:
    """게이트웨이 프로토콜 HTTP API(Starlette 미니 앱)."""

    async def open_session(request: Request) -> JSONResponse:
        body = OpenSessionRequest.model_validate(await request.json())
        try:
            session_id = await session_server.open_session(
                body.execution_mode,
                body.input_data,
                body.run_id,
                body.module_id,
                body.storage_state,
            )
            if heartbeat_manager is not None:
                await heartbeat_manager.register(
                    session_id,
                    run_id=body.run_id,
                    execution_mode=body.execution_mode,
                )
            return JSONResponse(OpenSessionResponse(session_id=session_id).model_dump())
        except Exception as exc:
            return JSONResponse(
                ErrorResponse(detail=str(exc)).model_dump(),
                status_code=500,
            )

    async def run_step(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        body = RunStepRequest.model_validate(await request.json())
        try:
            result, logs = await session_server.run_step(session_id, body.run_id, body.module)
            healing_events = [healing_attempt_to_payload(event) for event in result.healing_events]
            screenshot_path = str(result.screenshot_path) if result.screenshot_path else None
            response = RunStepResponse(
                status=result.status,
                message=result.message,
                artifacts=result.artifacts,
                current_url=result.current_url,
                dialog_messages=result.dialog_messages,
                last_error=result.last_error,
                screenshot_path=screenshot_path,
                healing_events=healing_events,
                failure_signal=result.failure_signal,
                logs=logs,
            )
            return JSONResponse(response.model_dump(mode="json"))
        except KeyError as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=404)
        except Exception as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=500)

    async def submit_input(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        body = SubmitInputRequest.model_validate(await request.json())
        try:
            await session_server.submit_input(session_id, body.value)
            return JSONResponse({"ok": True})
        except KeyError as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=404)
        except Exception as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=500)

    async def resume_from_step(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        body = ResumeFromStepRequest.model_validate(await request.json())
        try:
            await session_server.resume_from_step(session_id, body.module_index, body.workflow_step)
            return JSONResponse({"ok": True})
        except KeyError as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=404)
        except Exception as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=500)

    async def close_session(request: Request) -> JSONResponse:
        body = CloseSessionRequest.model_validate(await request.json())
        try:
            if heartbeat_manager is not None:
                await heartbeat_manager.unregister(body.session_id)
            await session_server.close_session(body.session_id)
            return JSONResponse({"ok": True})
        except Exception as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=500)

    async def capture_storage_state(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        try:
            # 알 수 없는 세션은 예외가 아니라 storage_state=None 을 돌려준다(체크포인트 생략).
            # API 측 게이트웨이도 이를 "캡처할 상태 없음"으로 읽어 실행을 막지 않는다.
            storage_state = await session_server.capture_storage_state(session_id)
            return JSONResponse({"storage_state": storage_state})
        except Exception as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=500)

    async def recover_session(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        body = RecoverSessionRequest.model_validate(await request.json())
        try:
            recovered = await session_server.recover(
                session_id, RecoveryTier(body.tier), body.entry_url
            )
            return JSONResponse(RecoverSessionResponse(recovered=recovered).model_dump())
        except KeyError as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=404)
        except Exception as exc:
            return JSONResponse(ErrorResponse(detail=str(exc)).model_dump(), status_code=500)

    async def heartbeat(request: Request) -> JSONResponse:
        body = HeartbeatRequest.model_validate(await request.json())
        ok = False
        if heartbeat_manager is not None:
            ok = await heartbeat_manager.heartbeat(body.session_id)
        return JSONResponse(HeartbeatResponse(ok=ok).model_dump())

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/sessions/open", open_session, methods=["POST"]),
            Route("/sessions/{session_id}/run-step", run_step, methods=["POST"]),
            Route("/sessions/{session_id}/submit-input", submit_input, methods=["POST"]),
            Route(
                "/sessions/{session_id}/resume-from-step",
                resume_from_step,
                methods=["POST"],
            ),
            Route(
                "/sessions/{session_id}/storage-state",
                capture_storage_state,
                methods=["POST"],
            ),
            Route(
                "/sessions/{session_id}/recover",
                recover_session,
                methods=["POST"],
            ),
            Route("/sessions/close", close_session, methods=["POST"]),
            Route("/sessions/heartbeat", heartbeat, methods=["POST"]),
        ],
    )


def start_http_server(
    session_server: SessionServer,
    *,
    host: str = "0.0.0.0",
    port: int = 8100,
    heartbeat_manager: SessionHeartbeatManager | None = None,
) -> threading.Thread:
    """uvicorn 으로 HTTP 서버를 백그라운드 스레드에서 띄운다."""
    app = create_http_app(session_server, heartbeat_manager)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    def _run() -> None:
        server.run()

    thread = threading.Thread(target=_run, name="worker-http", daemon=True)
    thread.start()
    return thread
