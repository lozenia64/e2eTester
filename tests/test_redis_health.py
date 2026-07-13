"""Tests for app.platform.redis_health."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.platform.redis_health import (
    DEFAULT_REDIS_URL,
    ensure_redis_ready,
    is_local_redis_url,
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


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("redis://127.0.0.1:6379/0", True),
        ("redis://localhost:6380", True),
        ("redis://10.0.0.1:6399/1", False),
    ],
)
def test_is_local_redis_url(url: str, expected: bool) -> None:
    assert is_local_redis_url(url) is expected


def test_ensure_redis_ready_rejects_remote_host(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.platform.redis_health.ping_redis", lambda url: False)
    with pytest.raises(RuntimeError, match="원격 호스트"):
        ensure_redis_ready(
            {"E2E_REDIS_URL": "redis://10.0.0.1:6399/1"},
            root=tmp_path,
        )


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


def test_ensure_redis_ready_passes_port_from_url(tmp_path, monkeypatch) -> None:
    from app.platform.redis_health import ensure_redis_ready

    launched: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs) -> MagicMock:
        launched.append(cmd)
        return MagicMock()

    monkeypatch.setattr("app.platform.redis_health.resolve_redis_server", lambda: "redis-server")
    monkeypatch.setattr("app.platform.redis_health.ping_redis", lambda url: False)
    monkeypatch.setattr("app.platform.redis_health.wait_for_redis", lambda url, **kw: True)
    monkeypatch.setattr("app.platform.redis_health.popen_managed", fake_popen)

    ensure_redis_ready(
        {"E2E_REDIS_URL": "redis://127.0.0.1:6380/0"},
        root=tmp_path,
    )
    assert launched
    assert launched[0][-2:] == ["--port", "6380"]
