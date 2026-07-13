from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as redis

from app.platform.redis_client import connect_redis_async

# Redis 키 접두사 — 세션 리스 목록/메타데이터.
_SESSION_KEY_PREFIX = "e2e:session:"


class RedisSessionRegistry:
    """원격 워커 브라우저 세션의 리스·하트비트를 Redis 에 기록한다.

    OTP 일시정지 후 API 프로세스가 재기동해도, 워커가 살아 있고 세션 리스가
    유효하면 ``reconcile_interrupted_runs`` 가 WAITING_INPUT Run 을 봉인하지 않는다.
    """

    def __init__(self, redis_url: str, lease_ttl_seconds: int = 60) -> None:
        self._redis_url = redis_url
        self._lease_ttl = max(5, lease_ttl_seconds)
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = connect_redis_async(self._redis_url, decode_responses=True)
        return self._client

    def _key(self, session_id: str) -> str:
        return f"{_SESSION_KEY_PREFIX}{session_id}"

    async def register(
        self,
        session_id: str,
        *,
        worker_id: str,
        run_id: str,
        execution_mode: str,
    ) -> None:
        """세션을 등록하고 TTL 리스를 시작한다."""
        client = await self._get_client()
        payload = {
            "worker_id": worker_id,
            "run_id": run_id,
            "execution_mode": execution_mode,
            "registered_at": datetime.now(UTC).isoformat(),
        }
        await client.set(self._key(session_id), json.dumps(payload), ex=self._lease_ttl)

    async def heartbeat(self, session_id: str) -> bool:
        """리스 TTL 을 갱신한다. 키가 없으면 False."""
        client = await self._get_client()
        key = self._key(session_id)
        if not await client.exists(key):
            return False
        await client.expire(key, self._lease_ttl)
        return True

    async def is_alive(self, session_id: str) -> bool:
        """세션 리스가 아직 유효한지 확인한다."""
        client = await self._get_client()
        return bool(await client.exists(self._key(session_id)))

    async def unregister(self, session_id: str) -> None:
        client = await self._get_client()
        await client.delete(self._key(session_id))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
