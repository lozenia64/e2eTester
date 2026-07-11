from __future__ import annotations

from collections.abc import Awaitable, Callable

import redis.asyncio as redis

from app.core.logging import get_logger
from app.execution.job_queue_port import Job, RunJobDescriptor

logger = get_logger(__name__)

# Run 작업 Redis Stream 키·소비자 그룹.
RUN_JOBS_STREAM = "e2e:run-jobs"
RUN_JOBS_GROUP = "e2e-workers"


class RedisJobQueue:
    """Redis Streams 기반 Run 작업 브로커(API 프로세스 측 생산자).

    ``enqueue_run_job`` 으로 직렬화 가능한 작업 설명자를 스트림에 적재하고,
    별도 워커 프로세스(``worker/job_consumer``)가 소비한다. 코루틴 팩토리는
    프로세스 경계를 넘길 수 없으므로 ``submit`` 은 원격 모드에서 지원하지 않는다.
    """

    def __init__(self, redis_url: str, *, stream_key: str = RUN_JOBS_STREAM) -> None:
        self._redis_url = redis_url
        self._stream_key = stream_key
        self._client: redis.Redis | None = None
        self._worker_count = 0
        self._started = False
        self._pending = 0

    @property
    def worker_count(self) -> int:
        return self._worker_count

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def pending_jobs(self) -> int:
        return self._pending

    def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def submit(self, job: Job, *, label: str) -> None:
        raise RuntimeError(
            "RedisJobQueue 는 코루틴 작업을 직접 받지 않습니다. enqueue_run_job 을 사용하세요."
        )

    async def enqueue_run_job(self, descriptor: RunJobDescriptor) -> None:
        if not self._started:
            raise RuntimeError("RedisJobQueue 가 시작되지 않았습니다.")
        client = await self._get_client()
        payload = {
            "run_id": descriptor.run_id,
            "kind": descriptor.kind,
            "start_index": str(descriptor.start_index),
            "label": descriptor.label or f"run:{descriptor.run_id}",
        }
        await client.xadd(self._stream_key, payload)
        self._pending += 1

    async def ensure_consumer_group(self) -> None:
        """소비자 그룹을 보장한다(워커 부트스트랩용)."""
        client = await self._get_client()
        try:
            await client.xgroup_create(self._stream_key, RUN_JOBS_GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume(
        self,
        handler: Callable[[RunJobDescriptor], Awaitable[None]],
        *,
        consumer_name: str,
        block_ms: int = 5000,
    ) -> None:
        """워커 측 소비 루프 — ``handler`` 로 작업을 위임한다."""
        await self.ensure_consumer_group()
        client = await self._get_client()
        while True:
            messages = await client.xreadgroup(
                RUN_JOBS_GROUP,
                consumer_name,
                {self._stream_key: ">"},
                count=1,
                block=block_ms,
            )
            if not messages:
                continue
            for _stream, entries in messages:
                for message_id, fields in entries:
                    descriptor = RunJobDescriptor(
                        run_id=fields["run_id"],
                        kind=fields["kind"],  # type: ignore[arg-type]
                        start_index=int(fields.get("start_index", "0")),
                        label=fields.get("label", ""),
                    )
                    try:
                        await handler(descriptor)
                    except Exception as exc:
                        logger.exception(
                            "Redis 작업 처리 오류",
                            log_event="redis_job.failed",
                            run_id=descriptor.run_id,
                            error=str(exc),
                        )
                    finally:
                        await client.xack(self._stream_key, RUN_JOBS_GROUP, message_id)
                        self._pending = max(0, self._pending - 1)
