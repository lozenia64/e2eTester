"""애플리케이션 컨테이너 — FastAPI ``main`` 에서 분리된 의존성 배선·수명 주기."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.contexts.healing.composition import HealingContainer, compose_healing
from app.contexts.identity.composition import IdentityContainer, compose_identity
from app.contexts.insights.composition import (
    InsightsContainer,
    compose_insights,
    compose_insights_repositories,
)
from app.contexts.preset.composition import (
    PresetContainer,
    compose_preset_repository,
    compose_preset_service,
)
from app.contexts.run.composition import (
    RunContainer,
    compose_run_container,
    compose_run_repositories,
    compose_run_service,
)
from app.contexts.run.infrastructure.backfill.legacy_runs_projection_backfill import (
    backfill_from_legacy_runs,
)
from app.contexts.run.infrastructure.backfill.module_history_backfill import (
    backfill_module_history_index,
)
from app.contexts.run.infrastructure.backfill.run_history_backfill import backfill_run_history_index
from app.contexts.run.infrastructure.failure_analysis_subscriber import FailureAnalysisSubscriber
from app.contexts.run.infrastructure.hydration import RunHydrator, RunProjectionLoader
from app.contexts.scheduling.composition import (
    SchedulingContainer,
    compose_daily_report_scheduler,
    compose_retention_scheduler,
    compose_scheduler,
)
from app.contexts.scheduling.infrastructure.sqlite_schedule_repository import (
    SqliteScheduleRepository,
)
from app.contexts.suite.composition import (
    SuiteContainer,
    compose_suite_repositories,
    compose_suite_service,
)
from app.contexts.suite.infrastructure.hydration import SuiteHydrator
from app.core.env_utils import DEFAULT_ENV_FILE_PATH, load_dotenv_file
from app.core.logging import configure_logging, get_logger
from app.core.settings import E2ESettings
from app.execution.composition import (
    ExecutionContainer,
    compose_execution_gateway,
    compose_execution_runtime,
)
from app.notifications.daily_report_email import (
    DailyReportEmailService,
    resolve_daily_report_recipients,
)
from app.notifications.infrastructure.sqlite_email_notification_dedup import (
    SqliteEmailNotificationDedupStore,
)
from app.notifications.run_completion_email import (
    EmailNotificationConfig,
    RunCompletionEmailNotifier,
)
from app.orchestrator.queries import AdminDashboardQueries, DailyDashboardQueries
from app.orchestrator.queries.daily_summary_queries import DailySummaryQueries
from app.platform.db import DEFAULT_DB_PATH
from app.platform.eventing.bus import RunFinished
from app.platform.eventing.composition import EventingContainer, compose_event_bus
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.relay import OutboxRelay
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.platform.snapshot_rebuild import (
    rebuild_missing_run_snapshots,
    repair_incomplete_run_snapshots,
)
from app.realtime.composition import RealtimeContainer, compose_realtime, should_use_redis_fanout
from app.realtime.projector import RealtimeProjector
from app.registry.loader import ModuleRegistry

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

    identity: IdentityContainer = field(init=False)
    run: RunContainer = field(init=False)
    suite: SuiteContainer = field(init=False)
    preset: PresetContainer = field(init=False)
    scheduling: SchedulingContainer = field(init=False)
    insights: InsightsContainer = field(init=False)
    healing: HealingContainer = field(init=False)
    execution: ExecutionContainer = field(init=False)
    realtime: RealtimeContainer = field(init=False)
    eventing: EventingContainer = field(init=False)

    outbox_relay: OutboxRelay = field(init=False)
    _scheduler_task: asyncio.Task[None] | None = field(init=False, default=None, repr=False)
    _retention_task: asyncio.Task[None] | None = field(init=False, default=None, repr=False)
    _daily_report_task: asyncio.Task[None] | None = field(init=False, default=None, repr=False)

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

        self.identity = compose_identity(self.db_path)

        encryption_secret = self.settings.jwt_secret.get_secret_value()
        self.run = compose_run_container(
            compose_run_repositories(self.es_db, self.db_path, encryption_secret)
        )
        self.suite = SuiteContainer(
            repos=compose_suite_repositories(self.es_db, self.db_path, encryption_secret)
        )
        self.scheduling = SchedulingContainer(
            schedule_repository=SqliteScheduleRepository(self.db_path)
        )
        self.preset = PresetContainer(preset_repository=compose_preset_repository(self.db_path))
        self.insights = InsightsContainer(
            repos=compose_insights_repositories(self.db_path, self.es_db)
        )

    def wire_realtime(self) -> None:
        self.realtime = compose_realtime(self.settings)

    def _should_use_redis_fanout(self) -> bool:
        return should_use_redis_fanout(self.settings)

    def wire_execution(self) -> None:
        runtime = compose_execution_runtime(self.registry, self.settings)
        healing = compose_healing(self.db_path, self.registry)
        gateway = compose_execution_gateway(self.settings, runtime.session_registry)

        self.healing = healing
        self.execution = ExecutionContainer(
            artifact_manager=runtime.artifact_manager,
            system_codes=runtime.system_codes,
            session_registry=runtime.session_registry,
            run_queue=runtime.run_queue,
            execution_gateway=gateway.execution_gateway,
        )

    def wire_orchestration(self) -> None:
        self.eventing = compose_event_bus(
            system_codes=self.execution.system_codes,
            es_db=self.es_db,
        )
        failure_analyzer = GeminiFailureAnalyzer.from_env()
        FailureAnalysisSubscriber(
            failure_analyzer,
            self.run.repos.run_write_repo,
            self.registry,
        ).register(self.eventing.event_bus)

        run_svc = compose_run_service(
            registry=self.registry,
            run_write_repo=self.run.repos.run_write_repo,
            run_summary_query=self.run.repos.run_summary_query,
            realtime=self.realtime.realtime,
            run_log_store=self.run.repos.run_log_store,
            execution_gateway=self.execution.execution_gateway,
            event_bus=self.eventing.event_bus,
            run_control_store=self.run.repos.run_control_store,
            run_input_store=self.run.repos.run_input_store,
            run_queue=self.execution.run_queue,
            artifact_manager=self.execution.artifact_manager,
            healing_recorder=self.healing.healing_service,
            session_registry=self.execution.session_registry,
            session_checkpoint_store=self.run.repos.session_checkpoint_store,
            settings=self.settings,
        )
        self.run.services = run_svc

        self.insights.daily_queries = DailyDashboardQueries(
            self.registry, self.insights.repos.daily_status_query
        )
        self.insights.admin_dashboard_queries = AdminDashboardQueries(
            self.registry, self.run.repos.run_summary_query
        )

        self.preset.preset_service = compose_preset_service(
            self.preset.preset_repository, run_svc.run_service
        )

        suite_svc = compose_suite_service(
            registry=self.registry,
            run_commands=run_svc.run_service,
            suite_write_repo=self.suite.repos.suite_write_repo,
            suite_repository=self.suite.repos.suite_repository,
            suite_realtime=self.realtime.suite_realtime,
            event_bus=self.eventing.event_bus,
            suite_control_store=self.suite.repos.suite_control_store,
            suite_input_store=self.suite.repos.suite_input_store,
            suite_summary_query=self.run.repos.suite_summary_query,
        )
        self.suite.services = suite_svc

        self.scheduling.scheduler = compose_scheduler(
            run_svc.run_service,
            suite_svc.suite_service,
            self.scheduling.schedule_repository,
            self.run.run_queries,
            self.preset.preset_repository,
        )
        realtime_projector = RealtimeProjector(
            self.realtime.realtime,
            self.realtime.suite_realtime,
            run_loader=self.run.repos.run_write_repo.get_run,
            suite_loader=self.suite.repos.suite_write_repo.get_suite,
            log_store=self.run.repos.run_log_store,
        )
        run_projection_loader = RunProjectionLoader(self.run.repos.run_write_repo)
        self.outbox_relay = OutboxRelay(
            SqliteOutbox(self.es_db),
            ProjectionHandlers(self.es_db, loaders={"Run": run_projection_loader}),
            hydrators={
                "Run": RunHydrator(
                    self.run.repos.run_write_repo,
                    self.run.repos.run_log_store,
                ),
                "Suite": SuiteHydrator(suite_svc.suite_service),
            },
            event_bus=self.eventing.event_bus,
            realtime=realtime_projector,
        )
        self.scheduling.retention_scheduler = compose_retention_scheduler(run_svc.run_service)

    def wire_read_models(self) -> None:
        services = compose_insights(
            stats_query=self.insights.repos.stats_query,
            suite_summary_query=self.run.repos.suite_summary_query,
            registry=self.registry,
            module_settings_repo=self.insights.repos.module_settings_repository,
            user_service=self.identity.user_service,
            schedule_repo=self.scheduling.schedule_repository,
            run_summary_query=self.run.repos.run_summary_query,
            module_history_query=self.run.repos.module_history_query,
            anomaly_store=self.insights.repos.anomaly_handling_store,
            anomaly_query=self.insights.repos.anomaly_inbox_query,
            settings=self.settings,
            run_queue=self.execution.run_queue,
            scheduler=self.scheduling.scheduler,
        )
        self.insights.stats_service = services.stats_service
        self.insights.insights_service = services.insights_service
        self.insights.ops_service = services.ops_service

        self.insights.daily_summary_queries = DailySummaryQueries(
            self.insights.daily_queries,
            self.healing.healing_service,
            self.insights.stats_service,
        )
        email_config = EmailNotificationConfig.from_env(self.execution.system_codes)
        if email_config is not None:
            daily_recipients, recipient_errors = resolve_daily_report_recipients(
                load_dotenv_file(DEFAULT_ENV_FILE_PATH)
            )
            for message in recipient_errors:
                # 오타 난 주소를 조용히 버리면 그 사람만 리포트를 못 받고 이유가 남지 않는다.
                logger.warning(
                    "일간 리포트 수신자 설정 오류",
                    log_event="daily_report.recipient_config_error",
                    detail=message,
                )
            daily_report_service = DailyReportEmailService(
                summary_queries=self.insights.daily_summary_queries,
                dedup_store=SqliteEmailNotificationDedupStore(self.es_db),
                config=email_config,
                recipients=daily_recipients,
                public_base_url=self.settings.public_base_url,
                wall_enabled=self.settings.wall_enabled,
            )
            self.scheduling.daily_report_scheduler = compose_daily_report_scheduler(
                daily_report_service
            )

    def apply_to_app_state(self, app: FastAPI) -> None:
        app.state.settings = self.settings
        app.state.user_service = self.identity.user_service
        app.state.healing_service = self.healing.healing_service
        app.state.module_settings_repo = self.insights.repos.module_settings_repository
        app.state.preset_service = self.preset.preset_service
        app.state.run_service = self.run.services.run_service
        app.state.run_queries = self.run.run_queries
        app.state.run_summary_query = self.run.repos.run_summary_query
        app.state.daily_queries = self.insights.daily_queries
        app.state.daily_summary_queries = self.insights.daily_summary_queries
        app.state.admin_dashboard_queries = self.insights.admin_dashboard_queries
        app.state.suite_summary_query = self.run.repos.suite_summary_query
        app.state.suite_service = self.suite.services.suite_service
        app.state.run_queue = self.execution.run_queue
        app.state.registry = self.registry
        app.state.suite_repository = self.suite.repos.suite_repository
        app.state.schedule_repository = self.scheduling.schedule_repository
        app.state.otp_relay_token = self.settings.otp_relay_token_str()
        app.state.otp_relay_regex = self.settings.otp_relay_regex
        app.state.stats_service = self.insights.stats_service
        app.state.anomaly_store = self.insights.repos.anomaly_handling_store
        app.state.insights_service = self.insights.insights_service
        app.state.schedule_service = self.scheduling.scheduler
        app.state.ops_service = self.insights.ops_service

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
        await backfill_run_history_index(self.es_db, self.run.repos.run_write_repo)
        module_rows = await backfill_module_history_index(self.es_db, self.run.repos.run_write_repo)
        legacy = await backfill_from_legacy_runs(self.es_db, self.run.repos.run_write_repo)
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
        if self.realtime.redis_fanout is not None:
            try:
                await self.realtime.redis_fanout.start()
            except Exception:
                logger.warning(
                    "Redis fan-out 연결 실패 — 로컬-only 실시간 알림으로 전환",
                    log_event="startup.redis_fanout_fallback",
                    exc_info=True,
                )
                self.realtime = RealtimeContainer(
                    realtime=self.realtime.realtime,
                    suite_realtime=self.realtime.suite_realtime,
                    redis_fanout=None,
                )
                self.realtime.realtime.disable_fanout()
                self.realtime.suite_realtime.disable_fanout()
        await self.realtime.realtime.start()
        await self.realtime.suite_realtime.start()
        await self.identity.user_service.seed_admin(
            self.settings.admin_email, self.settings.admin_password.get_secret_value()
        )

        email_status = RunCompletionEmailNotifier.inspect_env_status(self.execution.system_codes)
        logger.info(
            "메일 알림 상태",
            log_event="startup.email_status",
            title=email_status.title,
            message=email_status.message,
            pid=os.getpid(),
            db_path=str(self.db_path),
            email_handler_count=self.eventing.event_bus.handler_count(RunFinished),
            email_subscriber_id=id(self.eventing.email_subscriber),
            outbox_relay_id=self.outbox_relay.relay_instance_id,
        )

        interrupted_runs = await self.run.services.run_service.reconcile_interrupted_runs()
        interrupted_suites = await self.suite.services.suite_service.reconcile_interrupted_suites()
        if interrupted_runs or interrupted_suites:
            logger.info(
                "재기동으로 중단된 작업 정리",
                log_event="startup.reconcile_interrupted",
                interrupted_runs=interrupted_runs,
                interrupted_suites=interrupted_suites,
            )

        self.execution.run_queue.start()
        logger.info(
            "실행 작업 큐 시작",
            log_event="startup.run_queue_started",
            worker_count=getattr(self.execution.run_queue, "worker_count", 0),
            execution_mode=self.settings.execution_mode,
        )

        self._scheduler_task = asyncio.create_task(self.scheduling.scheduler.run_forever())
        self.outbox_relay.start()
        if self.scheduling.retention_scheduler is not None:
            self._retention_task = asyncio.create_task(
                self.scheduling.retention_scheduler.run_forever()
            )
        if self.scheduling.daily_report_scheduler is not None:
            self._daily_report_task = asyncio.create_task(
                self.scheduling.daily_report_scheduler.run_forever()
            )

    async def stop(self) -> None:
        await self.outbox_relay.stop()
        if self.realtime.redis_fanout is not None:
            await self.realtime.redis_fanout.stop()
        self.scheduling.scheduler.stop()
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
        if self.scheduling.retention_scheduler is not None:
            self.scheduling.retention_scheduler.stop()
        if self._retention_task is not None:
            self._retention_task.cancel()
            try:
                await self._retention_task
            except asyncio.CancelledError:
                pass
            self._retention_task = None
        if self.scheduling.daily_report_scheduler is not None:
            self.scheduling.daily_report_scheduler.stop()
        if self._daily_report_task is not None:
            self._daily_report_task.cancel()
            try:
                await self._daily_report_task
            except asyncio.CancelledError:
                pass
            self._daily_report_task = None
        await self.execution.run_queue.stop()
        if self.execution.session_registry is not None:
            await self.execution.session_registry.close()
