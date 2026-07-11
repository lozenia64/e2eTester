"""SQLite relational helpers for event store, outbox, and projections."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "data/e2etester.db"


class SqliteDatabase:
    """Shared SQLite connection with WAL mode and async lock."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = asyncio.Lock()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self._execute_sync, sql, params)

    def _execute_sync(self, sql: str, params: tuple[Any, ...]) -> None:
        self._conn.execute(sql, params)
        self._conn.commit()

    async def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._executemany_sync, sql, params_seq)

    def _executemany_sync(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        self._conn.executemany(sql, params_seq)
        self._conn.commit()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        async with self._lock:
            return await asyncio.to_thread(self._fetchall_sync, sql, params)

    def _fetchall_sync(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        cursor = self._conn.execute(sql, params)
        return cursor.fetchall()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        async with self._lock:
            return await asyncio.to_thread(self._fetchone_sync, sql, params)

    def _fetchone_sync(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        cursor = self._conn.execute(sql, params)
        return cursor.fetchone()

    async def transaction(self) -> _Transaction:
        return _Transaction(self)

    def json_dumps(self, value: Any) -> str:
        return json.dumps(value, default=str)


class _Transaction:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        self._lock = db._lock

    async def __aenter__(self) -> _Transaction:
        await self._lock.acquire()
        await asyncio.to_thread(self._db._conn.execute, "BEGIN")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                await asyncio.to_thread(self._db._conn.commit)
            else:
                await asyncio.to_thread(self._db._conn.rollback)
        finally:
            self._lock.release()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._db._conn.execute(sql, params)

    def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        self._db._conn.executemany(sql, params_seq)


async def ensure_schema(db: SqliteDatabase) -> None:
    """Create event sourcing and projection tables if missing."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS domain_events (
            sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_domain_events_aggregate
        ON domain_events (aggregate_type, aggregate_id, sequence_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS outbox (
            sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            published_at TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_outbox_pending
        ON outbox (sequence_id) WHERE published_at IS NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS run_history_index (
            run_id TEXT PRIMARY KEY,
            system_code TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            ended_at TEXT,
            schedule_id TEXT,
            suite_id TEXT,
            created_by_user_id TEXT,
            created_by_user_name TEXT,
            triggered_by TEXT NOT NULL DEFAULT 'manual'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_run_history_system ON run_history_index (system_code)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_requested ON run_history_index (requested_at)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_schedule ON run_history_index (schedule_id)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_user ON run_history_index (created_by_user_id)",
        """
        CREATE TABLE IF NOT EXISTS run_comparison_cache (
            run_id TEXT PRIMARY KEY,
            baseline_run_id TEXT,
            newly_failed TEXT NOT NULL DEFAULT '[]',
            recovered TEXT NOT NULL DEFAULT '[]',
            still_failing TEXT NOT NULL DEFAULT '[]',
            computed_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS anomaly_inbox_index (
            module_run_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            system_code TEXT NOT NULL,
            status TEXT NOT NULL,
            ended_at TEXT,
            created_by_user_id TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_anomaly_system ON anomaly_inbox_index (system_code)",
        """
        CREATE TABLE IF NOT EXISTS daily_system_status (
            day_key TEXT NOT NULL,
            system_code TEXT NOT NULL,
            module_id TEXT NOT NULL,
            last_status TEXT NOT NULL,
            last_run_id TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (day_key, system_code, module_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS stats_rollup (
            day_key TEXT NOT NULL,
            system_code TEXT NOT NULL,
            passed_count INTEGER NOT NULL DEFAULT 0,
            anomaly_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            cancelled_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day_key, system_code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schedule_execution_history (
            schedule_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            ended_at TEXT,
            PRIMARY KEY (schedule_id, run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_last_finished (
            system_code TEXT PRIMARY KEY,
            last_finished_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS projection_checkpoints (
            projection_name TEXT NOT NULL,
            event_id TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY (projection_name, event_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS run_inputs (
            run_id TEXT PRIMARY KEY,
            ciphertext TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS suite_inputs (
            suite_id TEXT PRIMARY KEY,
            ciphertext TEXT NOT NULL
        )
        """,
        "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL)",
    ]
    for sql in statements:
        await db.execute(sql)
