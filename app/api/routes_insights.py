from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_insights_service
from app.auth.dependencies import get_current_user
from app.auth.models import User

if TYPE_CHECKING:
    from app.contexts.insights.application.insights_service import InsightsService


router = APIRouter(prefix="/api/systems", tags=["insights"])


def _ensure_access(current_user: User, system_code: str) -> None:
    """권한 밖 시스템/미지정 접근을 존재 노출 없이 404 로."""
    if current_user.role == "admin":
        return
    if system_code not in current_user.allowed_system_codes:
        raise HTTPException(status_code=404, detail="시스템을 찾을 수 없습니다.")


@router.get("/{system_code}/health")
async def system_health(
    system_code: str,
    days: int = Query(30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    insights: InsightsService = Depends(get_insights_service),
):
    """시스템 헬스 대시보드 — 통과율 스코어·추이·모듈 안정성 랭킹·캘린더 히트맵."""
    _ensure_access(current_user, system_code)
    try:
        return await insights.get_system_health(system_code, days=days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="시스템을 찾을 수 없습니다.") from exc


@router.get("/{system_code}/timeline")
async def system_timeline(
    system_code: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    insights: InsightsService = Depends(get_insights_service),
):
    """시스템 수직 타임라인 — Run 카드·회귀 시작점·변화 칩."""
    _ensure_access(current_user, system_code)
    try:
        return await insights.get_system_timeline(system_code, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="시스템을 찾을 수 없습니다.") from exc


@router.get("/{system_code}/modules/breakdown")
async def module_breakdown(
    system_code: str,
    current_user: User = Depends(get_current_user),
    insights: InsightsService = Depends(get_insights_service),
):
    """모듈 딥다이브 — 파이프라인 노드·소요/실패 분포·스크린샷 스트립·누적 소요."""
    _ensure_access(current_user, system_code)
    try:
        return await insights.get_module_breakdown(system_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="시스템을 찾을 수 없습니다.") from exc
