"""Redis PUBLISH/SUBSCRIBE 기반 크로스 인스턴스 실시간 fan-out."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import redis.asyncio as redis

from app.core.logging import get_logger
from app.platform.redis_client import connect_redis_async

logger = get_logger(__name__)

_CHANNEL_PREFIX = "e2e:realtime:"


class RedisRealtimeFanOut:
    """``RealtimeFanOutPort`` Redis 구현."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._handlers: dict[str, list[Callable[[str], Awaitable[None]]]] = {}
        self._listener_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Redis 연결·pubsub 준비. 수신 루프는 첫 ``subscribe`` 이후에만 시작한다."""
        if self._running:
            return
        self._client = connect_redis_async(self._redis_url, decode_responses=True)
        await self._client.ping()
        self._pubsub = self._client.pubsub()
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._pubsub is not None:
            await self._pubsub.close()
            self._pubsub = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, channel: str, payload: str) -> None:
        if self._client is None:
            return
        await self._client.publish(f"{_CHANNEL_PREFIX}{channel}", payload)

    async def subscribe(self, channel: str, handler: Callable[[str], Awaitable[None]]) -> None:
        if not self._running or self._pubsub is None:
            raise RuntimeError("RedisRealtimeFanOut.start() must be called before subscribe()")
        key = f"{_CHANNEL_PREFIX}{channel}"
        self._handlers.setdefault(key, []).append(handler)
        await self._pubsub.subscribe(key)
        if self._listener_task is None:
            self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        if self._pubsub is None:
            return
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None or message.get("type") != "message":
                    continue
                channel = message.get("channel")
                data = message.get("data")
                if not isinstance(channel, str) or not isinstance(data, str):
                    continue
                for handler in list(self._handlers.get(channel, [])):
                    try:
                        await handler(data)
                    except Exception:
                        logger.exception(
                            "Redis fan-out 핸들러 오류",
                            log_event="realtime.fanout_handler_failed",
                            channel=channel,
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Redis fan-out 수신 루프 오류", log_event="realtime.fanout_loop_failed"
                )
                await asyncio.sleep(0.5)


def serialize_dashboard_event(event) -> str:
    return json.dumps(event.model_dump(mode="json"), ensure_ascii=False)


def deserialize_dashboard_event(data: str):
    from app.core.run_models import DashboardEvent

    return DashboardEvent.model_validate(json.loads(data))


def serialize_suite_event(event) -> str:
    return json.dumps(event.model_dump(mode="json"), ensure_ascii=False)


def deserialize_suite_event(data: str):
    from app.core.suite_models import SuiteEvent

    return SuiteEvent.model_validate(json.loads(data))
