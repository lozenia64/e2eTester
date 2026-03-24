from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(tags=["ws"])


@router.websocket("/ws/runs/{run_id}")
async def run_updates(websocket: WebSocket, run_id: str):
    await websocket.accept()
    run_service = websocket.app.state.run_service
    queue = await run_service.subscribe(run_id)
    try:
        run = await run_service.get_run(run_id)
        await websocket.send_json(
            {
                "event_type": "snapshot",
                "run_id": run.run_id,
                "system_code": run.system_code,
                "run_status": run.status,
                "payload": run.model_dump(mode="json"),
            }
        )
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        await run_service.unsubscribe(run_id, queue)
