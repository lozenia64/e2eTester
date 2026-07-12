from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.api.dependencies import get_daily_queries
from app.auth.dependencies import get_current_user
from app.auth.models import User

if TYPE_CHECKING:
    from app.orchestrator.queries import DailyDashboardQueries


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/daily")
async def daily_dashboard(
    current_user: User = Depends(get_current_user),
    daily_queries: DailyDashboardQueries = Depends(get_daily_queries),
):
    """로그인 사용자의 접근 가능한 시스템별 **일간 점검 현황**(시스템·모듈 단위)."""
    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    return await daily_queries.get_daily_dashboard(allowed_system_codes=allowed)
