"""Tests for SSOT SQLite connection factory and lock-contention tolerance."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from app.platform.sqlite_connection import connect_sqlite


def _pragma_int(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute(f"PRAGMA {name}").fetchone()
    assert row is not None
    return int(row[0])


def test_connect_sqlite_applies_production_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "pragmas.db"
    conn = connect_sqlite(db_path, busy_timeout_ms=7500)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        assert _pragma_int(conn, "busy_timeout") == 7500
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_concurrent_writes_succeed_with_busy_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.db"
    conn_a = connect_sqlite(db_path, busy_timeout_ms=5000)
    conn_a.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v INTEGER)")
    conn_a.commit()

    errors: list[Exception] = []

    def writer(name: str, delay: float) -> None:
        conn = connect_sqlite(db_path, busy_timeout_ms=5000)
        try:
            conn.execute("BEGIN IMMEDIATE")
            time.sleep(delay)
            conn.execute(
                "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                (name, 1),
            )
            conn.commit()
        except Exception as exc:
            errors.append(exc)
        finally:
            conn.close()

    t1 = threading.Thread(target=writer, args=("a", 0.3))
    t2 = threading.Thread(target=writer, args=("b", 0.0))
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, errors
    verify = connect_sqlite(db_path)
    try:
        count = verify.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
        assert count == 2
    finally:
        verify.close()


def test_immediate_write_waits_for_busy_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "wait.db"
    holder = connect_sqlite(db_path, busy_timeout_ms=2000)
    holder.execute("CREATE TABLE IF NOT EXISTS hold (id INTEGER PRIMARY KEY)")
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO hold (id) VALUES (1)")

    waiter_errors: list[Exception] = []
    finished = threading.Event()

    def waiter() -> None:
        conn = connect_sqlite(db_path, busy_timeout_ms=3000)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO hold (id) VALUES (2)")
            conn.commit()
        except Exception as exc:
            waiter_errors.append(exc)
        finally:
            conn.close()
            finished.set()

    thread = threading.Thread(target=waiter)
    time.sleep(0.05)
    thread.start()
    time.sleep(0.25)
    holder.commit()
    holder.close()
    thread.join(timeout=5)

    assert finished.is_set()
    assert not waiter_errors, waiter_errors


def test_resolve_busy_timeout_ms_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("E2E_SQLITE_BUSY_TIMEOUT_MS", "8000")
    from app.core.settings import clear_settings_cache
    from app.platform.sqlite_connection import resolve_busy_timeout_ms

    clear_settings_cache()
    assert resolve_busy_timeout_ms() == 8000
    clear_settings_cache()
