#!/usr/bin/env python3
"""Thin wrapper around the Orca CLI for dev-verify loop scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any


def configure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


def resolve_orca_executable() -> str:
    env = os.environ.get("ORCA_CLI_COMMAND")
    if env:
        return env
    if os.environ.get("ORCA_DEV_REPO_ROOT"):
        return "orca-dev"
    return "orca"


def run_orca(args: list[str], *, timeout_sec: int | None = None) -> dict[str, Any]:
    cmd = [resolve_orca_executable(), *args]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
        env=env,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if not stdout:
        return {
            "ok": False,
            "exit_code": proc.returncode,
            "error": stderr or "empty stdout from orca",
            "command": cmd,
        }
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "exit_code": proc.returncode,
            "error": f"invalid JSON: {exc}",
            "stdout": stdout,
            "stderr": stderr,
            "command": cmd,
        }
    data.setdefault("exit_code", proc.returncode)
    return data


def require_ok(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get("ok"):
        msg = data.get("error") or data.get("result") or data
        raise RuntimeError(f"orca command failed: {msg}")
    return data


def orca_available() -> bool:
    exe = resolve_orca_executable()
    return shutil.which(exe) is not None
