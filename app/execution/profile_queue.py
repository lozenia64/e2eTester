"""실행 프로필(heavy/light/interactive)별 Run 작업 큐 분할.

실행 평면 분리(Model B, WP-C1): Run 오케스트레이션 인터프리터는 항상 API 프로세스에서
in-process 로 돈다. 이 큐는 프로필별 in-process 워커 풀(``RunExecutionQueue``)에 잡을 라우팅할
뿐, Redis 로 Run 을 분배하지 않는다(씬 워커에는 Run 소비자가 없다 — 브라우저 스텝만
``WorkerExecutionGateway`` 로 원격 위임). Redis 는 워커 세션 리스·실시간 팬아웃·체크포인트 전용.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.core.logging import get_logger
from app.execution.job_queue_port import Job, RunJobDescriptor
from app.execution.run_queue import RunExecutionQueue

logger = get_logger(__name__)

_PROFILES = ("heavy", "light", "interactive")


class ProfilePartitionedRunQueue:
    """``RunExecutionQueue`` 를 execution_profile 로 라우팅하는 in-process 큐."""

    def __init__(
        self,
        *,
        heavy_workers: int,
        light_workers: int,
        interactive_workers: int,
    ) -> None:
        self._queues = {
            "heavy": RunExecutionQueue(worker_count=max(1, heavy_workers)),
            "light": RunExecutionQueue(worker_count=max(1, light_workers)),
            "interactive": RunExecutionQueue(worker_count=max(1, interactive_workers)),
        }
        self._worker_count = sum(queue.worker_count for queue in self._queues.values())

    @property
    def worker_count(self) -> int:
        return self._worker_count

    @property
    def is_running(self) -> bool:
        return all(queue.is_running for queue in self._queues.values())

    @property
    def pending_jobs(self) -> int:
        return sum(queue.pending_jobs for queue in self._queues.values())

    def start(self) -> None:
        for profile, queue in self._queues.items():
            queue.start()
            logger.info(
                "프로필 큐 시작",
                log_event="queue.profile_started",
                execution_profile=profile,
                worker_count=queue.worker_count,
            )

    async def stop(self) -> None:
        for queue in self._queues.values():
            await queue.stop()

    async def submit(self, job: Job, *, label: str) -> None:
        await self._queues["heavy"].submit(job, label=label)

    async def enqueue_run_job(self, descriptor: RunJobDescriptor) -> None:
        profile = (
            descriptor.execution_profile if descriptor.execution_profile in _PROFILES else "heavy"
        )
        await self._queues[profile].enqueue_run_job(descriptor)

    def set_run_job_handler(self, handler: Callable[[RunJobDescriptor], Awaitable[None]]) -> None:
        for queue in self._queues.values():
            queue.set_run_job_handler(handler)
