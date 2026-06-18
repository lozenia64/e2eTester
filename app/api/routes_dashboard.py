from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.notifications.run_completion_email import RunCompletionEmailNotifier

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, current_user: User = Depends(get_current_user)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    run_service = request.app.state.run_service
    systems = run_service.list_systems()
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
        },
    )


@router.get("/suites/{suite_id}", response_class=HTMLResponse)
async def suite_dashboard(request: Request, suite_id: str, current_user: User = Depends(get_current_user)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        suite = await request.app.state.suite_service.get_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    return templates.TemplateResponse(
        request,
        "suite.html",
        {
            "suite": suite,
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_dashboard(request: Request, run_id: str, current_user: User = Depends(get_current_user)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        run = await request.app.state.run_service.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "run": run,
        },
    )
