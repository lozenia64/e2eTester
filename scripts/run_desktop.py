#!/usr/bin/env python3
"""Windows 데스크탑 배포용 단일 진입점 — uvicorn API 만 기동한다.

``E2E_EXECUTION_MODE=local``(기본)에서 Playwright·SQLite·오케스트레이션은 모두 이 프로세스
안에서 동작한다. Redis·별도 worker 프로세스는 필요 없다.

사용:
    python3 scripts/run_desktop.py
    python3 scripts/run_desktop.py --port 3000
    python3 scripts/run_desktop.py --print   # 기동 없이 명령만 출력

개발/CI용 API+worker 동시 기동은 ``scripts/run_local.py``(remote 모드)를 참고하세요.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build_command(host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("E2E_EXECUTION_MODE", "local")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run e2eTester desktop (uvicorn only, local mode)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="print the command and environment without launching",
    )
    args = parser.parse_args()

    cmd = _build_command(args.host, args.port)
    env = _child_env()

    if args.print_only:
        print("command:", " ".join(cmd))
        print("execution_mode:", env.get("E2E_EXECUTION_MODE"))
        print("db_path:", env.get("E2E_DB_PATH", "(default data/e2etester.db)"))
        return 0

    os.chdir(ROOT)
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
