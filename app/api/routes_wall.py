"""상황판(/wall) — 로그인 없이 열리는 읽기 전용 공개 화면.

사무실 상시 디스플레이용이다. 기존 인증을 쓸 수 없는 이유: JWT 가 7일 만료이고
비인증 상태에서 비-API 경로는 /login 으로 리다이렉트하므로, 키보드 없는 디스플레이는
주마다 재로그인해야 하고 만료 순간 사무실 벽에 로그인 폼이 뜬다.

설계 원칙:
- **GET 전용, 부수효과 없음.** POST 를 만들지 않고 페이지에 링크·버튼을 두지 않는다.
- **JSON API 를 만들지 않는다.** 비인증 표면을 최소화하기 위해 서버 렌더 HTML 만 낸다.
- **인증 라우터와 물리적으로 분리한다.** routes_dashboard.py 는 전부 인증 경로이므로,
  비인증 라우트를 섞으면 다음 사람이 의존을 실수로 빼거나 붙일 위험이 생긴다.
- E2E_WALL_ENABLED=false 면 404 — 앱이 사내망 밖에 노출될 때의 차단 스위치다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import get_daily_summary_queries
from app.contexts.insights.application.wall_view import build_wall_view
from app.core.settings import get_settings
from app.web.asset_manifest import TEMPLATE_SEARCH_DIRS, asset_css, asset_js
from app.web.status_view import status_badge_view

if TYPE_CHECKING:
    from app.orchestrator.queries.daily_summary_queries import DailySummaryQueries

router = APIRouter(tags=["wall"])
templates = Jinja2Templates(directory=TEMPLATE_SEARCH_DIRS)
templates.env.globals["asset_js"] = asset_js
templates.env.globals["asset_css"] = asset_css
templates.env.globals["status_badge_view"] = status_badge_view


def wall_enabled() -> bool:
    """차단 스위치. 의존성으로 두어 테스트가 override 할 수 있게 한다."""
    return get_settings().wall_enabled


async def _load_view(summary_queries: DailySummaryQueries) -> dict[str, Any]:
    summary = await summary_queries.get_daily_summary(
        user_id=None,  # 상황판에 "내 기여분"은 의미가 없다
        allowed_system_codes=None,  # 전사 상황판
        is_admin=False,  # 절감 카드의 관리자 링크를 비운다
    )
    return build_wall_view(summary)


def _require_enabled(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/wall", response_class=HTMLResponse)
async def wall_page(
    request: Request,
    enabled: bool = Depends(wall_enabled),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """상황판 전체 페이지. 인증하지 않는다."""
    _require_enabled(enabled)
    view = await _load_view(summary_queries)
    return templates.TemplateResponse(request, "wall.html", {"view": view, "request": request})


@router.get("/wall/fragment", response_class=HTMLResponse)
async def wall_fragment(
    request: Request,
    enabled: bool = Depends(wall_enabled),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """htmx 갱신 대상 본문. 인증하지 않는다."""
    _require_enabled(enabled)
    view = await _load_view(summary_queries)
    return templates.TemplateResponse(
        request, "wall_fragment.html", {"view": view, "request": request}
    )
