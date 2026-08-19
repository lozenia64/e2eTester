from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import get_daily_queries, get_daily_summary_queries
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.insights.application.daily_dashboard import system_summary_badge
from app.web.asset_manifest import TEMPLATE_SEARCH_DIRS, asset_css, asset_js

if TYPE_CHECKING:
    from app.orchestrator.queries import DailyDashboardQueries
    from app.orchestrator.queries.daily_summary_queries import DailySummaryQueries


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory=TEMPLATE_SEARCH_DIRS)
templates.env.globals["system_summary_badge"] = system_summary_badge
templates.env.globals["asset_js"] = asset_js
templates.env.globals["asset_css"] = asset_css

_FRAGMENT_TEMPLATES = {
    "kpi": "dashboard/partials/zone_a_kpi.html",
    "matrix": "dashboard/partials/zone_b_matrix.html",
}


async def _load_dashboard(
    daily_queries: DailyDashboardQueries,
    current_user: User,
) -> dict:
    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    return await daily_queries.get_daily_dashboard(allowed_system_codes=allowed)


async def _load_summary(
    summary_queries: DailySummaryQueries,
    current_user: User,
) -> dict:
    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    return await summary_queries.get_daily_summary(
        user_id=current_user.user_id,
        allowed_system_codes=allowed,
    )


@router.get("/daily")
async def daily_dashboard(
    current_user: User = Depends(get_current_user),
    daily_queries: DailyDashboardQueries = Depends(get_daily_queries),
):
    """로그인 사용자의 접근 가능한 시스템별 **일간 점검 현황**(시스템·모듈 단위)."""
    return await _load_dashboard(daily_queries, current_user)


@router.get("/daily/summary")
async def daily_summary(
    current_user: User = Depends(get_current_user),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """KPI 카드 4장(통과율·스스로 복구·승인 대기·절감). 사용자별 분해는 담지 않는다."""
    return await _load_summary(summary_queries, current_user)


@router.get("/daily/fragments/{zone}", response_class=HTMLResponse)
async def daily_dashboard_fragment(
    zone: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    daily_queries: DailyDashboardQueries = Depends(get_daily_queries),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """HTMX용 일간 대시보드 zone partial."""
    template_name = _FRAGMENT_TEMPLATES.get(zone)
    if template_name is None:
        raise HTTPException(status_code=404, detail="unknown fragment zone")
    if zone == "kpi":
        data = await _load_summary(summary_queries, current_user)
    else:
        data = await _load_dashboard(daily_queries, current_user)
    return templates.TemplateResponse(
        request,
        template_name,
        {"data": data, "request": request},
    )


@router.get("/daily/fragments/system/{system_code}/panel", response_class=HTMLResponse)
async def daily_system_panel(
    system_code: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    daily_queries: DailyDashboardQueries = Depends(get_daily_queries),
):
    """모듈·시스템 드릴다운 패널(HTMX)."""
    data = await _load_dashboard(daily_queries, current_user)
    system = next((s for s in data["systems"] if s["system_code"] == system_code), None)
    if system is None:
        raise HTTPException(status_code=404, detail="system not found")
    return templates.TemplateResponse(
        request,
        "dashboard/partials/system_panel.html",
        {
            "data": data,
            "system": system,
            "request": request,
        },
    )
