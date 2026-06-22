from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_suite_service
from app.auth.jwt import decode_token

if TYPE_CHECKING:
    from app.orchestrator.suite_service import SuiteService

router = APIRouter(tags=["ws"])


@router.websocket("/ws/suites/{suite_id}")
async def suite_updates(
    websocket: WebSocket,
    suite_id: str,
    suite_service: "SuiteService" = Depends(get_suite_service),
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
    queue = await suite_service.subscribe(suite_id)
    try:
        suite = await suite_service.get_suite(suite_id)
        await websocket.send_json(
            {
                "event_type": "snapshot",
                "suite_id": suite.suite_id,
                "suite_status": suite.status,
                "payload": suite.model_dump(mode="json"),
            }
        )
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        await suite_service.unsubscribe(suite_id, queue)
