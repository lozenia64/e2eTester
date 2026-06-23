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
    run_service: "RunService" = Depends(get_run_service),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.role == "admin":
        return RedirectResponse(url="/admin", status_code=302)
    systems = run_service.list_systems()
    if current_user.role != "admin":
        systems = [s for s in systems if s.system_code in current_user.allowed_system_codes]
    systems_payload = {system.system_code: system.model_dump(mode="json") for system in systems}
    system_codes = [system.system_code for system in systems]
    analyzer_status = GeminiFailureAnalyzer.inspect_env_status()
    email_status = RunCompletionEmailNotifier.inspect_env_status(system_codes)
    return templates.TemplateResponse(
        request,
        "index.html",
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
    suite_service: "SuiteService" = Depends(get_suite_service),
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


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_dashboard(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_service: "RunService" = Depends(get_run_service),
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
