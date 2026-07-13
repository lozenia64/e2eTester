from __future__ import annotations

from collections.abc import Awaitable, Callable

import redis.asyncio as redis

from app.core.logging import get_logger
from app.execution.job_queue_port import Job, RunJobDescriptor
from app.platform.redis_client import connect_redis_async

logger = get_logger(__name__)

# Run 작업 Redis Stream 키·소비자 그룹.
RUN_JOBS_STREAM = "e2e:run-jobs"
RUN_JOBS_GROUP = "e2e-workers"


class RedisJobQueue:
    """Redis Streams 기반 Run 작업 브로커(API 프로세스 측 생산자).

    ``enqueue_run_job`` 으로 직렬화 가능한 작업 설명자를 스트림에 적재하고, API 측
    ``ProfilePartitionedRunQueue`` 워커가 소비해 인터프리터를 in-process 로 구동한다(브라우저
    스텝만 ``WorkerExecutionGateway`` 로 씬 워커에 위임 — Run 오케스트레이션은 API 소유).
    코루틴 팩토리는 프로세스 경계를 넘길 수 없으므로 ``submit`` 은 원격 모드에서 지원하지 않는다.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        stream_key: str = RUN_JOBS_STREAM,
        lease_ttl_ms: int = 60_000,
    ) -> None:
        self._redis_url = redis_url
        self._stream_key = stream_key
        # 리스 TTL: 이 시간 이상 미확정(idle)인 메시지는 죽은 소비자 소유로 보고 XAUTOCLAIM 재청구.
        self._lease_ttl_ms = lease_ttl_ms
        self._client: redis.Redis | None = None
        self._worker_count = 0
        self._started = False

    @property
    def worker_count(self) -> int:
        return self._worker_count

    @property
    def is_running(self) -> bool:
        return self._started

    async def pending_count(self) -> int:
        """스트림의 미확정 작업 수(XPENDING 조회 — 인메모리 카운터 대신 Redis 가 권위)."""
        if not self._started:
            return 0
        client = await self._get_client()
        try:
            summary = await client.xpending(self._stream_key, RUN_JOBS_GROUP)
        except redis.ResponseError:
            return 0
        # xpending summary: {'pending': N, ...} (그룹 미존재 시 0).
        return int(summary.get("pending", 0)) if isinstance(summary, dict) else 0

    def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = connect_redis_async(self._redis_url, decode_responses=True)
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
        """워커 측 소비 루프 — ``handler`` 로 작업을 위임한다.

        리스 기반 잡 소유권(WP-C3): 매 순회에서 먼저 ``XAUTOCLAIM``(min-idle-time = lease TTL)로
        죽은 소비자가 붙잡고 있던(=lease TTL 이상 미확정) 메시지를 재청구해 처리한다. ``XACK`` 은
        **핸들러 성공 후에만** 호출하므로, 처리 중 소비자가 죽으면 메시지가 pending 으로 남아
        다른 소비자가 XAUTOCLAIM 으로 이어받는다(자동 재전달). 실패한 잡도 ack 되지 않아 재청구된다.
        """
        await self.ensure_consumer_group()
        client = await self._get_client()
        while True:
            reclaimed = await self._reclaim_idle(client, consumer_name, handler)
            messages = await client.xreadgroup(
                RUN_JOBS_GROUP,
                consumer_name,
                {self._stream_key: ">"},
                count=1,
                block=block_ms,
            )
            if not messages and not reclaimed:
                continue
            for _stream, entries in messages:
                for message_id, fields in entries:
                    await self._process(client, message_id, fields, handler)

    async def _reclaim_idle(self, client, consumer_name, handler) -> bool:
        """죽은 소비자의 idle 메시지를 XAUTOCLAIM 으로 재청구·처리한다(있으면 True)."""
        try:
            result = await client.xautoclaim(
                self._stream_key,
                RUN_JOBS_GROUP,
                consumer_name,
                min_idle_time=self._lease_ttl_ms,
                count=10,
            )
        except redis.ResponseError:
            return False
        # xautoclaim → (next_cursor, [(message_id, fields), ...], [deleted_ids]) (버전별 2~3튜플).
        entries = result[1] if len(result) >= 2 else []
        for message_id, fields in entries:
            if not fields:  # 삭제됐지만 아직 pending 인 유령 메시지 — 그냥 ack.
                await client.xack(self._stream_key, RUN_JOBS_GROUP, message_id)
                continue
            await self._process(client, message_id, fields, handler)
        return bool(entries)

    async def _process(self, client, message_id, fields, handler) -> None:
        descriptor = RunJobDescriptor(
            run_id=fields["run_id"],
            kind=fields["kind"],  # type: ignore[arg-type]
            start_index=int(fields.get("start_index", "0")),
            label=fields.get("label", ""),
        )
        try:
            await handler(descriptor)
        except Exception as exc:
            # ack 하지 않는다 — 메시지는 pending 으로 남아 XAUTOCLAIM 으로 재전달된다.
            logger.exception(
                "Redis 작업 처리 오류(미확정 유지 — 재전달 대상)",
                log_event="redis_job.failed",
                run_id=descriptor.run_id,
                error=str(exc),
            )
            return
        # 성공(=잡 완료/체크포인트 확정)한 뒤에만 확정한다.
        await client.xack(self._stream_key, RUN_JOBS_GROUP, message_id)
