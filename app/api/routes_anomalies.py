from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_insights_service
from app.auth.dependencies import get_current_user
from app.auth.models import User

if TYPE_CHECKING:
    from app.contexts.insights.application.insights_service import InsightsService


router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


class AnomalyUpdate(BaseModel):
    state: str | None = None
    assignee_user_id: str | None = None
    memo: str | None = None


def _allowed(current_user: User) -> list[str] | None:
    return None if current_user.role == "admin" else current_user.allowed_system_codes


@router.get("")
async def list_anomalies(
    current_user: User = Depends(get_current_user),
    insights: InsightsService = Depends(get_insights_service),
):
    """ANOMALY/ERROR 로 끝난 모듈(이상건) 인박스 — 처리상태·담당자·메모 포함."""
    return await insights.list_anomalies(allowed_system_codes=_allowed(current_user))


@router.get("/assignees")
async def list_assignees(
    current_user: User = Depends(get_current_user),
    insights: InsightsService = Depends(get_insights_service),
):
    """담당자 배정 드롭다운용 사용자 목록."""
    return await insights.list_assignees(allowed_system_codes=_allowed(current_user))


@router.patch("/{module_run_id}")
async def update_anomaly(
    module_run_id: str,
    payload: AnomalyUpdate,
    current_user: User = Depends(get_current_user),
    insights: InsightsService = Depends(get_insights_service),
):
    """이상건 처리상태/담당자/메모 갱신(부분 병합)."""
    try:
        handling = await insights.update_anomaly(
            module_run_id,
            state=payload.state,
            assignee_user_id=payload.assignee_user_id,
            memo=payload.memo,
            actor_user_id=current_user.user_id,
            allowed_system_codes=_allowed(current_user),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="이상건을 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return handling.model_dump(mode="json")
