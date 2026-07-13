#!/usr/bin/env python3
"""로컬 통합 기동기 — API 프로세스 + 워커 프로세스를 함께 띄운다(WP-C1).

이상 구조에서는 실행 평면이 분리돼(API 에는 Playwright/실행 스레드가 없다) Redis 가 전 모드
필수 인프라가 된다. 이 스크립트는 같은 머신에서 (1) uvicorn API 와 (2) ``python -m worker.main``
워커를 동시에 기동하고 수명을 함께 관리한다(한쪽이 죽으면 다른 쪽도 정리). 실행 모드는
``E2E_EXECUTION_MODE=remote`` 로 강제해 API 가 ``WorkerExecutionGateway`` 로 워커에 위임하게 한다.

사용:
    python3 scripts/run_local.py                 # Redis 자동 기동 + API :2222 + worker :8100
    python3 scripts/run_local.py --no-start-redis  # Redis 는 별도로 기동한 경우
    python3 scripts/run_local.py --api-port 3000 --worker-port 8200
    python3 scripts/run_local.py --print         # 실제 기동 없이 실행할 명령만 출력(스모크)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.port_cleanup import free_ports  # noqa: E402
from app.platform.process_lifecycle import graceful_shutdown, popen_managed  # noqa: E402
from app.platform.redis_health import ensure_redis_ready  # noqa: E402


def _build_commands(api_host: str, api_port: int, worker_port: int) -> list[list[str]]:
    api = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        api_host,
        "--port",
        str(api_port),
    ]
    worker = [sys.executable, "-m", "worker.main"]
    return [api, worker]


def _child_env(worker_port: int) -> dict[str, str]:
    env = os.environ.copy()
    # 실행 평면 분리: API 는 원격 게이트웨이로 워커에 위임한다(Redis 필수).
    env.setdefault("E2E_EXECUTION_MODE", "remote")
    env.setdefault("E2E_WORKER_HTTP_PORT", str(worker_port))
    env.setdefault("E2E_WORKER_BASE_URL", f"http://127.0.0.1:{worker_port}")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API + worker locally (WP-C1)")
    parser.add_argument("--api-host", default="0.0.0.0")
    parser.add_argument("--api-port", type=int, default=2222)
    parser.add_argument("--worker-port", type=int, default=8100)
    parser.add_argument(
        "--no-start-redis",
        action="store_true",
        help="do not auto-start Redis when E2E_REDIS_URL is unreachable",
    )
    parser.add_argument(
        "--no-free-ports",
        action="store_true",
        help="skip killing processes that already listen on api/worker ports",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="print the commands and environment without launching (smoke check)",
    )
    args = parser.parse_args()

    commands = _build_commands(args.api_host, args.api_port, args.worker_port)
    env = _child_env(args.worker_port)

    if args.print_only:
        print("execution_mode:", env["E2E_EXECUTION_MODE"])
        print("worker_base_url:", env["E2E_WORKER_BASE_URL"])
        for cmd in commands:
            print("launch:", " ".join(cmd))
        return 0

    if not args.no_free_ports:
        freed = free_ports([args.api_port, args.worker_port])
        for port, pids in freed.items():
            if pids:
                print(f"freed port {port}: terminated PIDs {pids}", file=sys.stderr)

    procs: list[subprocess.Popen] = []
    try:
        redis_proc = ensure_redis_ready(
            env,
            root=ROOT,
            start_if_missing=not args.no_start_redis,
        )
        if redis_proc is not None:
            procs.append(redis_proc)

        for cmd in commands:
            procs.append(popen_managed(cmd, cwd=str(ROOT), env=env))
        # 한 프로세스라도 종료하면 전체를 정리한다(수명 공동 관리).
        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"process exited (code={code}); shutting down siblings", file=sys.stderr)
                    return code or 0
            try:
                procs[0].wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        for proc in procs:
            graceful_shutdown(proc)


if __name__ == "__main__":
    raise SystemExit(main())
