"""Tests for port cleanup parsing and PID filtering."""

from __future__ import annotations

import os

from app.platform.port_cleanup import _WIN_LISTEN_RE, find_listening_pids, free_port


def test_windows_netstat_line_parsing() -> None:
    line = "  TCP    0.0.0.0:8100           0.0.0.0:0              LISTENING       2216"
    match = _WIN_LISTEN_RE.match(line)
    assert match is not None
    assert int(match.group("port")) == 8100
    assert int(match.group("pid")) == 2216


def test_find_listening_pids_skips_current_process(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.port_cleanup._pids_listening_on_port_windows",
        lambda port: [os.getpid()],
    )
    assert find_listening_pids(8100) == [os.getpid()]


def test_free_port_does_not_kill_self(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.platform.port_cleanup.find_listening_pids",
        lambda port: [os.getpid()],
    )
    assert free_port(8100) == []
