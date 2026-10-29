from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import (
    get_registry,
    get_schedule_repository,
    get_schedule_service,
)
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.suite.views.view import resolve_suite_request_for_user
from app.core.requests import (
    CreateScheduleRequest,
    CreateSuiteScheduleRequest,
    PauseScheduleRequest,
    StartSuiteRequest,
    UpdateScheduleRequest,
)
from app.core.schedule_models import Schedule

if TYPE_CHECKING:
    from app.contexts.scheduling.infrastructure.ports import ScheduleRepositoryPort
    from app.contexts.scheduling.scheduler import SchedulerService
    from app.registry.loader import ModuleRegistry


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


@router.get("/board")
async def schedule_board(
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    """관제 보드 — KPI + 문제 예약 분류(stuck/failing/missed/stale) 파생 필드 포함 목록."""
    user_id_filter = None if current_user.role == "admin" else current_user.user_id
    return await schedule_service.board(user_id=user_id_filter)


@router.get("/calendar")
async def schedule_calendar(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    """점검 시간표 — cron 미래 전개(계획) + schedule-triggered 실행(실적/누락) + 커버리지."""
    now = datetime.now(UTC)
    start = from_ if from_ is not None else now - timedelta(days=3)
    end = to if to is not None else now + timedelta(days=4)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    user_id_filter = None if current_user.role == "admin" else current_user.user_id
    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    try:
        return await schedule_service.calendar(
            start, end, user_id=user_id_filter, allowed_system_codes=allowed
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        schedule = await schedule_service.toggle(schedule_id, user_name=current_user.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.get("/{schedule_id}")
async def get_schedule_detail(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    """예약 상세(요약 + 변경 이력 + 저장된 입력값 키 목록 — 값(PII)은 미노출)."""
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    return await schedule_service.get_detail(schedule_id)


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: UpdateScheduleRequest,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    """예약 in-place 수정(이름/cron/모듈 선택/인증값 병합, suite 는 시스템 선택/브라우저 모드)."""
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        schedule = await schedule_service.update_schedule(
            schedule_id, payload, user_name=current_user.name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.get("/{schedule_id}/history")
async def schedule_history(
    schedule_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    """예약 단위 실행 이력(최근 N회 점 스트립 + 성공률/평균 소요/연속 성공 streak)."""
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    return await schedule_service.history(schedule_id, limit=limit)


@router.post("/{schedule_id}/pause-until")
async def pause_schedule_until(
    schedule_id: str,
    payload: PauseScheduleRequest,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    """일시 중지(~시각까지, 자동 재개). ``paused_until=null`` 은 즉시 재개."""
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        schedule = await schedule_service.pause_until(
            schedule_id, payload.paused_until, user_name=current_user.name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule.to_summary()


@router.post("/{schedule_id}/duplicate")
async def duplicate_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    schedule_service: SchedulerService = Depends(get_schedule_service),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
):
    """예약 복제 — 같은 대상/주기/입력의 새 예약(비활성 상태)을 만든다."""
    schedule = await _get_schedule_or_404(schedule_repo, schedule_id)
    _assert_can_manage_schedule(schedule, current_user)
    try:
        copy = await schedule_service.duplicate_schedule(
            schedule_id,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return copy.to_summary()


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
