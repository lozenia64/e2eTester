from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_run_queries, get_run_service
from app.auth.jwt import decode_token
from app.contexts.run.views.view import RunView

if TYPE_CHECKING:
    from app.contexts.run.application.service import RunService
    from app.orchestrator.queries import RunQueries


router = APIRouter(tags=["ws"])


@router.websocket("/ws/runs/{run_id}")
async def run_updates(
    websocket: WebSocket,
    run_id: str,
    run_service: RunService = Depends(get_run_service),
    run_queries: RunQueries = Depends(get_run_queries),
):
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = decode_token(token)
        if not payload.get("sub"):
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = await run_service.subscribe(run_id)
    try:
        run = await run_queries.get_run_detail(run_id)
        await websocket.send_json(
            {
                "event_type": "snapshot",
                "run_id": run.run_id,
                "system_code": run.system_code,
                "run_status": run.status,
                "payload": RunView.dump(run),
            }
        )
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        await run_service.unsubscribe(run_id, queue)
