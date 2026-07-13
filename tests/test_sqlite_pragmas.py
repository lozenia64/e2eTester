"""SQLite PRAGMA SSOT smoke test."""

from __future__ import annotations

import sqlite3

from app.storage.sqlite_pragmas import apply_sqlite_pragmas


def test_apply_sqlite_pragmas_sets_wal_and_busy_timeout(tmp_path):
    db_path = tmp_path / "pragma.db"
    conn = sqlite3.connect(db_path)
    apply_sqlite_pragmas(conn)

    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]

    conn.close()

    assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000
    assert synchronous == 1  # NORMAL
    assert foreign_keys == 1
