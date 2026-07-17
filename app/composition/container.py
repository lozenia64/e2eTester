"""애플리케이션 컨테이너 — FastAPI ``main`` 에서 분리된 의존성 배선·수명 주기."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.contexts.healing.composition import compose_healing
from app.contexts.healing.engine import SelfHealingEngine
from app.contexts.healing.service import HealingService
from app.contexts.identity.composition import compose_identity
from app.contexts.identity.infrastructure.sqlite_user_repository import SqliteUserRepository
from app.contexts.identity.service import UserService
from app.contexts.insights.application.insights_service import InsightsService
from app.contexts.insights.application.ops_service import OpsService
from app.contexts.insights.application.stats_service import StatsService
from app.contexts.insights.composition import compose_insights
from app.contexts.insights.infrastructure.sqlite_anomaly_handling_store import (
    SqliteAnomalyHandlingStore,
)
from app.contexts.insights.infrastructure.sqlite_anomaly_inbox_query import SqliteAnomalyInboxQuery
from app.contexts.insights.infrastructure.sqlite_daily_status_query import SqliteDailyStatusQuery
from app.contexts.insights.infrastructure.sqlite_module_settings_repository import (
    SqliteModuleSettingsRepository,
)
from app.contexts.insights.infrastructure.sqlite_stats_query import SqliteStatsQuery
from app.contexts.preset.application.service import PresetService
from app.contexts.preset.composition import compose_preset_repository, compose_preset_service
from app.contexts.preset.infrastructure.sqlite_preset_repository import SqlitePresetRepository
from app.contexts.run.application.service import RunService
from app.contexts.run.composition import compose_run_repositories, compose_run_service
from app.contexts.scheduling.composition import compose_retention_scheduler, compose_scheduler
from app.contexts.scheduling.infrastructure.sqlite_schedule_repository import (
    SqliteScheduleRepository,
)
from app.contexts.scheduling.run_retention import RunRetentionScheduler
from app.contexts.scheduling.scheduler import SchedulerService
from app.contexts.suite.application.service import SuiteService
from app.contexts.suite.composition import compose_suite_repositories, compose_suite_service
from app.core.logging import configure_logging, get_logger
from app.core.settings import E2ESettings
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.composition import compose_execution_gateway, compose_execution_runtime
from app.execution.profile_queue import ProfilePartitionedRunQueue
from app.execution.redis_session_registry import RedisSessionRegistry
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.queries import AdminDashboardQueries, DailyDashboardQueries, RunQueries
from app.platform.artifact_manager import ArtifactManager
from app.platform.eventing.bus import EventBus, RunFinished
from app.platform.eventing.composition import compose_event_bus
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.relay import OutboxRelay
from app.platform.eventing.snapshot_rebuild import (
    rebuild_missing_run_snapshots,
    repair_incomplete_run_snapshots,
)
from app.platform.eventing.subscribers.email_notification import EmailNotificationSubscriber
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.composition import compose_realtime, should_use_redis_fanout
from app.realtime.projector import RealtimeProjector
from app.realtime.redis_fanout import RedisRealtimeFanOut
from app.registry.loader import ModuleRegistry
from app.storage.encrypted_run_input_store import EncryptedSqliteRunInputStore
from app.storage.encrypted_suite_input_store import EncryptedSqliteSuiteInputStore
from app.storage.legacy_runs_projection_backfill import backfill_from_legacy_runs
from app.storage.module_history_backfill import backfill_module_history_index
from app.storage.run_history_backfill import backfill_run_history_index
from app.storage.sqlite_email_notification_dedup import SqliteEmailNotificationDedupStore
from app.storage.sqlite_module_history_query import SqliteModuleHistoryQuery
from app.storage.sqlite_run_control_store import SqliteRunControlStore
from app.storage.sqlite_run_log_store import SqliteRunLogStore
from app.storage.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_session_checkpoint_store import SqliteSessionCheckpointStore
from app.storage.sqlite_suite_control_store import SqliteSuiteControlStore
from app.storage.sqlite_suite_repository import SqliteSuiteRepository
from app.storage.sqlite_suite_summary_query import SqliteSuiteSummaryQuery
from app.storage.sqlite_suite_write_repository import SqliteSuiteWriteRepository
from app.storage.sqlite_support import DEFAULT_DB_PATH

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


@runtime_checkable
class Startable(Protocol):
    def start(self) -> None: ...


@runtime_checkable
class Stoppable(Protocol):
    async def stop(self) -> None: ...


@dataclass
class AppContainer:
    """애플리케이션 싱글턴 그래프 — ``build`` 로 배선, ``start``/``stop`` 으로 수명 주기."""

    settings: E2ESettings

    registry: ModuleRegistry = field(init=False)
    db_path: str = field(init=False)
    es_db: SqliteDatabase = field(init=False)
    user_repository: SqliteUserRepository = field(init=False)
    user_service: UserService = field(init=False)
    run_write_repo: SqliteRunWriteRepository = field(init=False)
    run_summary_query: SqliteRunSummaryQuery = field(init=False)
    module_history_query: SqliteModuleHistoryQuery = field(init=False)
    suite_summary_query: SqliteSuiteSummaryQuery = field(init=False)
    run_log_store: SqliteRunLogStore = field(init=False)
    run_control_store: SqliteRunControlStore = field(init=False)
    run_input_store: EncryptedSqliteRunInputStore = field(init=False)
    session_checkpoint_store: SqliteSessionCheckpointStore = field(init=False)
    suite_write_repo: SqliteSuiteWriteRepository = field(init=False)
    suite_repository: SqliteSuiteRepository = field(init=False)
    schedule_repository: SqliteScheduleRepository = field(init=False)
    suite_control_store: SqliteSuiteControlStore = field(init=False)
    suite_input_store: EncryptedSqliteSuiteInputStore = field(init=False)
    preset_repository: SqlitePresetRepository = field(init=False)
    module_settings_repository: SqliteModuleSettingsRepository = field(init=False)
    anomaly_handling_store: SqliteAnomalyHandlingStore = field(init=False)
    anomaly_inbox_query: SqliteAnomalyInboxQuery = field(init=False)
    daily_status_query: SqliteDailyStatusQuery = field(init=False)
    stats_query: SqliteStatsQuery = field(init=False)

    realtime: RealtimeNotificationAdapter = field(init=False)
    suite_realtime: SuiteRealtimeNotificationAdapter = field(init=False)
    redis_fanout: RedisRealtimeFanOut | None = field(init=False, default=None)

    artifact_manager: ArtifactManager = field(init=False)
    system_codes: list[str] = field(init=False)
    session_registry: RedisSessionRegistry | None = field(init=False, default=None)
    run_queue: ProfilePartitionedRunQueue = field(init=False)
    healing_engine: SelfHealingEngine | None = field(init=False, default=None)
    healing_service: HealingService = field(init=False)
    execution_gateway: CompositeExecutionGateway = field(init=False)

    event_bus: EventBus = field(init=False)
    email_dedup_store: SqliteEmailNotificationDedupStore = field(init=False)
    email_subscriber: EmailNotificationSubscriber = field(init=False)
    run_service: RunService = field(init=False)
    run_queries: RunQueries = field(init=False)
    daily_queries: DailyDashboardQueries = field(init=False)
    admin_dashboard_queries: AdminDashboardQueries = field(init=False)
    suite_service: SuiteService = field(init=False)
    preset_service: PresetService = field(init=False)

    stats_service: StatsService = field(init=False)
    insights_service: InsightsService = field(init=False)
    ops_service: OpsService = field(init=False)

    scheduler: SchedulerService = field(init=False)
    outbox_relay: OutboxRelay = field(init=False)
    retention_scheduler: RunRetentionScheduler | None = field(init=False, default=None)
    _scheduler_task: asyncio.Task[None] | None = field(init=False, default=None, repr=False)
    _retention_task: asyncio.Task[None] | None = field(init=False, default=None, repr=False)

    @classmethod
    def build(cls, settings: E2ESettings) -> AppContainer:
        container = cls(settings=settings)
        container.wire_persistence()
        container.wire_realtime()
        container.wire_execution()
        container.wire_orchestration()
        container.wire_read_models()
        return container

    def wire_persistence(self) -> None:
        self.registry = ModuleRegistry()
        self.db_path = self.settings.db_path or DEFAULT_DB_PATH
        self.es_db = SqliteDatabase(self.db_path)

        identity = compose_identity(self.db_path)
        self.user_repository = identity.user_repository
        self.user_service = identity.user_service

        encryption_secret = self.settings.jwt_secret.get_secret_value()
        run_repos = compose_run_repositories(self.es_db, self.db_path, encryption_secret)
        self.run_write_repo = run_repos.run_write_repo
        self.run_summary_query = run_repos.run_summary_query
        self.module_history_query = run_repos.module_history_query
        self.suite_summary_query = run_repos.suite_summary_query
        self.run_log_store = run_repos.run_log_store
        self.run_control_store = run_repos.run_control_store
        self.run_input_store = run_repos.run_input_store
        self.session_checkpoint_store = run_repos.session_checkpoint_store

        suite_repos = compose_suite_repositories(self.es_db, self.db_path, encryption_secret)
        self.suite_write_repo = suite_repos.suite_write_repo
        self.suite_repository = suite_repos.suite_repository
        self.schedule_repository = suite_repos.schedule_repository
        self.suite_control_store = suite_repos.suite_control_store
        self.suite_input_store = suite_repos.suite_input_store

        self.preset_repository = compose_preset_repository(self.db_path)
        self.module_settings_repository = SqliteModuleSettingsRepository(self.db_path)
        self.anomaly_handling_store = SqliteAnomalyHandlingStore(self.db_path)
        self.anomaly_inbox_query = SqliteAnomalyInboxQuery(self.es_db)
        self.daily_status_query = SqliteDailyStatusQuery(self.es_db)
        self.stats_query = SqliteStatsQuery(self.es_db)

    def wire_realtime(self) -> None:
        realtime = compose_realtime(self.settings)
        self.realtime = realtime.realtime
        self.suite_realtime = realtime.suite_realtime
        self.redis_fanout = realtime.redis_fanout

    def _should_use_redis_fanout(self) -> bool:
        return should_use_redis_fanout(self.settings)

    def wire_execution(self) -> None:
        runtime = compose_execution_runtime(self.registry, self.settings)
        self.artifact_manager = runtime.artifact_manager
        self.system_codes = runtime.system_codes
        self.session_registry = runtime.session_registry
        self.run_queue = runtime.run_queue

        self.healing_engine = None  # 런타임 치유 엔진은 워커 프로세스가 소유(API 는 기록/패치만).
        healing = compose_healing(self.db_path, self.registry)
        self.healing_service = healing.healing_service

        gateway = compose_execution_gateway(self.settings, self.session_registry)
        self.execution_gateway = gateway.execution_gateway

    def wire_orchestration(self) -> None:
        eventing = compose_event_bus(
            registry=self.registry,
            run_write_repo=self.run_write_repo,
            system_codes=self.system_codes,
            es_db=self.es_db,
        )
        self.event_bus = eventing.event_bus
        self.email_dedup_store = eventing.email_dedup_store
        self.email_subscriber = eventing.email_subscriber

        run_svc = compose_run_service(
            registry=self.registry,
            run_write_repo=self.run_write_repo,
            run_summary_query=self.run_summary_query,
            realtime=self.realtime,
            run_log_store=self.run_log_store,
            execution_gateway=self.execution_gateway,
            event_bus=self.event_bus,
            run_control_store=self.run_control_store,
            run_input_store=self.run_input_store,
            run_queue=self.run_queue,
            artifact_manager=self.artifact_manager,
            healing_recorder=self.healing_service,
            session_registry=self.session_registry,
            session_checkpoint_store=self.session_checkpoint_store,
        )
        self.run_service = run_svc.run_service

        self.run_queries = RunQueries(
            self.run_summary_query, self.run_write_repo, self.run_log_store
        )
        self.daily_queries = DailyDashboardQueries(self.registry, self.daily_status_query)
        self.admin_dashboard_queries = AdminDashboardQueries(self.registry, self.run_summary_query)

        self.preset_service = compose_preset_service(self.preset_repository, self.run_service)

        suite_svc = compose_suite_service(
            registry=self.registry,
            run_commands=self.run_service,
            suite_write_repo=self.suite_write_repo,
            suite_repository=self.suite_repository,
            suite_realtime=self.suite_realtime,
            event_bus=self.event_bus,
            suite_control_store=self.suite_control_store,
            suite_input_store=self.suite_input_store,
            suite_summary_query=self.suite_summary_query,
        )
        self.suite_service = suite_svc.suite_service

        self.scheduler = compose_scheduler(
            self.run_service,
            self.suite_service,
            self.schedule_repository,
            self.run_queries,
        )
        realtime_projector = RealtimeProjector(
            self.realtime,
            self.suite_realtime,
            run_loader=self.run_write_repo.get_run,
            suite_loader=self.suite_write_repo.get_suite,
            log_store=self.run_log_store,
        )
        self.outbox_relay = OutboxRelay(
            SqliteOutbox(self.es_db),
            ProjectionHandlers(self.es_db, self.run_write_repo),
            self.run_write_repo,
            self.event_bus,
            realtime_projector,
            log_store=self.run_log_store,
            suite_finished_loader=self.suite_service.load_suite_finished_payload,
        )
        self.retention_scheduler = compose_retention_scheduler(self.run_service)

    def wire_read_models(self) -> None:
        insights = compose_insights(
            stats_query=self.stats_query,
            suite_summary_query=self.suite_summary_query,
            registry=self.registry,
            module_settings_repo=self.module_settings_repository,
            user_service=self.user_service,
            schedule_repo=self.schedule_repository,
            run_summary_query=self.run_summary_query,
            module_history_query=self.module_history_query,
            anomaly_store=self.anomaly_handling_store,
            anomaly_query=self.anomaly_inbox_query,
            settings=self.settings,
            run_queue=self.run_queue,
            scheduler=self.scheduler,
        )
        self.stats_service = insights.stats_service
        self.insights_service = insights.insights_service
        self.ops_service = insights.ops_service

    def apply_to_app_state(self, app: FastAPI) -> None:
        app.state.settings = self.settings
        app.state.user_service = self.user_service
        app.state.healing_service = self.healing_service
        app.state.module_settings_repo = self.module_settings_repository
        app.state.preset_service = self.preset_service
        app.state.run_service = self.run_service
        app.state.run_queries = self.run_queries
        app.state.daily_queries = self.daily_queries
        app.state.admin_dashboard_queries = self.admin_dashboard_queries
        app.state.suite_summary_query = self.suite_summary_query
        app.state.suite_service = self.suite_service
        app.state.run_queue = self.run_queue
        app.state.registry = self.registry
        app.state.suite_repository = self.suite_repository
        app.state.schedule_repository = self.schedule_repository
        app.state.otp_relay_token = self.settings.otp_relay_token_str()
        app.state.otp_relay_regex = self.settings.otp_relay_regex
        app.state.stats_service = self.stats_service
        app.state.anomaly_store = self.anomaly_handling_store
        app.state.insights_service = self.insights_service
        app.state.schedule_service = self.scheduler
        app.state.ops_service = self.ops_service

    async def start(self) -> None:
        configure_logging(log_level=self.settings.log_level, log_format=self.settings.log_format)
        logger.info(
            "애플리케이션 시작",
            log_event="startup.begin",
            log_level=self.settings.log_level,
            log_format=self.settings.log_format,
        )

        await ensure_schema(self.es_db)
        rebuilt = await rebuild_missing_run_snapshots(self.es_db)
        if rebuilt:
            logger.info(
                "누락 Run 스냅샷 backfill",
                log_event="startup.snapshot_backfill",
                count=rebuilt,
            )
        repaired = await repair_incomplete_run_snapshots(self.es_db)
        if repaired:
            logger.info(
                "불완전 Run 스냅샷 수리",
                log_event="startup.snapshot_repair",
                count=repaired,
            )
        await backfill_run_history_index(self.es_db, self.run_write_repo)
        module_rows = await backfill_module_history_index(self.es_db, self.run_write_repo)
        legacy = await backfill_from_legacy_runs(self.es_db, self.run_write_repo)
        if module_rows:
            logger.info(
                "누락 모듈 이력 backfill",
                log_event="startup.module_history_backfill",
                count=module_rows,
            )
        if legacy.module_rows or legacy.run_rows:
            logger.info(
                "레거시 runs blob 프로젝션 backfill",
                log_event="startup.legacy_runs_projection_backfill",
                run_rows=legacy.run_rows,
                module_rows=legacy.module_rows,
            )
        if self.redis_fanout is not None:
            try:
                await self.redis_fanout.start()
            except Exception:
                logger.warning(
                    "Redis fan-out 연결 실패 — 로컬-only 실시간 알림으로 전환",
                    log_event="startup.redis_fanout_fallback",
                    exc_info=True,
                )
                self.redis_fanout = None
                self.realtime.disable_fanout()
                self.suite_realtime.disable_fanout()
        await self.realtime.start()
        await self.suite_realtime.start()
        await self.user_service.seed_admin(
            self.settings.admin_email, self.settings.admin_password.get_secret_value()
        )

        email_status = RunCompletionEmailNotifier.inspect_env_status(self.system_codes)
        logger.info(
            "메일 알림 상태",
            log_event="startup.email_status",
            title=email_status.title,
            message=email_status.message,
            pid=os.getpid(),
            db_path=str(self.db_path),
            email_handler_count=self.event_bus.handler_count(RunFinished),
            email_subscriber_id=id(self.email_subscriber),
            outbox_relay_id=self.outbox_relay.relay_instance_id,
        )

        interrupted_runs = await self.run_service.reconcile_interrupted_runs()
        interrupted_suites = await self.suite_service.reconcile_interrupted_suites()
        if interrupted_runs or interrupted_suites:
            logger.info(
                "재기동으로 중단된 작업 정리",
                log_event="startup.reconcile_interrupted",
                interrupted_runs=interrupted_runs,
                interrupted_suites=interrupted_suites,
            )

        self.run_queue.start()
        logger.info(
            "실행 작업 큐 시작",
            log_event="startup.run_queue_started",
            worker_count=getattr(self.run_queue, "worker_count", 0),
            execution_mode=self.settings.execution_mode,
        )

        self._scheduler_task = asyncio.create_task(self.scheduler.run_forever())
        self.outbox_relay.start()
        if self.retention_scheduler is not None:
            self._retention_task = asyncio.create_task(self.retention_scheduler.run_forever())

    async def stop(self) -> None:
        await self.outbox_relay.stop()
        if self.redis_fanout is not None:
            await self.redis_fanout.stop()
        self.scheduler.stop()
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
        if self.retention_scheduler is not None:
            self.retention_scheduler.stop()
        if self._retention_task is not None:
            self._retention_task.cancel()
            try:
                await self._retention_task
            except asyncio.CancelledError:
                pass
            self._retention_task = None
        await self.run_queue.stop()
        if self.session_registry is not None:
            await self.session_registry.close()
