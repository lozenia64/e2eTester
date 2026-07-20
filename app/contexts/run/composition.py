"""Run BC composition — 저장소 어댑터 + RunService."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contexts.healing.service import HealingService
from app.contexts.run.application.service import RunService
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.profile_queue import ProfilePartitionedRunQueue
from app.execution.redis_session_registry import RedisSessionRegistry
from app.orchestrator.queries import RunQueries
from app.platform.artifact_manager import ArtifactManager
from app.platform.eventing.bus import EventBus
from app.platform.eventing.support import SqliteDatabase
from app.realtime.adapter import RealtimeNotificationAdapter
from app.registry.loader import ModuleRegistry
from app.storage.encrypted_run_input_store import EncryptedSqliteRunInputStore
from app.storage.sqlite_module_history_query import SqliteModuleHistoryQuery
from app.storage.sqlite_run_control_store import SqliteRunControlStore
from app.storage.sqlite_run_log_store import SqliteRunLogStore
from app.storage.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from app.storage.sqlite_session_checkpoint_store import (
    SqliteSessionCheckpointStore,
    StorageStateCipher,
)
from app.storage.sqlite_suite_summary_query import SqliteSuiteSummaryQuery


@dataclass
class RunContainer:
    run_write_repo: SqliteRunWriteRepository = field(init=False)
    run_summary_query: SqliteRunSummaryQuery = field(init=False)
    module_history_query: SqliteModuleHistoryQuery = field(init=False)
    suite_summary_query: SqliteSuiteSummaryQuery = field(init=False)
    run_log_store: SqliteRunLogStore = field(init=False)
    run_control_store: SqliteRunControlStore = field(init=False)
    run_input_store: EncryptedSqliteRunInputStore = field(init=False)
    session_checkpoint_store: SqliteSessionCheckpointStore = field(init=False)
    run_service: RunService = field(init=False)
    run_queries: RunQueries = field(init=False)


@dataclass(frozen=True)
class RunRepositories:
    run_write_repo: SqliteRunWriteRepository
    run_summary_query: SqliteRunSummaryQuery
    module_history_query: SqliteModuleHistoryQuery
    suite_summary_query: SqliteSuiteSummaryQuery
    run_log_store: SqliteRunLogStore
    run_control_store: SqliteRunControlStore
    run_input_store: EncryptedSqliteRunInputStore
    session_checkpoint_store: SqliteSessionCheckpointStore


def compose_run_repositories(
    es_db: SqliteDatabase,
    db_path: str,
    encryption_secret: str,
) -> RunRepositories:
    return RunRepositories(
        run_write_repo=SqliteRunWriteRepository(es_db),
        run_summary_query=SqliteRunSummaryQuery(es_db),
        module_history_query=SqliteModuleHistoryQuery(es_db),
        suite_summary_query=SqliteSuiteSummaryQuery(es_db),
        run_log_store=SqliteRunLogStore(db_path),
        run_control_store=SqliteRunControlStore(db_path),
        run_input_store=EncryptedSqliteRunInputStore(es_db, encryption_secret),
        session_checkpoint_store=SqliteSessionCheckpointStore(
            es_db, cipher=StorageStateCipher(encryption_secret)
        ),
    )


@dataclass(frozen=True)
class RunServiceComposition:
    run_service: RunService


def compose_run_service(
    *,
    registry: ModuleRegistry,
    run_write_repo: SqliteRunWriteRepository,
    run_summary_query: SqliteRunSummaryQuery,
    realtime: RealtimeNotificationAdapter,
    run_log_store: SqliteRunLogStore,
    execution_gateway: CompositeExecutionGateway,
    event_bus: EventBus,
    run_control_store: SqliteRunControlStore,
    run_input_store: EncryptedSqliteRunInputStore,
    run_queue: ProfilePartitionedRunQueue,
    artifact_manager: ArtifactManager,
    healing_recorder: HealingService,
    session_registry: RedisSessionRegistry | None,
    session_checkpoint_store: SqliteSessionCheckpointStore,
) -> RunServiceComposition:
    run_service = RunService(
        registry=registry,
        write_repo=run_write_repo,
        summary_query=run_summary_query,
        realtime=realtime,
        log_store=run_log_store,
        execution_gateway=execution_gateway,
        event_bus=event_bus,
        control_store=run_control_store,
        input_store=run_input_store,
        run_queue=run_queue,
        artifact_manager=artifact_manager,
        healing_recorder=healing_recorder,
        session_registry=session_registry,
        session_checkpoint_store=session_checkpoint_store,
    )
    if isinstance(run_queue, ProfilePartitionedRunQueue):
        run_queue.set_run_job_handler(run_service.dispatch_run_job)
    return RunServiceComposition(run_service=run_service)
