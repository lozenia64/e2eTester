from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    run_service = request.app.state.run_service
    systems = run_service.list_systems()
    runs = await run_service.list_runs()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "systems": systems,
            "runs": runs[:8],
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_dashboard(request: Request, run_id: str):
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
