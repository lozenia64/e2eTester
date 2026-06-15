from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_runs import router as runs_router
from app.api.routes_schedules import router as schedules_router
from app.api.routes_suites import router as suites_router
from app.api.routes_systems import router as systems_router
from app.api.ws_runs import router as ws_runs_router
from app.api.ws_suites import router as ws_suites_router
from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.run_service import RunService
from app.orchestrator.suite_service import SuiteService
from app.registry.loader import ModuleRegistry
from app.scheduling.scheduler import SchedulerService
from app.storage.run_repository import InMemoryRunRepository
from app.storage.schedule_repository import InMemoryScheduleRepository
from app.storage.suite_repository import InMemorySuiteRepository


ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = ModuleRegistry()
    repository = InMemoryRunRepository()
    failure_analyzer = GeminiFailureAnalyzer.from_env()
    system_codes = [system.system_code for system in registry.list_systems()]
    email_notifier = RunCompletionEmailNotifier.from_env(system_codes)
    run_service = RunService(
        registry=registry,
        repository=repository,
        failure_analyzer=failure_analyzer,
        run_completion_notifier=email_notifier,
    )
    suite_repository = InMemorySuiteRepository()
    suite_service = SuiteService(
        registry=registry,
        run_service=run_service,
        repository=suite_repository,
    )
    app.state.run_service = run_service
    app.state.suite_service = suite_service

    scheduler = SchedulerService(run_service=run_service, repository=InMemoryScheduleRepository())
    app.state.schedule_service = scheduler
    scheduler_task = asyncio.create_task(scheduler.run_forever())
    try:
        yield
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="E2E Tester Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS_DIR), name="artifacts")
app.include_router(dashboard_router)
app.include_router(systems_router)
app.include_router(runs_router)
app.include_router(schedules_router)
app.include_router(suites_router)
app.include_router(ws_runs_router)
app.include_router(ws_suites_router)
