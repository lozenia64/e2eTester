"""Tests for port cleanup parsing and PID filtering."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app.platform.port_cleanup import _WIN_LISTEN_RE, find_listening_pids, free_port


def test_windows_netstat_line_parsing() -> None:
    line = "  TCP    0.0.0.0:8100           0.0.0.0:0              LISTENING       2216"
    match = _WIN_LISTEN_RE.match(line)
    assert match is not None
    assert int(match.group("port")) == 8100
    assert int(match.group("pid")) == 2216


def test_find_listening_pids_returns_discovered_pids(monkeypatch) -> None:
    target = (
        "app.platform.port_cleanup._pids_listening_on_port_windows"
        if sys.platform == "win32"
        else "app.platform.port_cleanup._pids_listening_on_port_unix"
    )
    monkeypatch.setattr(target, lambda port: [os.getpid()])
    assert find_listening_pids(8100) == [os.getpid()]


def test_free_port_does_not_kill_self(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.port_cleanup.find_listening_pids",
        lambda port: [os.getpid()],
    )
    assert free_port(8100) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskkill semantics")
def test_kill_pid_windows_exits_after_graceful(monkeypatch) -> None:
    calls: list[list[str]] = []
    alive_checks = iter([True, False])

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "app.platform.port_cleanup._pid_exists", lambda pid: next(alive_checks, False)
    )
    monkeypatch.setattr("app.platform.port_cleanup.time.sleep", lambda _: None)

    from app.platform.port_cleanup import _kill_pid_windows

    assert _kill_pid_windows(2216) is True
    assert calls == [["taskkill", "/PID", "2216"]]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskkill semantics")
def test_kill_pid_windows_falls_back_to_force(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("app.platform.port_cleanup._pid_exists", lambda pid: True)
    monkeypatch.setattr("app.platform.port_cleanup.time.sleep", lambda _: None)

    from app.platform.port_cleanup import _kill_pid_windows

    assert _kill_pid_windows(2216) is True
    assert calls[0] == ["taskkill", "/PID", "2216"]
    assert calls[-1] == ["taskkill", "/F", "/PID", "2216"]
