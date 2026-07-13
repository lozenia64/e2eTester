"""Cross-platform helpers to release TCP listen ports before local process launch."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Iterable

_WIN_LISTEN_RE = re.compile(
    r"^\s*TCP\s+\S+:(?P<port>\d+)\s+\S+\s+LISTENING\s+(?P<pid>\d+)\s*$",
    re.IGNORECASE,
)


def _pids_listening_on_port_windows(port: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []

    pids: set[int] = set()
    for line in proc.stdout.splitlines():
        match = _WIN_LISTEN_RE.match(line)
        if match is None or int(match.group("port")) != port:
            continue
        pids.add(int(match.group("pid")))
    return sorted(pids)


def _pids_listening_on_port_unix(port: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for token in proc.stdout.split():
        if token.isdigit():
            pids.append(int(token))
    return sorted(set(pids))


def find_listening_pids(port: int) -> list[int]:
    """Return PIDs listening on ``port`` (empty when none or unsupported)."""
    if port <= 0:
        return []
    if sys.platform == "win32":
        return _pids_listening_on_port_windows(port)
    return _pids_listening_on_port_unix(port)


def _kill_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if sys.platform == "win32":
        proc = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0

    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return True


def free_port(port: int) -> list[int]:
    """Terminate processes listening on ``port``. Returns killed PIDs."""
    killed: list[int] = []
    for pid in find_listening_pids(port):
        if _kill_pid(pid):
            killed.append(pid)
    return killed


def free_ports(ports: Iterable[int]) -> dict[int, list[int]]:
    """Release multiple ports. Returns mapping port → killed PIDs."""
    result: dict[int, list[int]] = {}
    for port in sorted({int(p) for p in ports}):
        result[port] = free_port(port)
    return result
