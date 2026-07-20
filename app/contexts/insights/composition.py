"""Insights BC composition — stats, insights, and ops read-model services."""

from __future__ import annotations

from dataclasses import dataclass

from app.contexts.identity.service import UserService
from app.contexts.insights.application.insights_service import InsightsService
from app.contexts.insights.application.ops_service import OpsService
from app.contexts.insights.application.stats_service import StatsService
from app.contexts.insights.infrastructure.sqlite_anomaly_handling_store import (
    SqliteAnomalyHandlingStore,
)
from app.contexts.insights.infrastructure.sqlite_anomaly_inbox_query import SqliteAnomalyInboxQuery
from app.contexts.insights.infrastructure.sqlite_daily_status_query import (
    SqliteDailyStatusQuery,
)
from app.contexts.insights.infrastructure.sqlite_module_settings_repository import (
    SqliteModuleSettingsRepository,
)
from app.contexts.insights.infrastructure.sqlite_stats_query import SqliteStatsQuery
from app.contexts.scheduling.infrastructure.sqlite_schedule_repository import (
    SqliteScheduleRepository,
)
from app.contexts.scheduling.scheduler import SchedulerService
from app.core.settings import E2ESettings
from app.execution.profile_queue import ProfilePartitionedRunQueue
from app.orchestrator.queries import AdminDashboardQueries, DailyDashboardQueries
from app.platform.eventing.support import SqliteDatabase
from app.registry.loader import ModuleRegistry
from app.storage.sqlite_module_history_query import SqliteModuleHistoryQuery
from app.storage.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.storage.sqlite_suite_summary_query import SqliteSuiteSummaryQuery


@dataclass(frozen=True)
class InsightsRepositories:
    module_settings_repository: SqliteModuleSettingsRepository
    anomaly_handling_store: SqliteAnomalyHandlingStore
    anomaly_inbox_query: SqliteAnomalyInboxQuery
    daily_status_query: SqliteDailyStatusQuery
    stats_query: SqliteStatsQuery


def compose_insights_repositories(db_path: str, es_db: SqliteDatabase) -> InsightsRepositories:
    return InsightsRepositories(
        module_settings_repository=SqliteModuleSettingsRepository(db_path),
        anomaly_handling_store=SqliteAnomalyHandlingStore(db_path),
        anomaly_inbox_query=SqliteAnomalyInboxQuery(es_db),
        daily_status_query=SqliteDailyStatusQuery(es_db),
        stats_query=SqliteStatsQuery(es_db),
    )


@dataclass
class InsightsContainer:
    repos: InsightsRepositories
    daily_queries: DailyDashboardQueries | None = None
    admin_dashboard_queries: AdminDashboardQueries | None = None
    stats_service: StatsService | None = None
    insights_service: InsightsService | None = None
    ops_service: OpsService | None = None


@dataclass(frozen=True)
class InsightsServices:
    stats_service: StatsService
    insights_service: InsightsService
    ops_service: OpsService


def compose_insights(
    *,
    stats_query: SqliteStatsQuery,
    suite_summary_query: SqliteSuiteSummaryQuery,
    registry: ModuleRegistry,
    module_settings_repo: SqliteModuleSettingsRepository,
    user_service: UserService,
    schedule_repo: SqliteScheduleRepository,
    run_summary_query: SqliteRunSummaryQuery,
    module_history_query: SqliteModuleHistoryQuery,
    anomaly_store: SqliteAnomalyHandlingStore,
    anomaly_query: SqliteAnomalyInboxQuery,
    settings: E2ESettings,
    run_queue: ProfilePartitionedRunQueue,
    scheduler: SchedulerService,
) -> InsightsServices:
    stats_service = StatsService(
        stats_query=stats_query,
        suite_summary_query=suite_summary_query,
        registry=registry,
        module_settings_repo=module_settings_repo,
        user_service=user_service,
        schedule_repo=schedule_repo,
    )
    insights_service = InsightsService(
        run_summary_query=run_summary_query,
        module_history_query=module_history_query,
        registry=registry,
        anomaly_store=anomaly_store,
        anomaly_query=anomaly_query,
        user_service=user_service,
        suite_summary_query=suite_summary_query,
        schedule_repo=schedule_repo,
    )
    ops_service = OpsService(
        settings=settings,
        run_summary_query=run_summary_query,
        suite_summary_query=suite_summary_query,
        schedule_repo=schedule_repo,
        run_queue=run_queue,
        scheduler=scheduler,
    )
    return InsightsServices(
        stats_service=stats_service,
        insights_service=insights_service,
        ops_service=ops_service,
    )
