"""실행 평면 composition — 아티팩트·세션·큐·게이트웨이."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import E2ESettings
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.profile_queue import ProfilePartitionedRunQueue
from app.execution.redis_session_registry import RedisSessionRegistry
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.execution.worker_gateway import WorkerExecutionGateway
from app.platform.artifact_manager import ArtifactManager
from app.registry.loader import ModuleRegistry


@dataclass(frozen=True)
class ExecutionRuntimeComposition:
    artifact_manager: ArtifactManager
    system_codes: list[str]
    session_registry: RedisSessionRegistry | None
    run_queue: ProfilePartitionedRunQueue


@dataclass(frozen=True)
class ExecutionGatewayComposition:
    execution_gateway: CompositeExecutionGateway


def compose_execution_runtime(
    registry: ModuleRegistry,
    settings: E2ESettings,
) -> ExecutionRuntimeComposition:
    artifact_manager = ArtifactManager()
    system_codes = [system.system_code for system in registry.list_systems()]

    # 실행 평면 분리(Model B): Run 오케스트레이션 인터프리터는 **항상 API 프로세스에서
    # in-process** 로 돈다(ProfilePartitionedRunQueue). 원격 모드에서도 Redis 로 Run 잡을
    # 분배하지 않는다 — 씬 워커에는 Run 을 소비할 RunService/RunJobConsumer 가 없기 때문이다.
    # 브라우저 스텝만 WorkerExecutionGateway 로 워커에 위임하고, Redis 는 워커 세션 리스
    # (session_registry)·실시간 팬아웃·체크포인트에만 쓴다.
    session_registry = (
        RedisSessionRegistry(settings.redis_url, settings.session_lease_ttl)
        if settings.execution_mode == "remote"
        else None
    )
    run_queue = ProfilePartitionedRunQueue(
        heavy_workers=settings.run_concurrency_heavy,
        light_workers=settings.run_concurrency_light,
        interactive_workers=settings.run_concurrency_interactive,
    )

    return ExecutionRuntimeComposition(
        artifact_manager=artifact_manager,
        system_codes=system_codes,
        session_registry=session_registry,
        run_queue=run_queue,
    )


def compose_execution_gateway(
    settings: E2ESettings,
    session_registry: RedisSessionRegistry | None,
) -> ExecutionGatewayComposition:
    # 실행 평면 분리(WP-C1): API 프로세스에는 Playwright·실행 스레드가 없다. 실 브라우저
    # 모듈은 항상 WorkerExecutionGateway 로 워커에 위임하고(런타임 자가치유도 워커가 소유),
    # SIM 모듈만 in-process SimulatedGateway 가 처리한다. in-process 브라우저 호스트는
    # 워커의 SessionServer 하나뿐이다(구 LocalExecutionGateway 는 폐기).
    execution_gateway = CompositeExecutionGateway(
        [
            WorkerExecutionGateway(settings.worker_base_url, session_registry),
            SimulatedExecutionGateway(),
        ]
    )
    return ExecutionGatewayComposition(execution_gateway=execution_gateway)
