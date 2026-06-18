from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import require_admin
from app.auth.models import User
from app.core.models import CreateScheduleRequest, CreateSuiteScheduleRequest


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("")
async def list_schedules(request: Request, current_user: User = Depends(require_admin)):
    return await request.app.state.schedule_service.list_schedules()


@router.post("/systems/{system_code}")
async def create_schedule(
    request: Request,
    system_code: str,
    payload: CreateScheduleRequest,
    current_user: User = Depends(require_admin),
):
    try:
        schedule = await request.app.state.schedule_service.create_schedule(
            system_code,
            payload,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/suites")
async def create_suite_schedule(
    request: Request,
    payload: CreateSuiteScheduleRequest,
    current_user: User = Depends(require_admin),
):
    try:
        schedule = await request.app.state.schedule_service.create_suite_schedule(
            payload,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(
    request: Request,
    schedule_id: str,
    current_user: User = Depends(require_admin),
):
    try:
        schedule = await request.app.state.schedule_service.toggle(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/run-now")
async def run_schedule_now(
    request: Request,
    schedule_id: str,
    current_user: User = Depends(require_admin),
):
    try:
        result = await request.app.state.schedule_service.run_now(
            schedule_id,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.delete("/{schedule_id}")
async def delete_schedule(
    request: Request,
    schedule_id: str,
    current_user: User = Depends(require_admin),
):
    try:
        await request.app.state.schedule_service.delete_schedule(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    return {"ok": True}
