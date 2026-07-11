from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.execution.job_queue_port import RunJobDescriptor
from app.execution.redis_job_queue import RedisJobQueue
from app.orchestrator.run_service import RunService

logger = get_logger(__name__)


class RunJobConsumer:
    """Redis Streams 에서 Run 작업을 소비해 ``RunService`` 로 실행한다."""

    def __init__(
        self,
        redis_queue: RedisJobQueue,
        run_service: RunService,
        *,
        consumer_name: str,
    ) -> None:
        self._redis_queue = redis_queue
        self._run_service = run_service
        self._consumer_name = consumer_name
        self._task: asyncio.Task | None = None

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
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._consume_loop(), name="run-job-consumer")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _consume_loop(self) -> None:
        await self._redis_queue.consume(
            self._handle_descriptor,
            consumer_name=self._consumer_name,
        )
