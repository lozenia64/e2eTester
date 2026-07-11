from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai.failure_analyzer import GeminiFailureAnalyzer
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
from app.api.ws_runs import router as ws_runs_router
from app.api.ws_suites import router as ws_suites_router
from app.auth.router import router as auth_router
from app.auth.service import UserService
from app.core.logging import bind_log_context, clear_log_context, configure_logging, get_logger
from app.core.settings import get_settings
from app.events.bus import EventBus
from app.events.subscribers.email_notification import EmailNotificationSubscriber
from app.events.subscribers.failure_analysis import FailureAnalysisSubscriber
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.relay import OutboxRelay
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.local_gateway import LocalExecutionGateway
from app.execution.redis_job_queue import RedisJobQueue
from app.execution.redis_session_registry import RedisSessionRegistry
from app.execution.remote_gateway import RemoteExecutionGateway
from app.execution.run_queue import RunExecutionQueue
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.healing.engine import SelfHealingEngine
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.healing_service import HealingService
from app.orchestrator.insights_service import InsightsService
from app.orchestrator.ops_service import OpsService
from app.orchestrator.preset_service import PresetService
from app.orchestrator.run_service import RunService
from app.orchestrator.stats_service import StatsService
from app.orchestrator.suite_service import SuiteService
from app.projections.handlers import ProjectionHandlers
from app.realtime.adapter import RealtimeNotificationAdapter
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.scheduling.run_retention import RunRetentionScheduler, RunRetentionService
from app.scheduling.scheduler import SchedulerService
from app.storage.encrypted_run_input_store import EncryptedSqliteRunInputStore
from app.storage.encrypted_suite_input_store import EncryptedSqliteSuiteInputStore
from app.storage.run_history_backfill import backfill_run_history_index
from app.storage.sqlite_anomaly_handling_store import SqliteAnomalyHandlingStore
from app.storage.sqlite_healing_stores import (
    SqliteHealingEventStore,
    SqliteHealingPatchStore,
    SqliteHealingPolicyReader,
    SqliteHealingPolicyStore,
)
from app.storage.sqlite_module_settings_repository import SqliteModuleSettingsRepository
from app.storage.sqlite_preset_repository import SqlitePresetRepository
from app.storage.sqlite_run_control_store import SqliteRunControlStore
from app.storage.sqlite_run_history_query import SqliteRunHistoryQuery
from app.storage.sqlite_run_log_store import SqliteRunLogStore
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_schedule_repository import SqliteScheduleRepository
from app.storage.sqlite_suite_control_store import SqliteSuiteControlStore
from app.storage.sqlite_suite_repository import SqliteSuiteRepository
from app.storage.sqlite_support import DEFAULT_DB_PATH
from app.storage.sqlite_user_repository import SqliteUserRepository

