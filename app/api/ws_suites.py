from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


@router.websocket("/ws/suites/{suite_id}")
async def suite_updates(websocket: WebSocket, suite_id: str):
    await websocket.accept()
    suite_service = websocket.app.state.suite_service
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
