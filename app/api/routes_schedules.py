from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.models import CreateScheduleRequest


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("")
async def list_schedules(request: Request):
    return await request.app.state.schedule_service.list_schedules()


@router.post("/systems/{system_code}")
async def create_schedule(request: Request, system_code: str, payload: CreateScheduleRequest):
    try:
        schedule = await request.app.state.schedule_service.create_schedule(system_code, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(request: Request, schedule_id: str):
    try:
        schedule = await request.app.state.schedule_service.toggle(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/run-now")
async def run_schedule_now(request: Request, schedule_id: str):
    try:
        run = await request.app.state.schedule_service.run_now(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run.model_dump(mode="json")


@router.delete("/{schedule_id}")
async def delete_schedule(request: Request, schedule_id: str):
    try:
        await request.app.state.schedule_service.delete_schedule(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    return {"ok": True}
