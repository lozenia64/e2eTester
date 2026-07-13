"""Redis reachability checks and optional local auto-start for run_local.py."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from app.platform.process_lifecycle import graceful_shutdown, popen_managed
from app.platform.redis_client import connect_redis
from app.platform.redis_discovery import redis_not_found_message, resolve_redis_server

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
_LOCAL_REDIS_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def redis_url_from_env(env: dict[str, str]) -> str:
    return env.get("E2E_REDIS_URL", DEFAULT_REDIS_URL)


def redis_port_from_url(redis_url: str) -> int:
    parsed = urlparse(redis_url)
    if parsed.port is not None:
        return parsed.port
    return 6379


def is_local_redis_url(redis_url: str) -> bool:
    """True when auto-starting a local redis-server could satisfy the URL."""
    parsed = urlparse(redis_url)
    host = (parsed.hostname or "127.0.0.1").lower()
    return host in _LOCAL_REDIS_HOSTS or host.endswith(".localhost")


def ping_redis(redis_url: str, *, connect_timeout_sec: float = 1.0) -> bool:
    try:
        client = connect_redis(redis_url, socket_connect_timeout=connect_timeout_sec)
        return bool(client.ping())
    except Exception:
        return False


def wait_for_redis(redis_url: str, *, timeout_sec: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if ping_redis(redis_url):
            return True
        time.sleep(0.25)
    return False


def ensure_redis_ready(
    env: dict[str, str],
    *,
    root: Path,
    start_if_missing: bool = True,
    timeout_sec: float = 15.0,
) -> subprocess.Popen | None:
    """Return a Redis child process when this call started it, else None."""
    redis_url = redis_url_from_env(env)
    if ping_redis(redis_url):
        return None
    if not start_if_missing:
        msg = (
            f"Redis 에 연결할 수 없습니다 ({redis_url}). "
            "scripts/run_redis.py 를 먼저 실행하거나 redis-server 를 설치하세요."
        )
        raise RuntimeError(msg)
    if not is_local_redis_url(redis_url):
        msg = (
            f"Redis 에 연결할 수 없습니다 ({redis_url}). "
            "원격 호스트는 자동 기동을 지원하지 않습니다. "
            "Redis 서버를 직접 기동하거나 E2E_REDIS_URL 을 localhost 로 설정하세요."
        )
        raise RuntimeError(msg)
    if resolve_redis_server() is None:
        raise RuntimeError(redis_not_found_message())

    port = redis_port_from_url(redis_url)
    proc = popen_managed(
        [sys.executable, str(root / "scripts" / "run_redis.py"), "--port", str(port)],
        cwd=str(root),
        env=env,
    )
    if not wait_for_redis(redis_url, timeout_sec=timeout_sec):
        graceful_shutdown(proc)
        msg = (
            f"Redis 가 제한 시간 내에 기동되지 않았습니다 ({redis_url}). "
            "redis-server 설치·PATH 를 확인하세요."
        )
        raise RuntimeError(msg)
    print(f"started Redis ({redis_url})", file=sys.stderr)
    return proc
