from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import (
    get_registry,
    get_schedule_repository,
    get_schedule_service,
)
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.models import (
    CreateScheduleRequest,
    CreateSuiteScheduleRequest,
    Schedule,
    StartSuiteRequest,
)
from app.orchestrator.suite_view import resolve_suite_request_for_user

if TYPE_CHECKING:
    from app.registry.loader import ModuleRegistry
    from app.scheduling.scheduler import SchedulerService
    from app.storage.ports import ScheduleRepositoryPort


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


async def _get_schedule_or_404(schedule_repo: ScheduleRepositoryPort, schedule_id: str) -> Schedule:
    try:
        return await schedule_repo.get(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc


def _assert_can_manage_schedule(schedule: Schedule, current_user: User) -> None:
    if current_user.role == "admin":
        return
    if schedule.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="이 예약에 대한 권한이 없습니다.")


@router.get("")
async def list_schedules(
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    user_id_filter = None if current_user.role == "admin" else current_user.user_id
    return await schedule_service.list_schedules(user_id=user_id_filter)


@router.post("/systems/{system_code}")
async def create_schedule(
    system_code: str,
    payload: CreateScheduleRequest,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    if current_user.role != "admin" and system_code not in current_user.allowed_system_codes:
        raise HTTPException(status_code=403, detail="해당 시스템에 대한 접근 권한이 없습니다.")
    try:
        schedule = await schedule_service.create_schedule(
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
    payload: CreateSuiteScheduleRequest,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    registry: ModuleRegistry = Depends(get_registry),
):
    if current_user.role != "admin":
        all_codes = [s.system_code for s in registry.list_systems()]
        try:
            resolved = resolve_suite_request_for_user(
                StartSuiteRequest(
                    browser_mode=payload.browser_mode,
                    systems=payload.systems,
                    selected_system_codes=payload.selected_system_codes,
                    scope_system_codes=payload.scope_system_codes,
                ),
                all_system_codes=all_codes,
                allowed_system_codes=current_user.allowed_system_codes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        payload = payload.model_copy(
            update={
                "selected_system_codes": resolved.selected_system_codes,
                "scope_system_codes": resolved.scope_system_codes,
            }
        )
    try:
        schedule = await schedule_service.create_suite_schedule(
            payload,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        schedule = await schedule_service.toggle(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/run-now")
async def run_schedule_now(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        result = await schedule_service.run_now(
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
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        await schedule_service.delete_schedule(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    return {"ok": True}
