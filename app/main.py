from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.auth.service import UserService
from app.storage.sqlite_user_repository import SqliteUserRepository
from app.api.routes_admin import router as admin_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_runs import router as runs_router
from app.api.routes_schedules import router as schedules_router
from app.api.routes_suites import router as suites_router
from app.api.routes_systems import router as systems_router
from app.api.ws_runs import router as ws_runs_router
from app.api.ws_suites import router as ws_suites_router
from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.events.bus import EventBus
from app.events.subscribers.email_notification import EmailNotificationSubscriber
from app.events.subscribers.failure_analysis import FailureAnalysisSubscriber
from app.execution.local_gateway import LocalExecutionGateway
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.run_service import RunService
from app.orchestrator.stats_service import StatsService
from app.orchestrator.suite_service import SuiteService
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.scheduling.scheduler import SchedulerService
from app.storage.run_input_store import InMemoryRunInputStore
from app.storage.sqlite_module_settings_repository import SqliteModuleSettingsRepository
from app.storage.sqlite_run_control_store import SqliteRunControlStore
from app.storage.sqlite_run_log_store import SqliteRunLogStore
from app.storage.sqlite_run_repository import SqliteRunRepository
from app.storage.sqlite_schedule_repository import SqliteScheduleRepository
from app.storage.sqlite_suite_repository import SqliteSuiteRepository
from app.storage.sqlite_support import DEFAULT_DB_PATH
from app.core.env_utils import load_dotenv_file, resolve_env_value


ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = ModuleRegistry()
    dotenv = load_dotenv_file()
    # 영속 저장소(SQLite): Run/Suite/예약이 서버 재시작 후에도 남는다. 경로는 E2E_DB_PATH.
    db_path = resolve_env_value("E2E_DB_PATH", dotenv) or DEFAULT_DB_PATH

    user_repository = SqliteUserRepository(db_path)
    user_service = UserService(user_repository)
    app.state.user_service = user_service
    admin_email = resolve_env_value("E2E_ADMIN_EMAIL", dotenv) or "admin@example.com"
    admin_password = resolve_env_value("E2E_ADMIN_PASSWORD", dotenv) or "admin1234"
    await user_service.seed_admin(admin_email, admin_password)

    repository = SqliteRunRepository(db_path)
    # 모듈 로그는 Run 상태 집합체와 분리된 append-only 스트림 스토어가 소유한다(핫패스
    # full-blob 쓰기 제거). Run blob 에는 로그가 담기지 않고, 읽기 시 하이드레이션된다.
    run_log_store = SqliteRunLogStore(db_path)
    # 제어 상태(취소 의도·OTP 재개 컨텍스트)는 영속(SQLite) — 재기동 후에도 권위 있게 남는다.
    # PII 입력값은 Phase 1 에서 인메모리(오늘과 동일한 휘발성). 암호화 SQLite 어댑터로 바꾸면
    # 재기동 후 rerun 까지 가능해진다(Phase 2).
    run_control_store = SqliteRunControlStore(db_path)
    run_input_store = InMemoryRunInputStore()
    artifact_manager = ArtifactManager()
    system_codes = [system.system_code for system in registry.list_systems()]

    # 실행 경계: 오케스트레이터는 이 포트 뒤의 브라우저/스레드/런타임을 모른다.
    execution_gateway = LocalExecutionGateway(artifact_manager, system_codes)

    # 도메인 이벤트 버스 + 부수 관심사 구독자(AI 실패 분석·종료 메일).
    event_bus = EventBus()
    failure_analyzer = GeminiFailureAnalyzer.from_env()
    FailureAnalysisSubscriber(failure_analyzer, repository, registry).register(event_bus)
    email_notifier = RunCompletionEmailNotifier.from_env(system_codes)
    if email_notifier is not None:
        EmailNotificationSubscriber(email_notifier).register(event_bus)

    run_service = RunService(
        registry=registry,
        repository=repository,
        log_store=run_log_store,
        execution_gateway=execution_gateway,
        event_bus=event_bus,
        control_store=run_control_store,
        input_store=run_input_store,
        artifact_manager=artifact_manager,
    )
    module_settings_repository = SqliteModuleSettingsRepository(db_path)
    app.state.module_settings_repo = module_settings_repository

    suite_repository = SqliteSuiteRepository(db_path)
    schedule_repository = SqliteScheduleRepository(db_path)
    suite_service = SuiteService(
        registry=registry,
        run_service=run_service,
        repository=suite_repository,
        event_bus=event_bus,
    )
    app.state.run_service = run_service
    app.state.suite_service = suite_service
    app.state.stats_service = StatsService(
        run_repo=repository,
        suite_repo=suite_repository,
        registry=registry,
        module_settings_repo=module_settings_repository,
        user_service=user_service,
        schedule_repo=schedule_repository,
    )

    # 재기동 시 이어받을 수 없는(브라우저 세션이 사라진) 진행 중 Run/Suite 를 CANCELLED 로 봉인.
    interrupted_runs = await run_service.reconcile_interrupted_runs()
    interrupted_suites = await suite_service.reconcile_interrupted_suites()
    if interrupted_runs or interrupted_suites:
        print(
            f"[startup] 재기동으로 중단된 Run {interrupted_runs}건 · "
            f"Suite {interrupted_suites}건을 CANCELLED 로 정리했습니다."
        )

    scheduler = SchedulerService(
        run_service=run_service,
        suite_service=suite_service,
        repository=schedule_repository,
    )
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
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(dashboard_router)
app.include_router(systems_router)
app.include_router(runs_router)
app.include_router(schedules_router)
app.include_router(suites_router)
app.include_router(ws_runs_router)
app.include_router(ws_suites_router)
