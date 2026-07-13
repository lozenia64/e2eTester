"""애플리케이션 컨테이너 — FastAPI ``main`` 에서 분리된 의존성 배선·수명 주기."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.contexts.healing.engine import SelfHealingEngine
from app.contexts.healing.service import HealingService
from app.contexts.identity.service import UserService
from app.contexts.insights.application.insights_service import InsightsService
from app.contexts.insights.application.ops_service import OpsService
from app.contexts.insights.application.stats_service import StatsService
from app.contexts.preset.application.service import PresetService
from app.contexts.run.application.service import RunService
from app.contexts.scheduling.run_retention import RunRetentionScheduler, RunRetentionService
from app.contexts.scheduling.scheduler import SchedulerService
from app.contexts.suite.application.service import SuiteService
from app.core.logging import configure_logging, get_logger
from app.core.settings import E2ESettings
from app.events.bus import EventBus
from app.events.subscribers.email_notification import EmailNotificationSubscriber
from app.events.subscribers.failure_analysis import FailureAnalysisSubscriber
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.relay import OutboxRelay
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.profile_queue import ProfilePartitionedRunQueue
from app.execution.redis_session_registry import RedisSessionRegistry
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.execution.worker_gateway import WorkerExecutionGateway
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.orchestrator.queries import DailyDashboardQueries, RunQueries
from app.platform.artifact_manager import ArtifactManager
from app.projections.handlers import ProjectionHandlers
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.projector import RealtimeProjector
from app.realtime.redis_fanout import RedisRealtimeFanOut
from app.registry.loader import ModuleRegistry
from app.storage.encrypted_run_input_store import EncryptedSqliteRunInputStore
from app.storage.encrypted_suite_input_store import EncryptedSqliteSuiteInputStore
from app.storage.run_history_backfill import backfill_run_history_index
from app.storage.sqlite_anomaly_handling_store import SqliteAnomalyHandlingStore
from app.storage.sqlite_anomaly_inbox_query import SqliteAnomalyInboxQuery
from app.storage.sqlite_daily_status_query import SqliteDailyStatusQuery
from app.storage.sqlite_healing_stores import (
    SqliteHealingEventStore,
    SqliteHealingPatchStore,
    SqliteHealingPolicyStore,
)
from app.storage.sqlite_module_history_query import SqliteModuleHistoryQuery
from app.storage.sqlite_module_settings_repository import SqliteModuleSettingsRepository
from app.storage.sqlite_preset_repository import SqlitePresetRepository
from app.storage.sqlite_run_control_store import SqliteRunControlStore
from app.storage.sqlite_run_log_store import SqliteRunLogStore
from app.storage.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_schedule_repository import SqliteScheduleRepository
from app.storage.sqlite_session_checkpoint_store import (
    SqliteSessionCheckpointStore,
    StorageStateCipher,
)
from app.storage.sqlite_stats_query import SqliteStatsQuery
from app.storage.sqlite_suite_control_store import SqliteSuiteControlStore
from app.storage.sqlite_suite_repository import SqliteSuiteRepository
from app.storage.sqlite_suite_summary_query import SqliteSuiteSummaryQuery
from app.storage.sqlite_suite_write_repository import SqliteSuiteWriteRepository
from app.storage.sqlite_support import DEFAULT_DB_PATH
from app.storage.sqlite_user_repository import SqliteUserRepository

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
    run_service: RunService = field(init=False)
    run_queries: RunQueries = field(init=False)
    daily_queries: DailyDashboardQueries = field(init=False)
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

        self.user_repository = SqliteUserRepository(self.db_path)
        self.user_service = UserService(self.user_repository)

        self.run_write_repo = SqliteRunWriteRepository(self.es_db)
        self.run_summary_query = SqliteRunSummaryQuery(self.es_db)
        self.module_history_query = SqliteModuleHistoryQuery(self.es_db)
        self.suite_summary_query = SqliteSuiteSummaryQuery(self.es_db)
        self.run_log_store = SqliteRunLogStore(self.db_path)
        self.run_control_store = SqliteRunControlStore(self.db_path)
        encryption_secret = self.settings.jwt_secret.get_secret_value()
        self.run_input_store = EncryptedSqliteRunInputStore(self.es_db, encryption_secret)
        # Phase C: 세션 storage_state 를 입력 스토어와 동일 비밀로 암호화해 보관하는 체크포인트 스토어.
        self.session_checkpoint_store = SqliteSessionCheckpointStore(
            self.es_db, cipher=StorageStateCipher(encryption_secret)
        )

        self.suite_write_repo = SqliteSuiteWriteRepository(self.es_db)
        self.suite_repository = SqliteSuiteRepository(self.es_db)
        self.schedule_repository = SqliteScheduleRepository(self.db_path)
        self.suite_control_store = SqliteSuiteControlStore(self.db_path)
        self.suite_input_store = EncryptedSqliteSuiteInputStore(self.es_db, encryption_secret)

        self.preset_repository = SqlitePresetRepository(self.db_path)
        self.module_settings_repository = SqliteModuleSettingsRepository(self.db_path)
        self.anomaly_handling_store = SqliteAnomalyHandlingStore(self.db_path)
        self.anomaly_inbox_query = SqliteAnomalyInboxQuery(self.es_db)
        self.daily_status_query = SqliteDailyStatusQuery(self.es_db)
        self.stats_query = SqliteStatsQuery(self.es_db)

    def wire_realtime(self) -> None:
        use_redis_fanout = self._should_use_redis_fanout()
        if use_redis_fanout:
            self.redis_fanout = RedisRealtimeFanOut(self.settings.redis_url)
            self.realtime = RealtimeNotificationAdapter(self.redis_fanout)
            self.suite_realtime = SuiteRealtimeNotificationAdapter(self.redis_fanout)
        else:
            self.redis_fanout = None
            self.realtime = RealtimeNotificationAdapter()
            self.suite_realtime = SuiteRealtimeNotificationAdapter()

    def _should_use_redis_fanout(self) -> bool:
        """remote 실행 또는 명시 opt-in 일 때만 Redis fan-out 을 켠다."""
        if not self.settings.redis_url:
            return False
        return self.settings.execution_mode == "remote" or self.settings.realtime_fanout_enabled

    def wire_execution(self) -> None:
        self.artifact_manager = ArtifactManager()
        self.system_codes = [system.system_code for system in self.registry.list_systems()]

        # 실행 평면 분리(Model B): Run 오케스트레이션 인터프리터는 **항상 API 프로세스에서
        # in-process** 로 돈다(ProfilePartitionedRunQueue). 원격 모드에서도 Redis 로 Run 잡을
        # 분배하지 않는다 — 씬 워커에는 Run 을 소비할 RunService/RunJobConsumer 가 없기 때문이다.
        # 브라우저 스텝만 WorkerExecutionGateway 로 워커에 위임하고, Redis 는 워커 세션 리스
        # (session_registry)·실시간 팬아웃·체크포인트에만 쓴다.
        self.session_registry = (
            RedisSessionRegistry(self.settings.redis_url, self.settings.session_lease_ttl)
            if self.settings.execution_mode == "remote"
            else None
        )
        self.run_queue = ProfilePartitionedRunQueue(
            heavy_workers=self.settings.run_concurrency_heavy,
            light_workers=self.settings.run_concurrency_light,
            interactive_workers=self.settings.run_concurrency_interactive,
        )

        # 실행 평면 분리(WP-C1): API 프로세스에는 Playwright·실행 스레드가 없다. 실 브라우저
        # 모듈은 항상 WorkerExecutionGateway 로 워커에 위임하고(런타임 자가치유도 워커가 소유),
        # SIM 모듈만 in-process SimulatedGateway 가 처리한다. in-process 브라우저 호스트는
        # 워커의 SessionServer 하나뿐이다(구 LocalExecutionGateway 는 폐기).
        self.healing_engine = None  # 런타임 치유 엔진은 워커 프로세스가 소유(API 는 기록/패치만).

        self.healing_service = HealingService(
            event_store=SqliteHealingEventStore(self.db_path),
            policy_store=SqliteHealingPolicyStore(self.db_path),
            patch_store=SqliteHealingPatchStore(self.db_path),
            registry=self.registry,
        )

        self.execution_gateway = CompositeExecutionGateway(
            [
                WorkerExecutionGateway(self.settings.worker_base_url, self.session_registry),
                SimulatedExecutionGateway(),
            ]
        )

    def wire_orchestration(self) -> None:
        self.event_bus = EventBus()
        failure_analyzer = GeminiFailureAnalyzer.from_env()
        FailureAnalysisSubscriber(failure_analyzer, self.run_write_repo, self.registry).register(
            self.event_bus
        )
        EmailNotificationSubscriber(self.system_codes).register(self.event_bus)

        self.run_service = RunService(
            registry=self.registry,
            write_repo=self.run_write_repo,
            summary_query=self.run_summary_query,
            realtime=self.realtime,
            log_store=self.run_log_store,
            execution_gateway=self.execution_gateway,
            event_bus=self.event_bus,
            control_store=self.run_control_store,
            input_store=self.run_input_store,
            run_queue=self.run_queue,
            artifact_manager=self.artifact_manager,
            healing_recorder=self.healing_service,
            session_registry=self.session_registry,
            session_checkpoint_store=self.session_checkpoint_store,
        )
        if isinstance(self.run_queue, ProfilePartitionedRunQueue):
            self.run_queue.set_run_job_handler(self.run_service.dispatch_run_job)

        # 읽기 전용 질의 핸들러(CQRS query side) — 라우트가 직접 주입받는다.
        self.run_queries = RunQueries(
            self.run_summary_query, self.run_write_repo, self.run_log_store
        )
        self.daily_queries = DailyDashboardQueries(self.registry, self.daily_status_query)

        self.preset_service = PresetService(
            repository=self.preset_repository,
            run_service=self.run_service,
        )

        self.suite_service = SuiteService(
            registry=self.registry,
            run_commands=self.run_service,
            write_repo=self.suite_write_repo,
            read_repo=self.suite_repository,
            realtime=self.suite_realtime,
            event_bus=self.event_bus,
            cancel_store=self.suite_control_store,
            input_store=self.suite_input_store,
            summary_query=self.suite_summary_query,
        )
        self.suite_service.register(self.event_bus)

        self.scheduler = SchedulerService(
            run_commands=self.run_service,
            suite_service=self.suite_service,
            repository=self.schedule_repository,
            run_queries=self.run_queries,
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
        self.retention_scheduler = RunRetentionScheduler.from_env(
            RunRetentionService(self.run_service)
        )

    def wire_read_models(self) -> None:
        self.stats_service = StatsService(
            stats_query=self.stats_query,
            suite_summary_query=self.suite_summary_query,
            registry=self.registry,
            module_settings_repo=self.module_settings_repository,
            user_service=self.user_service,
            schedule_repo=self.schedule_repository,
        )
        self.insights_service = InsightsService(
            run_summary_query=self.run_summary_query,
            module_history_query=self.module_history_query,
            registry=self.registry,
            anomaly_store=self.anomaly_handling_store,
            anomaly_query=self.anomaly_inbox_query,
            user_service=self.user_service,
            suite_summary_query=self.suite_summary_query,
            schedule_repo=self.schedule_repository,
        )
        self.ops_service = OpsService(
            settings=self.settings,
            run_summary_query=self.run_summary_query,
            suite_summary_query=self.suite_summary_query,
            schedule_repo=self.schedule_repository,
            run_queue=self.run_queue,
            scheduler=self.scheduler,
        )

    def apply_to_app_state(self, app: FastAPI) -> None:
        app.state.settings = self.settings
        app.state.user_service = self.user_service
        app.state.healing_service = self.healing_service
        app.state.module_settings_repo = self.module_settings_repository
        app.state.preset_service = self.preset_service
        app.state.run_service = self.run_service
        app.state.run_queries = self.run_queries
        app.state.daily_queries = self.daily_queries
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
        await backfill_run_history_index(self.es_db, self.run_write_repo)
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
