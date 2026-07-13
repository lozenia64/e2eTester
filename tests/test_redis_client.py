"""Tests for app.platform.redis_client."""

from __future__ import annotations

from unittest.mock import patch

from app.platform.redis_client import connect_redis, connect_redis_async


def test_connect_redis_uses_resp2() -> None:
    with patch("app.platform.redis_client.redis.from_url") as from_url:
        connect_redis("redis://127.0.0.1:6379/0", socket_connect_timeout=1.0)
    from_url.assert_called_once_with(
        "redis://127.0.0.1:6379/0",
        decode_responses=False,
        protocol=2,
        socket_connect_timeout=1.0,
    )


def test_connect_redis_async_uses_resp2() -> None:
    with patch("app.platform.redis_client.redis_async.from_url") as from_url:
        connect_redis_async("redis://127.0.0.1:6379/0", decode_responses=True)
    from_url.assert_called_once_with(
        "redis://127.0.0.1:6379/0",
        decode_responses=True,
        protocol=2,
    )
