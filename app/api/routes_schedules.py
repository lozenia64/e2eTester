from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.models import CreateScheduleRequest, CreateSuiteScheduleRequest, Schedule


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


async def _get_schedule_or_404(request: Request, schedule_id: str) -> Schedule:
    try:
        return await request.app.state.schedule_service._repository.get(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc


def _assert_can_manage_schedule(schedule: Schedule, current_user: User) -> None:
    if current_user.role == "admin":
        return
    if schedule.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="이 예약에 대한 권한이 없습니다.")


@router.get("")
async def list_schedules(request: Request, current_user: User = Depends(get_current_user)):
    user_id_filter = None if current_user.role == "admin" else current_user.user_id
    return await request.app.state.schedule_service.list_schedules(user_id=user_id_filter)


@router.post("/systems/{system_code}")
async def create_schedule(
    request: Request,
    system_code: str,
    payload: CreateScheduleRequest,
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin" and system_code not in current_user.allowed_system_codes:
        raise HTTPException(status_code=403, detail="해당 시스템에 대한 접근 권한이 없습니다.")
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
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        allowed = current_user.allowed_system_codes
        all_codes = [s.system_code for s in request.app.state.run_service._registry.list_systems()]
        requested = payload.selected_system_codes or all_codes
        blocked = [code for code in requested if code not in allowed]
        if blocked:
            raise HTTPException(status_code=403, detail=f"접근 권한이 없는 시스템: {', '.join(blocked)}")
        payload = payload.model_copy(
            update={"selected_system_codes": [code for code in requested if code in allowed]}
        )
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
    current_user: User = Depends(get_current_user),
):
    schedule = await _get_schedule_or_404(request, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
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
    current_user: User = Depends(get_current_user),
):
    schedule = await _get_schedule_or_404(request, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
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
    current_user: User = Depends(get_current_user),
):
    schedule = await _get_schedule_or_404(request, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        await request.app.state.schedule_service.delete_schedule(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    return {"ok": True}
