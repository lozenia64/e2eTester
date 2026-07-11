from __future__ import annotations

import asyncio
import os
import socket

import uvicorn

from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.events.bus import EventBus
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.local_gateway import LocalExecutionGateway
from app.execution.redis_job_queue import RedisJobQueue
from app.execution.redis_session_registry import RedisSessionRegistry
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.healing.engine import SelfHealingEngine
from app.orchestrator.healing_service import HealingService
from app.orchestrator.run_comparator import RunComparator
from app.orchestrator.run_service import RunService
from app.realtime.adapter import RealtimeNotificationAdapter
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.storage.encrypted_run_input_store import EncryptedSqliteRunInputStore
from app.storage.sqlite_healing_stores import (
    SqliteHealingEventStore,
    SqliteHealingPatchStore,
    SqliteHealingPolicyReader,
    SqliteHealingPolicyStore,
)
from app.storage.sqlite_run_control_store import SqliteRunControlStore
from app.storage.sqlite_run_history_query import SqliteRunHistoryQuery
from app.storage.sqlite_run_log_store import SqliteRunLogStore
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository
from worker.health import SessionHeartbeatManager
from worker.http_server import create_http_app
from worker.job_consumer import RunJobConsumer
from worker.session_server import SessionServer

logger = get_logger(__name__)


async def _async_main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    registry = ModuleRegistry()
    db_path = settings.db_path
    es_db = SqliteDatabase(db_path)
    await ensure_schema(es_db)

    run_write_repo = SqliteRunWriteRepository(es_db)
    run_history_query = SqliteRunHistoryQuery(es_db, run_write_repo)
    realtime = RealtimeNotificationAdapter()
    run_log_store = SqliteRunLogStore(db_path)
    run_control_store = SqliteRunControlStore(db_path)
    encryption_secret = settings.jwt_secret.get_secret_value()
    run_input_store = EncryptedSqliteRunInputStore(es_db, encryption_secret)
    artifact_manager = ArtifactManager()
    system_codes = [system.system_code for system in registry.list_systems()]

    healing_engine = SelfHealingEngine(SqliteHealingPolicyReader(db_path))
    healing_service = HealingService(
        event_store=SqliteHealingEventStore(db_path),
        policy_store=SqliteHealingPolicyStore(db_path),
        patch_store=SqliteHealingPatchStore(db_path),
        registry=registry,
    )

    session_server = SessionServer(artifact_manager, system_codes, healing_engine=healing_engine)
    execution_gateway = CompositeExecutionGateway(
        [
            LocalExecutionGateway(artifact_manager, system_codes, healing_engine=healing_engine),
            SimulatedExecutionGateway(),
        ]
    )
    event_bus = EventBus()
    redis_queue = RedisJobQueue(settings.redis_url)
    redis_queue.start()

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
        run_queue=redis_queue,
        artifact_manager=artifact_manager,
        healing_recorder=healing_service,
        comparator=RunComparator(run_history_query),
    )

    session_registry = RedisSessionRegistry(settings.redis_url, settings.session_lease_ttl)
    heartbeat_manager = SessionHeartbeatManager(session_registry)
    consumer_name = f"{socket.gethostname()}-{os.getpid()}"
    job_consumer = RunJobConsumer(redis_queue, run_service, consumer_name=consumer_name)
    job_consumer.start()

    host = os.environ.get("E2E_WORKER_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("E2E_WORKER_HTTP_PORT", "8100"))
    http_app = create_http_app(session_server, heartbeat_manager)
    config = uvicorn.Config(http_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    logger.info(
        "워커 시작",
        log_event="worker.started",
        http_port=port,
        consumer_name=consumer_name,
        worker_concurrency=settings.worker_concurrency,
    )
    await server.serve()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
