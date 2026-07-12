from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_run_queries, get_run_service
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.models import StartRunRequest, SubmitOtpRequest
from app.orchestrator.run_view import RunView

if TYPE_CHECKING:
    from app.orchestrator.queries import RunQueries
    from app.orchestrator.run_service import RunService


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
