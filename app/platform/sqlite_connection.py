"""SSOT SQLite connection factory — WAL, busy_timeout, and production PRAGMA bundle."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_MS = 5000


def resolve_busy_timeout_ms() -> int:
    """Resolve lock-wait timeout from env or default (milliseconds)."""
    raw = os.environ.get("E2E_SQLITE_BUSY_TIMEOUT_MS")
    if raw is None or not str(raw).strip():
        try:
            from app.core.settings import get_settings

            return get_settings().sqlite_busy_timeout_ms
        except Exception:
            return DEFAULT_BUSY_TIMEOUT_MS
    try:
        value = int(str(raw).strip())
    except ValueError:
        return DEFAULT_BUSY_TIMEOUT_MS
    return max(0, value)


def connect_sqlite(
    db_path: str | Path,
    *,
    busy_timeout_ms: int | None = None,
    check_same_thread: bool = False,
) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and lock-contention tolerance."""
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    ms = busy_timeout_ms if busy_timeout_ms is not None else resolve_busy_timeout_ms()
    conn = sqlite3.connect(
        str(path),
        timeout=ms / 1000.0,
        check_same_thread=check_same_thread,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={ms}")
    return conn
