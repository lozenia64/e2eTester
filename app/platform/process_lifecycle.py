"""Cross-platform subprocess lifecycle helpers."""

from __future__ import annotations

import signal
import subprocess
import sys


def popen_managed(cmd: list[str], *, cwd: str, env: dict[str, str]) -> subprocess.Popen:
    """Start a child process with platform-appropriate process-group semantics."""
    if sys.platform == "win32":
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True)


def graceful_shutdown(proc: subprocess.Popen, *, timeout: float = 10) -> None:
    """Terminate a managed child process; escalate to kill on timeout."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except (AttributeError, OSError, ValueError):
            proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)
