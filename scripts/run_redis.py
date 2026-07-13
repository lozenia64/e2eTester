#!/usr/bin/env python3
"""로컬 Redis 기동 — 영속 파일(dump.rdb)을 redis-data/ 에 둔다.

Redis 를 작업 디렉터리에서 그대로 실행하면 프로젝트 루트에 dump.rdb 가 생긴다.
SQLite 앱 DB(`data/e2etester.db`)와 분리하기 위해 redis-data/ 를 사용한다.

사용:
    python3 scripts/run_redis.py              # 포그라운드 (Ctrl+C 종료)
    python3 scripts/run_redis.py --daemonize yes   # 백그라운드 (redis-server 옵션 전달)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.redis_discovery import redis_not_found_message, resolve_redis_server  # noqa: E402
from app.platform.redis_health import ping_redis  # noqa: E402
from app.platform.stdio_utf8 import configure_stdio_utf8  # noqa: E402

REDIS_DATA_DIR = ROOT / "redis-data"
DEFAULT_PORT = 6379


def _redis_bind_args() -> list[str]:
    # Windows Redis rejects --bind 127.0.0.1 with "No such file or directory".
    if sys.platform == "win32":
        return []
    return ["--bind", "127.0.0.1"]


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser(description="Start Redis with persistence under redis-data/")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--executable",
        default=None,
        help="redis-server executable path (auto-discovered when omitted)",
    )
    parser.add_argument(
        "redis_args",
        nargs=argparse.REMAINDER,
        help="extra arguments passed to redis-server (prefix with --)",
    )
    args = parser.parse_args()

    redis_url = f"redis://127.0.0.1:{args.port}/0"
    if ping_redis(redis_url):
        print(f"Redis already listening on port {args.port}", file=sys.stderr)
        return 0

    redis_server = resolve_redis_server(override=args.executable)
    if not redis_server:
        print(redis_not_found_message(), file=sys.stderr)
        return 127

    REDIS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        redis_server,
        "--dir",
        str(REDIS_DATA_DIR),
        "--dbfilename",
        "dump.rdb",
        "--port",
        str(args.port),
        *_redis_bind_args(),
        *args.redis_args,
    ]

    print(f"redis data dir: {REDIS_DATA_DIR}")
    print("launch:", " ".join(cmd))
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print(redis_not_found_message(), file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
