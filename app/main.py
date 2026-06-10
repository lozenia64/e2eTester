from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_runs import router as runs_router
from app.api.routes_systems import router as systems_router
from app.api.ws_runs import router as ws_runs_router
from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.run_service import RunService
from app.registry.loader import ModuleRegistry
from app.storage.run_repository import InMemoryRunRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = ModuleRegistry()
    repository = InMemoryRunRepository()
    failure_analyzer = GeminiFailureAnalyzer.from_env()
    system_codes = [system.system_code for system in registry.list_systems()]
    email_notifier = RunCompletionEmailNotifier.from_env(system_codes)
    app.state.run_service = RunService(
        registry=registry,
        repository=repository,
        failure_analyzer=failure_analyzer,
        run_completion_notifier=email_notifier,
    )
    yield


app = FastAPI(title="E2E Tester Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.mount("/artifacts", StaticFiles(directory="artifacts"), name="artifacts")
app.include_router(dashboard_router)
app.include_router(systems_router)
app.include_router(runs_router)
app.include_router(ws_runs_router)
