"""워커 진입점 — **씬 워커**(WP-C1): 세션 HTTP 실행 호스트 전용.

실행 평면 분리 후 워커는 오케스트레이션을 하지 않는다 — 오케스트레이션(상태 전이·이벤트
append·실행 순서)은 API 프로세스의 인터프리터가 독점하고, 워커는 (1) ``SessionHost``(브라우저
+ 스레드 어피니티) 위에서 스텝을 실행하는 HTTP API(``open-session``/``run-step``/``submit-input``/
``resume-from-step``)와 (2) 세션 리스 하트비트만 노출한다. API 의 ``WorkerExecutionGateway`` 가
이 HTTP API 를 스텝 단위로 원격 구동한다. 과거의 워커 내장 ``RunService``·``RunJobConsumer``
(두 번째 컴포지션 루트, Run 전체를 워커가 오케스트레이션하던 Model A)는 제거됐다.
"""

from __future__ import annotations

import asyncio
import os

import uvicorn

from app.contexts.healing.engine import SelfHealingEngine
from app.contexts.healing.infrastructure.sqlite_healing_stores import SqliteHealingPolicyReader
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.execution.redis_session_registry import RedisSessionRegistry
from app.platform.artifact_manager import ArtifactManager
from app.registry.loader import ModuleRegistry
from worker.health import SessionHeartbeatManager
from worker.http_server import create_http_app
from worker.session_server import SessionServer

logger = get_logger(__name__)


async def _async_main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    # 씬 워커는 상태 저장소(runs/이벤트/입력)를 배선하지 않는다 — 그 소유는 API 프로세스다.
    # 워커가 아는 것은 (a) 어떤 시스템의 스텝을 어떻게 실행하는지(registry+executors),
    # (b) 브라우저 아티팩트 경로, (c) 런타임 자가치유(실행 스레드에서 동작)뿐이다.
    registry = ModuleRegistry()
    artifact_manager = ArtifactManager()
    system_codes = [system.system_code for system in registry.list_systems()]
    healing_engine = SelfHealingEngine(SqliteHealingPolicyReader(settings.db_path))

    # 세션 HTTP 실행 호스트: open-session/run-step/submit-input/resume-from-step + storage_state 캡처.
    session_server = SessionServer(artifact_manager, system_codes, healing_engine=healing_engine)
    session_registry = RedisSessionRegistry(settings.redis_url, settings.session_lease_ttl)
    heartbeat_manager = SessionHeartbeatManager(session_registry)

    host = os.environ.get("E2E_WORKER_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("E2E_WORKER_HTTP_PORT", "8100"))
    http_app = create_http_app(session_server, heartbeat_manager)
    config = uvicorn.Config(http_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    logger.info(
        "씬 워커 시작(세션 HTTP 실행 호스트 — 오케스트레이션은 API 소유)",
        log_event="worker.started",
        http_port=port,
    )
    await server.serve()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
