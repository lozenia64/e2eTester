from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.core.logging import get_logger
from app.execution.in_memory_job_queue import DEFAULT_RUN_CONCURRENCY, InMemoryJobQueue
from app.execution.job_queue_port import Job, JobQueuePort, RunJobDescriptor

logger = get_logger(__name__)

# 하위 호환: 기존 import 경로 유지.
JobQueue = JobQueuePort


class RunExecutionQueue:
    """Run 실행을 위한 **감독되는(in-process) 작업 큐**.

    ``InMemoryJobQueue`` 백엔드를 워커 풀이 소비한다. 원격 모드에서는 API 가
    ``RedisJobQueue`` 로 작업을 적재하고, 별도 워커 프로세스가 소비한다.
    """

    def __init__(
        self,
        worker_count: int = DEFAULT_RUN_CONCURRENCY,
        *,
        backend: InMemoryJobQueue | None = None,
        run_job_handler: Callable[[RunJobDescriptor], Awaitable[None]] | None = None,
    ) -> None:
        self._worker_count = max(1, worker_count)
        self._backend = backend or InMemoryJobQueue()
        self._run_job_handler = run_job_handler
        self._workers: list[asyncio.Task] = []
        self._started = False

    @property
    def worker_count(self) -> int:
        return self._worker_count

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def pending_jobs(self) -> int:
        return self._backend.pending_jobs

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._backend.mark_started()
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"run-queue-worker-{index}")
            for index in range(self._worker_count)
        ]

    async def submit(self, job: Job, *, label: str) -> None:
        if not self._started:
            raise RuntimeError("RunExecutionQueue 가 시작되지 않았습니다.")
        await self._backend.submit(job, label=label)

    async def enqueue_run_job(self, descriptor: RunJobDescriptor) -> None:
        if not self._started:
            raise RuntimeError("RunExecutionQueue 가 시작되지 않았습니다.")
        await self._backend.enqueue_run_job(descriptor)

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._started = False

    async def join(self) -> None:
        await self._backend.join()

    async def _worker(self, index: int) -> None:
        while True:
            item = await self._backend.get()
            try:
                if isinstance(item, RunJobDescriptor):
                    if self._run_job_handler is None:
                        raise RuntimeError("RunJobDescriptor 핸들러가 설정되지 않았습니다.")
                    await self._run_job_handler(item)
                else:
                    job, label = item
                    await job()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                label = item.label if isinstance(item, RunJobDescriptor) else item[1]
                logger.exception(
                    "실행 큐 작업 오류",
                    log_event="queue.job_failed",
                    worker_index=index,
                    job_label=label,
                    error=str(exc),
                )
            finally:
                self._backend.task_done()
