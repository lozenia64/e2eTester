"""Shared Redis client factory.

redis-py 8 defaults to RESP3 (HELLO handshake). Windows Redis builds
(tporadowski/winget) often support only RESP2 — force protocol 2 everywhere.
"""

from __future__ import annotations

import redis
import redis.asyncio as redis_async

_RESP2 = 2


def connect_redis(
    redis_url: str,
    *,
    decode_responses: bool = False,
    socket_connect_timeout: float | None = None,
) -> redis.Redis:
    kwargs: dict = {"decode_responses": decode_responses, "protocol": _RESP2}
    if socket_connect_timeout is not None:
        kwargs["socket_connect_timeout"] = socket_connect_timeout
    return redis.from_url(redis_url, **kwargs)


def connect_redis_async(
    redis_url: str,
    *,
    decode_responses: bool = False,
) -> redis_async.Redis:
    return redis_async.from_url(redis_url, decode_responses=decode_responses, protocol=_RESP2)
