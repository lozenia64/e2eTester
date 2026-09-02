from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_admin_dashboard_queries, get_run_queries, get_run_service
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.views.view import RunView
from app.core.requests import StartRunRequest, SubmitOtpRequest
from app.orchestrator.queries.admin_dashboard_queries import (
    AdminDashboardQueries,
    _schedule_tz,
)

if TYPE_CHECKING:
    from app.contexts.run.application.service import RunService
    from app.orchestrator.queries import RunQueries


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
async def list_runs(
    scope: Literal["today", "before_today"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    run_queries: RunQueries = Depends(get_run_queries),
):
    user_id_filter = None if current_user.role == "admin" else current_user.user_id
    return await run_queries.list_run_summaries(
        limit=limit,
        user_id=user_id_filter,
        scope=scope,
    )


_ACTOR_FIELDS = ("created_by_user_id", "created_by_user_name")


def _permitted_codes(user: User) -> frozenset[str] | None:
    """admin은 전 시스템, 그 외는 허용 목록. None은 '필터 없음'."""
    if user.role == "admin":
        return None
    return frozenset(user.allowed_system_codes)


@router.get("/coverage")
async def runs_coverage(
    current_user: User = Depends(get_current_user),
    admin_queries: AdminDashboardQueries = Depends(get_admin_dashboard_queries),
):
    """시스템 x 7일 점검 커버리지(사용자 권한 범위, PII 없음)."""
    return await admin_queries.get_coverage_dashboard(system_codes=_permitted_codes(current_user))


@router.get("/day")
async def runs_of_day(
    system_code: str,
    day: str,
    current_user: User = Depends(get_current_user),
    run_queries: RunQueries = Depends(get_run_queries),
):
    """격자 셀 드릴다운 — 그 날 그 시스템의 Run 전량.

    셀에 실린 대표 run_id를 쓰지 않는 이유는 서버가 슬롯당 한 건으로 접기
    때문이다(설계 D4). 권한 축은 격자와 같은 시스템 축이고(D8), 실행자
    필드는 싣지 않는다(D9).
    """
    permitted = _permitted_codes(current_user)
    if permitted is not None and system_code not in permitted:
        raise HTTPException(status_code=403, detail="해당 시스템에 대한 접근 권한이 없습니다.")
    try:
        day_start_local = datetime.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="day는 YYYY-MM-DD 형식이어야 합니다.") from exc
    tz = _schedule_tz()
    since = day_start_local.replace(tzinfo=tz).astimezone(UTC)
    before = since + timedelta(days=1)
    page = await run_queries.list_run_summaries_page(
        limit=200,
        system_code=system_code,
        requested_since=since,
        requested_before=before,
    )
    return [
        {key: value for key, value in item.items() if key not in _ACTOR_FIELDS}
        for item in page["items"]
    ]


@router.post("/systems/{system_code}")
async def start_system_run(
    system_code: str,
    payload: StartRunRequest,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    if current_user.role != "admin" and system_code not in current_user.allowed_system_codes:
        raise HTTPException(status_code=403, detail="해당 시스템에 대한 접근 권한이 없습니다.")
    try:
        run = await run_service.start_run(
            system_code,
            payload.input_data,
            payload.selected_module_ids,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RunView.dump(run)


@router.post("/{run_id}/otp")
async def submit_run_otp(
    run_id: str,
    payload: SubmitOtpRequest,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = await run_service.submit_otp(run_id, payload.otp_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not waiting for OTP") from exc
    return RunView.dump(run)


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = await run_service.cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RunView.dump(run)


@router.post("/{run_id}/rerun")
async def rerun_run(
    run_id: str,
    from_module: str | None = Query(default=None, alias="from_module"),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = await run_service.rerun_run(
            run_id,
            user_id=current_user.user_id,
            user_name=current_user.name,
            from_module_id=from_module,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RunView.dump(run)


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_queries: RunQueries = Depends(get_run_queries),
):
    try:
        run = await run_queries.get_run_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return RunView.dump(run)


@router.get("/{run_id}/nodes")
async def get_run_nodes(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_queries: RunQueries = Depends(get_run_queries),
):
    try:
        run = await run_queries.get_run_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return [module.model_dump(mode="json") for module in run.modules]
