from __future__ import annotations

import asyncio

from app.contexts.run.application.service import RunService
from app.core.logging import get_logger
from app.execution.job_queue_port import RunJobDescriptor
from app.execution.redis_job_queue import RedisJobQueue

logger = get_logger(__name__)


class RunJobConsumer:
    """Redis Streams 에서 Run 작업을 소비해 ``RunService`` 로 실행한다."""

    def __init__(
        self,
        redis_queue: RedisJobQueue,
        run_service: RunService,
        *,
        consumer_name: str,
        worker_count: int = 1,
    ) -> None:
        self._redis_queue = redis_queue
        self._run_service = run_service
        self._consumer_name = consumer_name
        self._worker_count = max(1, worker_count)
        self._tasks: list[asyncio.Task] = []

    async def _handle_descriptor(self, descriptor: RunJobDescriptor) -> None:
        try:
            await self._run_service.dispatch_run_job(descriptor)
        except KeyError as exc:
            logger.warning(
                "작업 스킵",
                log_event="worker.job_skipped",
                run_id=descriptor.run_id,
                error=str(exc),
            )

    def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(
                self._consume_loop(consumer_name=f"{self._consumer_name}-{index}"),
                name=f"run-job-consumer-{index}",
            )
            for index in range(self._worker_count)
        ]

    async def stop(self) -> None:
        if not self._tasks:
            return
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _consume_loop(self, *, consumer_name: str) -> None:
        await self._redis_queue.consume(
            self._handle_descriptor,
            consumer_name=consumer_name,
        )
