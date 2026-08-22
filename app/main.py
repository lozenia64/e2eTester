from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_admin import router as admin_router
from app.api.routes_anomalies import router as anomalies_router
from app.api.routes_daily import router as daily_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_healing import router as healing_router
from app.api.routes_insights import router as insights_router
from app.api.routes_otp import router as otp_router
from app.api.routes_presets import router as presets_router
from app.api.routes_runs import router as runs_router
from app.api.routes_schedules import router as schedules_router
from app.api.routes_suites import router as suites_router
from app.api.routes_systems import router as systems_router
from app.api.routes_trigger import router as trigger_router
from app.api.routes_wall import router as wall_router
from app.api.ws_runs import router as ws_runs_router
from app.api.ws_suites import router as ws_suites_router
from app.composition.container import AppContainer
from app.contexts.identity.router import router as auth_router
from app.core.logging import bind_log_context, clear_log_context
from app.core.settings import get_settings

ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    container = AppContainer.build(settings)
    container.apply_to_app_state(app)
    await container.start()
    try:
        yield
    finally:
        await container.stop()


app = FastAPI(title="E2E Tester Dashboard", lifespan=lifespan)


@app.middleware("http")
async def request_log_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    bind_log_context(
        request_id=request_id,
        http_method=request.method,
        http_path=request.url.path,
    )
    try:
        return await call_next(request)
    finally:
        clear_log_context("request_id", "http_method", "http_path")


app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS_DIR), name="artifacts")

_FAVICON_ICO = Path("app/web/static/favicon.ico")
_APPLE_TOUCH_ICON = Path("app/web/static/apple-touch-icon.png")
_APPLE_TOUCH_ICON_PRECOMPOSED = Path("app/web/static/apple-touch-icon-precomposed.png")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico() -> FileResponse:
    """브라우저가 루트로 자동 요청하는 /favicon.ico 를 인증 없이 제공한다."""
    return FileResponse(_FAVICON_ICO, media_type="image/x-icon")


@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon() -> FileResponse:
    """iOS/Safari 가 루트로 자동 요청하는 홈 화면 아이콘(180x180)을 인증 없이 제공한다."""
    return FileResponse(_APPLE_TOUCH_ICON, media_type="image/png")


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def apple_touch_icon_precomposed() -> FileResponse:
    """구형 iOS 가 요청하는 precomposed 변형 — 동일한 180x180 아이콘을 제공한다."""
    return FileResponse(_APPLE_TOUCH_ICON_PRECOMPOSED, media_type="image/png")


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(dashboard_router)
app.include_router(daily_router)
app.include_router(systems_router)
app.include_router(insights_router)
app.include_router(anomalies_router)
app.include_router(healing_router)
app.include_router(runs_router)
app.include_router(presets_router)
app.include_router(otp_router)
app.include_router(schedules_router)
app.include_router(trigger_router)
app.include_router(wall_router)
app.include_router(suites_router)
app.include_router(ws_runs_router)
app.include_router(ws_suites_router)
