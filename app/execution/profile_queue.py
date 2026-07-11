"""실행 프로필(heavy/light/interactive)별 Run 작업 큐 분할."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.core.logging import get_logger
from app.execution.job_queue_port import Job, RunJobDescriptor
from app.execution.redis_job_queue import RedisJobQueue
from app.execution.run_queue import RunExecutionQueue

logger = get_logger(__name__)

_PROFILES = ("heavy", "light", "interactive")


class ProfilePartitionedRunQueue:
    """``RunExecutionQueue`` 또는 ``RedisJobQueue`` 를 execution_profile 로 라우팅한다.

    로컬 모드에서는 프로필별 in-process 워커 풀을 두고, 원격 모드에서는 단일
    ``RedisJobQueue`` 로 위임한다(워커 프로세스가 소비).
    """

    def __init__(
        self,
        *,
        heavy_workers: int,
        light_workers: int,
        interactive_workers: int,
        redis_queue: RedisJobQueue | None = None,
    ) -> None:
        self._redis_queue = redis_queue
        if redis_queue is not None:
            self._queues = None
            self._worker_count = redis_queue.worker_count
        else:
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
        if self._redis_queue is not None:
            return self._redis_queue.is_running
        assert self._queues is not None
        return all(queue.is_running for queue in self._queues.values())

    @property
    def pending_jobs(self) -> int:
        if self._redis_queue is not None:
            return self._redis_queue.pending_jobs
        assert self._queues is not None
        return sum(queue.pending_jobs for queue in self._queues.values())

    def start(self) -> None:
        if self._redis_queue is not None:
            self._redis_queue.start()
            return
        assert self._queues is not None
        for profile, queue in self._queues.items():
            queue.start()
            logger.info(
                "프로필 큐 시작",
                log_event="queue.profile_started",
                execution_profile=profile,
                worker_count=queue.worker_count,
            )

    async def stop(self) -> None:
        if self._redis_queue is not None:
            await self._redis_queue.stop()
            return
        assert self._queues is not None
        for queue in self._queues.values():
            await queue.stop()

    async def submit(self, job: Job, *, label: str) -> None:
        if self._redis_queue is not None:
            await self._redis_queue.submit(job, label=label)
            return
        assert self._queues is not None
        await self._queues["heavy"].submit(job, label=label)

    async def enqueue_run_job(self, descriptor: RunJobDescriptor) -> None:
        profile = (
            descriptor.execution_profile if descriptor.execution_profile in _PROFILES else "heavy"
        )
        if self._redis_queue is not None:
            await self._redis_queue.enqueue_run_job(descriptor)
            return
        assert self._queues is not None
        await self._queues[profile].enqueue_run_job(descriptor)

    def set_run_job_handler(self, handler: Callable[[RunJobDescriptor], Awaitable[None]]) -> None:
        if self._redis_queue is not None:
            return
        assert self._queues is not None
        for queue in self._queues.values():
            queue.set_run_job_handler(handler)
