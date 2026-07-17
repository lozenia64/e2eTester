"""Suite BC composition — 저장소 어댑터 + SuiteService."""

from __future__ import annotations

from dataclasses import dataclass

from app.contexts.run.application.service import RunService
from app.contexts.scheduling.infrastructure.sqlite_schedule_repository import (
    SqliteScheduleRepository,
)
from app.contexts.suite.application.service import SuiteService
from app.platform.eventing.bus import EventBus
from app.platform.eventing.support import SqliteDatabase
from app.realtime.adapter import SuiteRealtimeNotificationAdapter
from app.registry.loader import ModuleRegistry
from app.storage.encrypted_suite_input_store import EncryptedSqliteSuiteInputStore
from app.storage.sqlite_suite_control_store import SqliteSuiteControlStore
from app.storage.sqlite_suite_repository import SqliteSuiteRepository
from app.storage.sqlite_suite_summary_query import SqliteSuiteSummaryQuery
from app.storage.sqlite_suite_write_repository import SqliteSuiteWriteRepository


@dataclass(frozen=True)
class SuiteRepositories:
    suite_write_repo: SqliteSuiteWriteRepository
    suite_repository: SqliteSuiteRepository
    schedule_repository: SqliteScheduleRepository
    suite_control_store: SqliteSuiteControlStore
    suite_input_store: EncryptedSqliteSuiteInputStore


def compose_suite_repositories(
    es_db: SqliteDatabase,
    db_path: str,
    encryption_secret: str,
) -> SuiteRepositories:
    return SuiteRepositories(
        suite_write_repo=SqliteSuiteWriteRepository(es_db),
        suite_repository=SqliteSuiteRepository(es_db),
        schedule_repository=SqliteScheduleRepository(db_path),
        suite_control_store=SqliteSuiteControlStore(db_path),
        suite_input_store=EncryptedSqliteSuiteInputStore(es_db, encryption_secret),
    )


@dataclass(frozen=True)
class SuiteServiceComposition:
    suite_service: SuiteService


def compose_suite_service(
    *,
    registry: ModuleRegistry,
    run_commands: RunService,
    suite_write_repo: SqliteSuiteWriteRepository,
    suite_repository: SqliteSuiteRepository,
    suite_realtime: SuiteRealtimeNotificationAdapter,
    event_bus: EventBus,
    suite_control_store: SqliteSuiteControlStore,
    suite_input_store: EncryptedSqliteSuiteInputStore,
    suite_summary_query: SqliteSuiteSummaryQuery,
) -> SuiteServiceComposition:
    suite_service = SuiteService(
        registry=registry,
        run_commands=run_commands,
        write_repo=suite_write_repo,
        read_repo=suite_repository,
        realtime=suite_realtime,
        event_bus=event_bus,
        cancel_store=suite_control_store,
        input_store=suite_input_store,
        summary_query=suite_summary_query,
    )
    suite_service.register(event_bus)
    return SuiteServiceComposition(suite_service=suite_service)
