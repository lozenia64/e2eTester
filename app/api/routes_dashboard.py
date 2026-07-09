from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.api.dependencies import get_run_service, get_suite_service
from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.suite_view import filter_suite_for_user

if TYPE_CHECKING:
    from app.orchestrator.run_service import RunService
    from app.orchestrator.suite_service import SuiteService

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """일간 점검 현황 대시보드(로그인 후 첫 화면). 데이터는 JS 가 `/api/dashboard/daily` 로 로드."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.role == "admin":
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"current_user": current_user},
    )


@router.get("/runs/execute", response_class=HTMLResponse)
async def run_execute(
    request: Request,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """시스템 단위 점검 실행 화면(기존 대시보드의 Run 트리거 UI)."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.role == "admin":
        return RedirectResponse(url="/admin", status_code=302)
    systems = run_service.list_systems()
    systems = [s for s in systems if s.system_code in current_user.allowed_system_codes]
    systems_payload = {system.system_code: system.model_dump(mode="json") for system in systems}
    system_codes = [system.system_code for system in systems]
    analyzer_status = GeminiFailureAnalyzer.inspect_env_status()
    email_status = RunCompletionEmailNotifier.inspect_env_status(system_codes)
    return templates.TemplateResponse(
        request,
        "execute.html",
        {
            "systems": systems,
            "systems_payload": systems_payload,
            "analyzer_status": analyzer_status,
            "email_status": email_status,
            "current_user": current_user,
        },
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request, current_user: User = Depends(require_admin)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {"current_user": current_user},
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, current_user: User = Depends(require_admin)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {"current_user": current_user},
    )


@router.get("/admin/modules", response_class=HTMLResponse)
async def admin_modules(request: Request, current_user: User = Depends(require_admin)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "admin/modules.html",
        {"current_user": current_user},
    )


@router.get("/admin/ops", response_class=HTMLResponse)
async def admin_ops(request: Request, current_user: User = Depends(require_admin)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "admin/ops.html",
        {"current_user": current_user},
    )


@router.get("/admin/stats", response_class=HTMLResponse)
async def admin_stats(request: Request, current_user: User = Depends(require_admin)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "admin/stats.html",
        {"current_user": current_user},
    )


@router.get("/suites/{suite_id}", response_class=HTMLResponse)
async def suite_dashboard(
    request: Request,
    suite_id: str,
    current_user: User = Depends(get_current_user),
    suite_service: SuiteService = Depends(get_suite_service),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        suite = await suite_service.get_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    suite = filter_suite_for_user(suite, current_user)
    return templates.TemplateResponse(
        request,
        "suite.html",
        {
            "suite": suite,
            "current_user": current_user,
        },
    )


@router.get("/runs/history", response_class=HTMLResponse)
async def runs_history(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.role == "admin":
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(
        request,
        "runs_history.html",
        {"current_user": current_user},
    )


def _accessible_systems(current_user: User, run_service: RunService) -> list[dict]:
    """시스템 선택기용 — 접근 가능한 시스템(관리자는 전체)을 display_order 순으로."""
    systems = run_service.list_systems()
    if current_user.role != "admin":
        allowed = set(current_user.allowed_system_codes)
        systems = [s for s in systems if s.system_code in allowed]
    systems = sorted(systems, key=lambda s: (s.display_order, s.name))
    return [{"system_code": s.system_code, "name": s.name} for s in systems]


@router.get("/anomalies", response_class=HTMLResponse)
async def anomalies_inbox(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """이상징후 인박스(팀 전체 작업목록). 관리자도 접근 가능(리다이렉트 없음)."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "anomalies.html",
        {"current_user": current_user},
    )


@router.get("/insights", response_class=HTMLResponse)
async def insights_index(
    request: Request,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """시스템 인사이트(헬스/타임라인/모듈 딥다이브 3탭). 관리자도 접근 가능."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    systems = _accessible_systems(current_user, run_service)
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "current_user": current_user,
            "systems": systems,
            "selected_code": systems[0]["system_code"] if systems else None,
        },
    )


@router.get("/systems/{system_code}/insights", response_class=HTMLResponse)
async def system_insights(
    request: Request,
    system_code: str,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """특정 시스템으로 프리셀렉트된 인사이트 화면."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    systems = _accessible_systems(current_user, run_service)
    codes = {s["system_code"] for s in systems}
    if system_code not in codes:
        raise HTTPException(status_code=404, detail="시스템을 찾을 수 없습니다.")
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "current_user": current_user,
            "systems": systems,
            "selected_code": system_code,
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_dashboard(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        run = await run_service.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "run": run,
            "current_user": current_user,
        },
    )
