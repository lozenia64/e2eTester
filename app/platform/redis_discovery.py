"""Locate a redis-server executable across macOS, Linux, and Windows installs."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _windows_candidates() -> list[Path]:
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    return [
        Path(program_files) / "Redis" / "redis-server.exe",
        Path(program_files_x86) / "Redis" / "redis-server.exe",
        Path(r"C:\ProgramData\chocolatey\lib\redis-64\tools\redis-server.exe"),
        Path(program_files) / "Memurai" / "memurai-server.exe",
    ]


def resolve_redis_server(*, override: str | None = None) -> str | None:
    if override:
        path = Path(override)
        return str(path) if path.exists() else override

    found = shutil.which("redis-server")
    if found:
        return found

    if sys.platform == "win32":
        for candidate in _windows_candidates():
            if candidate.is_file():
                return str(candidate)

    return None


def redis_not_found_message() -> str:
    lines = [
        "redis-server 를 찾을 수 없습니다.",
        "",
        "Windows: winget install Redis.Redis 또는 Memurai 설치 후 PATH 등록",
        "macOS: brew install redis",
        "Linux: sudo apt-get install redis-server",
        "",
        "또는 python3 scripts/run_redis.py 로 기동하거나",
        "--executable 로 redis-server 경로를 직접 지정하세요.",
    ]
    return "\n".join(lines)
