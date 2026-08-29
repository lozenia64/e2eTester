from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.api.dependencies import (
    get_healing_service,
    get_run_queries,
    get_run_service,
    get_run_summary_query,
    get_suite_service,
)
from app.contexts.identity.dependencies import get_current_user, require_admin
from app.contexts.identity.models import User
from app.contexts.suite.views.view import SuiteView, filter_suite_for_user
from app.core.status_view import status_badge_view, status_options, tone_glyph
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.web.asset_manifest import TEMPLATE_SEARCH_DIRS, asset_css, asset_js

if TYPE_CHECKING:
    from app.contexts.healing.service import HealingService
    from app.contexts.run.application.service import RunService
    from app.contexts.run.contracts.ports import RunSummaryQueryPort
    from app.contexts.suite.application.service import SuiteService
    from app.orchestrator.queries import RunQueries

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATE_SEARCH_DIRS)
templates.env.globals["asset_js"] = asset_js
templates.env.globals["asset_css"] = asset_css
templates.env.globals["status_badge_view"] = status_badge_view
templates.env.globals["status_options"] = status_options
templates.env.globals["tone_glyph"] = tone_glyph


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """일간 점검 현황 대시보드(로그인 후 첫 화면). HTMX fragment + JSON API 로 데이터 로드."""
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


@router.get("/admin/runs", response_class=HTMLResponse)
async def admin_runs(request: Request, current_user: User = Depends(require_admin)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "admin/runs.html",
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
    run_summary_query: RunSummaryQueryPort = Depends(get_run_summary_query),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        suite = await suite_service.get_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    suite = filter_suite_for_user(suite, current_user)
    try:
        # ETA baseline. 실행 중 변하지 않으므로 1회만 주입한다(설계 §3.3).
        step_baselines = await run_summary_query.avg_duration_ms_by_system()
    except Exception:  # noqa: BLE001 — baseline 조회가 실패해도 화면은 떠야 한다(ETA 만 사라짐)
        step_baselines = {}
    # 최초 렌더도 SuiteView 를 거친다 — expanded_step_order 등 파생 필드를 WS 페이로드와
    # 같은 출처에서 보게 하기 위함(설계 D8).
    return templates.TemplateResponse(
        request,
        "suite.html",
        {
            "suite": SuiteView.from_suite(suite),
            "current_user": current_user,
            "step_baselines": step_baselines,
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
        return RedirectResponse(url="/admin/runs", status_code=302)
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


@router.get("/presets", response_class=HTMLResponse)
async def presets_center(
    request: Request,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """인증 프리셋 관리 — 저장된 내 점검 세트 조회·수정·삭제. 관리자도 접근 가능."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    systems = run_service.list_systems()
    if current_user.role != "admin":
        allowed = set(current_user.allowed_system_codes)
        systems = [s for s in systems if s.system_code in allowed]
    systems = sorted(systems, key=lambda s: (s.display_order, s.name))
    systems_payload = {system.system_code: system.model_dump(mode="json") for system in systems}
    return templates.TemplateResponse(
        request,
        "presets.html",
        {
            "current_user": current_user,
            "systems_payload": systems_payload,
        },
    )


@router.get("/schedules", response_class=HTMLResponse)
async def schedules_center(
    request: Request,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """예약 점검 관리 센터(무인 점검 관제실) — 관제 보드/목록/캘린더/상세 드로어.

    관리자도 리다이렉트 없이 접근한다(이상징후 인박스와 같은 규칙). 수정 폼 렌더링을
    위해 접근 가능한 시스템의 manifest(run_form·모듈 목록)를 함께 내려준다.
    """
    if isinstance(current_user, RedirectResponse):
        return current_user
    systems = run_service.list_systems()
    if current_user.role != "admin":
        allowed = set(current_user.allowed_system_codes)
        systems = [s for s in systems if s.system_code in allowed]
    systems = sorted(systems, key=lambda s: (s.display_order, s.name))
    systems_payload = {system.system_code: system.model_dump(mode="json") for system in systems}
    return templates.TemplateResponse(
        request,
        "schedules.html",
        {
            "current_user": current_user,
            "systems_payload": systems_payload,
        },
    )


@router.get("/self-healing", response_class=HTMLResponse)
async def self_healing_center(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """자가 치유 센터(복구 콘솔/승인 대기 패치/셀렉터 내구성 맵 3탭). 관리자도 접근 가능."""
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "self_healing.html",
        {"current_user": current_user},
    )


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
    run_queries: RunQueries = Depends(get_run_queries),
    healing: HealingService = Depends(get_healing_service),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        run = await run_queries.get_run_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    healing_payload = await healing.list_events(allowed_system_codes=allowed, run_id=run_id)
    healing_by_module: dict[str, list[dict]] = {}
    for item in healing_payload["items"]:
        # NO_CANDIDATE 는 복구되지 않은 시도다 — 화면에 표시하지 않는다(설계 §3.5).
        if item["action"] == "NO_CANDIDATE":
            continue
        healing_by_module.setdefault(item["module_id"], []).append(item)

    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "run": run,
            "current_user": current_user,
            "healing_by_module": healing_by_module,
        },
    )
