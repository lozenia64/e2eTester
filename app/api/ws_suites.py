from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_suite_service
from app.auth.dependencies import get_user_service
from app.auth.jwt import decode_token
from app.orchestrator.suite_view import (
    SuiteView,
    filter_suite_event_for_user,
    filter_suite_for_user,
)

if TYPE_CHECKING:
    from app.auth.service import UserService
    from app.orchestrator.suite_service import SuiteService

router = APIRouter(tags=["ws"])


@router.websocket("/ws/suites/{suite_id}")
async def suite_updates(
    websocket: WebSocket,
    suite_id: str,
    suite_service: SuiteService = Depends(get_suite_service),
    user_service: UserService = Depends(get_user_service),
):
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008)
            return
        user = await user_service.get_user(user_id)
        if not user.is_active:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = await suite_service.subscribe(suite_id)
    try:
        suite = filter_suite_for_user(await suite_service.get_suite(suite_id), user)
        await websocket.send_json(
            {
                "event_type": "snapshot",
                "suite_id": suite.suite_id,
                "suite_status": suite.status,
                "payload": SuiteView.dump(suite),
            }
        )
        while True:
            event = filter_suite_event_for_user(await queue.get(), user)
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        await suite_service.unsubscribe(suite_id, queue)
