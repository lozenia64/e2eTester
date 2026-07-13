"""Tests for app.platform.redis_health."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.platform.redis_health import (
    DEFAULT_REDIS_URL,
    ping_redis,
    redis_port_from_url,
    redis_url_from_env,
    wait_for_redis,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("redis://127.0.0.1:6379/0", 6379),
        ("redis://localhost:6380", 6380),
        ("redis://127.0.0.1", 6379),
    ],
)
def test_redis_port_from_url(url: str, expected: int) -> None:
    assert redis_port_from_url(url) == expected


def test_redis_url_from_env_default() -> None:
    assert redis_url_from_env({}) == DEFAULT_REDIS_URL


def test_redis_url_from_env_override() -> None:
    assert redis_url_from_env({"E2E_REDIS_URL": "redis://10.0.0.1:6399/1"}) == (
        "redis://10.0.0.1:6399/1"
    )


def test_ping_redis_success() -> None:
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    with patch("app.platform.redis_health.connect_redis", return_value=mock_client):
        assert ping_redis("redis://127.0.0.1:6379/0") is True


def test_ping_redis_failure() -> None:
    with patch("app.platform.redis_health.connect_redis", side_effect=ConnectionError("refused")):
        assert ping_redis("redis://127.0.0.1:6379/0") is False


def test_wait_for_redis_eventually_ready() -> None:
    with patch("app.platform.redis_health.ping_redis", side_effect=[False, False, True]):
        assert wait_for_redis("redis://127.0.0.1:6379/0", timeout_sec=1.0) is True


def test_wait_for_redis_timeout() -> None:
    with patch("app.platform.redis_health.ping_redis", return_value=False):
        assert wait_for_redis("redis://127.0.0.1:6379/0", timeout_sec=0.3) is False
