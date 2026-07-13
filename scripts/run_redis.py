#!/usr/bin/env python3
"""로컬 Redis 기동 — 영속 파일(dump.rdb)을 redis-data/ 에 둔다.

Redis 를 작업 디렉터리에서 그대로 실행하면 프로젝트 루트에 dump.rdb 가 생긴다.
SQLite 앱 DB(`data/e2etester.db`)와 분리하기 위해 redis-data/ 를 사용한다.

사용:
    python3 scripts/run_redis.py              # 포그라운드 (Ctrl+C 종료)
    python3 scripts/run_redis.py --daemonize yes   # 백그라운드 (redis-server 옵션 전달)

Docker 를 쓰는 경우 README 의 docker run 예시를 참고하세요.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REDIS_DATA_DIR = ROOT / "redis-data"
DEFAULT_PORT = 6379


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Redis with persistence under redis-data/")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "redis_args",
        nargs=argparse.REMAINDER,
        help="extra arguments passed to redis-server (prefix with --)",
    )
    args = parser.parse_args()

    REDIS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "redis-server",
        "--dir",
        str(REDIS_DATA_DIR),
        "--dbfilename",
        "dump.rdb",
        "--port",
        str(args.port),
        "--bind",
        "127.0.0.1",
        *args.redis_args,
    ]

    print(f"redis data dir: {REDIS_DATA_DIR}")
    print("launch:", " ".join(cmd))
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print(
            "redis-server 를 찾을 수 없습니다. "
            "Docker(`docker run ...`) 또는 OS 패키지로 Redis 를 설치하세요.",
            file=sys.stderr,
        )
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