logger = get_logger(__name__)


ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)
    app.state.settings = settings
    logger.info(
        "애플리케이션 시작",
        log_event="startup.begin",
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    registry = ModuleRegistry()
    db_path = settings.db_path or DEFAULT_DB_PATH

    user_repository = SqliteUserRepository(db_path)
    user_service = UserService(user_repository)
    app.state.user_service = user_service
    await user_service.seed_admin(settings.admin_email, settings.admin_password.get_secret_value())

    es_db = SqliteDatabase(db_path)
    await ensure_schema(es_db)
    run_write_repo = SqliteRunWriteRepository(es_db)
    await backfill_run_history_index(es_db, run_write_repo)
    run_history_query = SqliteRunHistoryQuery(es_db, run_write_repo)
    realtime = RealtimeNotificationAdapter()
    # 모듈 로그는 Run 상태 집합체와 분리된 append-only 스트림 스토어가 소유한다(핫패스
    # full-blob 쓰기 제거). Run blob 에는 로그가 담기지 않고, 읽기 시 하이드레이션된다.
    run_log_store = SqliteRunLogStore(db_path)
    # 제어 상태(취소 의도·OTP 재개 컨텍스트)는 영속(SQLite) — 재기동 후에도 권위 있게 남는다.
    run_control_store = SqliteRunControlStore(db_path)
    encryption_secret = settings.jwt_secret.get_secret_value()
    run_input_store = EncryptedSqliteRunInputStore(es_db, encryption_secret)
    artifact_manager = ArtifactManager()
    system_codes = [system.system_code for system in registry.list_systems()]

    # 감독되는 실행 작업 큐: 로컬 모드는 in-process, 원격 모드는 Redis 브로커(API 생산자).
    session_registry: RedisSessionRegistry | None = None
    if settings.execution_mode == "remote":
        session_registry = RedisSessionRegistry(settings.redis_url, settings.session_lease_ttl)
        run_queue = RedisJobQueue(settings.redis_url)
    else:
        run_queue = RunExecutionQueue(worker_count=settings.run_concurrency)

    # 자가 치유 센터: 로컬 모드는 API 실행 스레드, 원격 모드는 워커에서만 동작한다.
    healing_engine = None
    if settings.execution_mode == "local":
        healing_engine = SelfHealingEngine(SqliteHealingPolicyReader(db_path))
    healing_service = HealingService(
        event_store=SqliteHealingEventStore(db_path),
        policy_store=SqliteHealingPolicyStore(db_path),
        patch_store=SqliteHealingPatchStore(db_path),
        registry=registry,
    )
    app.state.healing_service = healing_service

    # 실행 경계: 로컬=LocalExecutionGateway, 원격=RemoteExecutionGateway(워커 HTTP).
    if settings.execution_mode == "remote":
        gateways = [
            RemoteExecutionGateway(settings.worker_base_url, session_registry),
            SimulatedExecutionGateway(),
        ]
    else:
        gateways = [
            LocalExecutionGateway(artifact_manager, system_codes, healing_engine=healing_engine),
            SimulatedExecutionGateway(),
        ]
    execution_gateway = CompositeExecutionGateway(gateways)

    # 도메인 이벤트 버스 + 부수 관심사 구독자(AI 실패 분석·종료 메일).
    event_bus = EventBus()
    failure_analyzer = GeminiFailureAnalyzer.from_env()
    FailureAnalysisSubscriber(failure_analyzer, run_write_repo, realtime, registry).register(
        event_bus
    )
    EmailNotificationSubscriber(system_codes).register(event_bus)
    email_status = RunCompletionEmailNotifier.inspect_env_status(system_codes)
    logger.info(
        "메일 알림 상태",
        log_event="startup.email_status",
        title=email_status.title,
        message=email_status.message,
    )

    run_service = RunService(
        registry=registry,
        write_repo=run_write_repo,
        history_query=run_history_query,
        realtime=realtime,
        log_store=run_log_store,
        execution_gateway=execution_gateway,
        event_bus=event_bus,
        control_store=run_control_store,
        input_store=run_input_store,
        run_queue=run_queue,
        artifact_manager=artifact_manager,
        healing_recorder=healing_service,
        session_registry=session_registry,
    )
    if isinstance(run_queue, RunExecutionQueue):
        run_queue._run_job_handler = run_service.dispatch_run_job  # noqa: SLF001
    module_settings_repository = SqliteModuleSettingsRepository(db_path)
    app.state.module_settings_repo = module_settings_repository

    # 인증 프리셋: 사용자별 인증 수단·정보 저장 세트. 인증 정보(PII 가능)를 의도적으로 영속하며
    # 저장 시 RunService 로 검증한다(실행 가능한 조합만 저장).
    preset_repository = SqlitePresetRepository(db_path)
    app.state.preset_service = PresetService(
        repository=preset_repository,
        run_service=run_service,
    )

    suite_repository = SqliteSuiteRepository(db_path)
    schedule_repository = SqliteScheduleRepository(db_path)
    # Suite 취소 의도는 영속(SQLite), 시스템별 입력값은 인메모리(Phase 1, RunInputStore 와 동일).
    suite_control_store = SqliteSuiteControlStore(db_path)
    suite_input_store = EncryptedSqliteSuiteInputStore(es_db, encryption_secret)
    suite_service = SuiteService(
        registry=registry,
        # 사가는 구체 RunService 가 아니라 명령 포트(RunCommandPort)에만 의존한다 — RunService 는
        # 그 포트를 구조적으로 만족하므로 그대로 주입한다(배선은 컴포지션 루트가 독점).
        run_commands=run_service,
        repository=suite_repository,
        event_bus=event_bus,
        cancel_store=suite_control_store,
        input_store=suite_input_store,
    )
    # Suite Saga 가 의존하는 도메인 이벤트(RunFinished/RunWaitingInput/RunResumed) 구독 등록.
    suite_service.register(event_bus)
    app.state.run_service = run_service
    app.state.suite_service = suite_service
    app.state.run_queue = run_queue
    # API 의존성 주입(app/api/dependencies.py)이 꺼내 쓰는 공유 싱글턴들. 라우트가 서비스의
    # 비공개 속성(._registry/._repository)을 들춰보지 않고 포트/레지스트리를 직접 주입받게 한다.
    app.state.registry = registry
    app.state.suite_repository = suite_repository
    app.state.schedule_repository = schedule_repository
    # SMS 중계 인바운드 OTP(POST /api/otp/inbound): 기기 토큰 미설정 시 기능 비활성(엔드포인트가
    # 503). SMS 원문 파싱 정규식은 회사 SMS 형식에 맞춰 재정의 가능(미설정 시 라우트 기본값).
    app.state.otp_relay_token = settings.otp_relay_token_str()
    app.state.otp_relay_regex = settings.otp_relay_regex
    app.state.stats_service = StatsService(
        run_repo=run_history_query,
        suite_repo=suite_repository,
        registry=registry,
        module_settings_repo=module_settings_repository,
        user_service=user_service,
        schedule_repo=schedule_repository,
    )

    # 운영 인텔리전스: 이상징후 인박스(처리상태 SQLite 영속) + 시스템 인사이트(헬스/타임라인/딥다이브).
    # 집계는 순수 빌더가, I/O 는 서비스가 담당한다(StatsService 와 같은 얇은 인터프리터 패턴).
    anomaly_handling_store = SqliteAnomalyHandlingStore(db_path)
    app.state.anomaly_store = anomaly_handling_store
    app.state.insights_service = InsightsService(
        run_repo=run_history_query,
        registry=registry,
        anomaly_store=anomaly_handling_store,
        user_service=user_service,
        suite_repo=suite_repository,
        schedule_repo=schedule_repository,
    )

    # 재기동 시 이어받을 수 없는(브라우저 세션이 사라진) 진행 중 Run/Suite 를 CANCELLED 로 봉인.
    interrupted_runs = await run_service.reconcile_interrupted_runs()
    interrupted_suites = await suite_service.reconcile_interrupted_suites()
    if interrupted_runs or interrupted_suites:
        logger.info(
            "재기동으로 중단된 작업 정리",
            log_event="startup.reconcile_interrupted",
            interrupted_runs=interrupted_runs,
            interrupted_suites=interrupted_suites,
        )

    # 감독되는 작업 큐의 워커를 띄운다(reconcile 이후 — reconcile 은 작업을 제출하지 않는다).
    run_queue.start()
    logger.info(
        "실행 작업 큐 시작",
        log_event="startup.run_queue_started",
        worker_count=getattr(run_queue, "worker_count", 0),
        execution_mode=settings.execution_mode,
    )

    scheduler = SchedulerService(
        run_commands=run_service,
        suite_service=suite_service,
        repository=schedule_repository,
    )
    app.state.schedule_service = scheduler
    app.state.ops_service = OpsService(
        settings=settings,
        run_repo=run_history_query,
        suite_repo=suite_repository,
        schedule_repo=schedule_repository,
        run_queue=run_queue,
        scheduler=scheduler,
    )
    scheduler_task = asyncio.create_task(scheduler.run_forever())
    outbox_relay = OutboxRelay(
        SqliteOutbox(es_db),
        ProjectionHandlers(es_db, run_write_repo),
        run_write_repo,
        event_bus,
        log_store=run_log_store,
    )
    outbox_relay.start()
    retention_scheduler = RunRetentionScheduler.from_env(RunRetentionService(run_service))
    retention_task: asyncio.Task | None = None
    if retention_scheduler is not None:
        retention_task = asyncio.create_task(retention_scheduler.run_forever())
    try:
        yield
    finally:
        await outbox_relay.stop()
        scheduler.stop()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        if retention_scheduler is not None:
            retention_scheduler.stop()
        if retention_task is not None:
            retention_task.cancel()
            try:
                await retention_task
            except asyncio.CancelledError:
                pass
        await run_queue.stop()
        if session_registry is not None:
            await session_registry.close()


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
app.include_router(suites_router)
app.include_router(ws_runs_router)
app.include_router(ws_suites_router)
