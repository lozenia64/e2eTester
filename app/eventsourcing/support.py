"""SQLite relational helpers for event store, outbox, and projections."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.platform.sqlite_connection import connect_sqlite

DEFAULT_DB_PATH = "data/e2etester.db"


class SqliteDatabase:
    """Shared SQLite connection with WAL mode and async lock."""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = connect_sqlite(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self._execute_sync, sql, params)

    async def execute_changes(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """INSERT/UPDATE/DELETE 실행 후 영향받은 행 수를 반환한다."""
        async with self._lock:
            return await asyncio.to_thread(self._execute_changes_sync, sql, params)

    def _execute_changes_sync(self, sql: str, params: tuple[Any, ...]) -> int:
        with self._thread_lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor.rowcount

    def execute_changes_sync(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """동기 스레드(예: SMTP 발송 스레드)에서 사용하는 변경 실행."""
        return self._execute_changes_sync(sql, params)

    def _execute_sync(self, sql: str, params: tuple[Any, ...]) -> None:
        with self._thread_lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    async def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._executemany_sync, sql, params_seq)

    def _executemany_sync(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        with self._thread_lock:
            self._conn.executemany(sql, params_seq)
            self._conn.commit()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        async with self._lock:
            return await asyncio.to_thread(self._fetchall_sync, sql, params)

    def _fetchall_sync(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        with self._thread_lock:
            cursor = self._conn.execute(sql, params)
            return cursor.fetchall()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        async with self._lock:
            return await asyncio.to_thread(self._fetchone_sync, sql, params)

    def close(self) -> None:
        """Close the underlying SQLite connection (required before deleting DB files on Windows)."""
        self._conn.close()

    def _fetchone_sync(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._thread_lock:
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
        await asyncio.to_thread(self._db._conn.execute, "BEGIN IMMEDIATE")
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

    def execute_changes(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        cursor = self._db._conn.execute(sql, params)
        return cursor.rowcount

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self._db._conn.execute(sql, params).fetchall())

    def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        self._db._conn.executemany(sql, params_seq)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        # 트랜잭션 내부 읽기(예: 스트림의 다음 stream_position 계산). 락은 이미 보유 중이다.
        return self._db._conn.execute(sql, params).fetchone()


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
            version INTEGER NOT NULL DEFAULT 1,
            stream_position INTEGER
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_domain_events_aggregate
        ON domain_events (aggregate_type, aggregate_id, sequence_id)
        """,
        # 스트림 내 위치의 유일성 = 낙관적 동시성 제어(같은 위치 이중 append → UNIQUE 위반).
        # 단일 프로세스 asyncio.Lock 이 실경합을 막지만, 계약을 스키마 수준에서 못박아
        # 다중 프로세스 전환 시에도 lost-update 를 구조적으로 차단한다.
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_domain_events_stream_position
        ON domain_events (aggregate_type, aggregate_id, stream_position)
        WHERE stream_position IS NOT NULL
        """,
        # 애그리거트 스냅샷 = 이벤트 폴드(evolve)의 파생 캐시. state_json 은 이벤트 스트림에서
        # scripts/rebuild_snapshots.py 로 언제든 재구성 가능하며(이벤트=진실), version 은 마지막
        # 반영 stream_position 이다.
        """
        CREATE TABLE IF NOT EXISTS aggregate_snapshots (
            stream_id TEXT PRIMARY KEY,
            aggregate_type TEXT NOT NULL,
            version INTEGER NOT NULL,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
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
            system_name TEXT,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            schedule_id TEXT,
            suite_id TEXT,
            created_by_user_id TEXT,
            created_by_user_name TEXT,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            awaiting_input_module_id TEXT,
            awaiting_input_prompt TEXT,
            module_total INTEGER,
            module_defined_total INTEGER,
            module_skipped INTEGER,
            module_passed INTEGER,
            current_module_name TEXT,
            failed_module_name TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_run_history_system ON run_history_index (system_code)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_requested ON run_history_index (requested_at)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_schedule ON run_history_index (schedule_id)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_user ON run_history_index (created_by_user_id)",
        "CREATE INDEX IF NOT EXISTS idx_run_history_status ON run_history_index (status)",
        """
        CREATE TABLE IF NOT EXISTS suite_history_index (
            suite_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            current_step_index INTEGER NOT NULL DEFAULT 0,
            active_run_id TEXT,
            awaiting_input_run_id TEXT,
            awaiting_input_prompt TEXT,
            browser_mode TEXT,
            selected_system_codes TEXT NOT NULL DEFAULT '[]',
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            schedule_id TEXT,
            created_by_user_id TEXT,
            created_by_user_name TEXT,
            step_total INTEGER NOT NULL DEFAULT 0,
            steps TEXT NOT NULL DEFAULT '[]'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_suite_history_requested ON suite_history_index (requested_at)",
        "CREATE INDEX IF NOT EXISTS idx_suite_history_user ON suite_history_index (created_by_user_id)",
        """
        CREATE TABLE IF NOT EXISTS module_history_index (
            run_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            system_code TEXT NOT NULL,
            module_name TEXT,
            status TEXT NOT NULL,
            message TEXT,
            started_at TEXT,
            ended_at TEXT,
            duration_ms INTEGER,
            current_url TEXT,
            artifacts TEXT NOT NULL DEFAULT '[]',
            ai_category TEXT,
            ai_summary TEXT,
            ai_action TEXT,
            suite_id TEXT,
            schedule_id TEXT,
            triggered_by TEXT,
            requested_at TEXT,
            created_by_user_id TEXT,
            created_by_user_name TEXT,
            PRIMARY KEY (run_id, module_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_module_history_system
        ON module_history_index (system_code, requested_at)
        """,
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
            duration_ms INTEGER,
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
        CREATE TABLE IF NOT EXISTS projection_cursor (
            projection_name TEXT PRIMARY KEY,
            last_sequence_id INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
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
        """
        CREATE TABLE IF NOT EXISTS email_notification_claims (
            scope TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            PRIMARY KEY (scope, entity_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS outbox_dead_letter (
            event_id TEXT PRIMARY KEY,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            failed_at TEXT NOT NULL,
            error_message TEXT NOT NULL
        )
        """,
        "CREATE TABLE IF NOT EXISTS suites (id TEXT PRIMARY KEY, data TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL)",
        # Phase C: 모듈 경계 내구 체크포인트. storage_state_cipher 는 입력 스토어와 동일 키로
        # 암호화된 Playwright storage_state(인증 쿠키=민감정보). 재기동/워커 교체 후 재개 워커가
        # 이 행으로 세션을 복원하고 module_index+1 부터 이어받는다(무효면 로그인부터 재실행).
        """
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            run_id TEXT PRIMARY KEY,
            session_id TEXT,
            worker_id TEXT,
            system_code TEXT NOT NULL,
            execution_mode TEXT NOT NULL,
            module_index INTEGER NOT NULL,
            workflow_step TEXT,
            storage_state_cipher BLOB,
            runtime_config_json TEXT,
            updated_at TEXT NOT NULL
        )
        """,
    ]
    for sql in statements:
        await db.execute(sql)
    # 기존 배포 DB 컬럼 증분(CREATE TABLE IF NOT EXISTS 는 기존 테이블을 바꾸지 않는다).
    # 값 채움은 스키마 책임이 아니다 — scripts/rebuild_projections.py 재생이 채운다.
    await _ensure_columns(
        db,
        "run_history_index",
        {
            "system_name": "TEXT",
            "started_at": "TEXT",
            "awaiting_input_module_id": "TEXT",
            "awaiting_input_prompt": "TEXT",
            "module_total": "INTEGER",
            "module_defined_total": "INTEGER",
            "module_skipped": "INTEGER",
            "module_passed": "INTEGER",
            "current_module_name": "TEXT",
            "failed_module_name": "TEXT",
        },
    )
    await _ensure_columns(db, "daily_system_status", {"duration_ms": "INTEGER"})
    await _ensure_columns(db, "module_history_index", {"ai_action": "TEXT"})
    # 기존 배포 DB 의 domain_events 에 stream_position 컬럼을 증분 추가한다(낙관적 동시성 위치).
    # NULL 로 시작하며 append 경로가 스트림별 위치를 채운다(부분 UNIQUE 인덱스는 NULL 을 무시).
    await _ensure_columns(db, "domain_events", {"stream_position": "INTEGER"})
    await _ensure_columns(
        db,
        "outbox",
        {
            "claimed_by": "TEXT",
            "claimed_at": "TEXT",
        },
    )
    await _migrate_projection_checkpoints_to_cursor(db)


async def _ensure_columns(db: SqliteDatabase, table: str, columns: dict[str, str]) -> None:
    """기존 테이블에 없는 컬럼만 ALTER TABLE ADD COLUMN 으로 추가한다(멱등)."""
    rows = await db.fetchall(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in rows}
    for name, declaration in columns.items():
        if name in existing:
            continue
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


async def _migrate_projection_checkpoints_to_cursor(db: SqliteDatabase) -> None:
    """per-event ``projection_checkpoints`` → 단조 커서 ``projection_cursor`` 1회성 이관.

    프로젝션 멱등성 판정이 "이벤트별 적용 여부 행"에서 "프로젝션별 마지막 적용 시퀀스"로
    바뀌었다. 기존 배포 DB 는 체크포인트 행에서 프로젝션별 최대 정본 시퀀스
    (``domain_events.sequence_id``)를 계산해 커서로 승계하고, 구 테이블은 폐기한다.
    """
    row = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'projection_checkpoints'"
    )
    if row is None:
        return
    now = datetime.now(UTC).isoformat()
    rows = await db.fetchall(
        """
        SELECT pc.projection_name AS projection_name, MAX(de.sequence_id) AS last_sequence_id
        FROM projection_checkpoints pc
        JOIN domain_events de ON de.event_id = pc.event_id
        GROUP BY pc.projection_name
        """
    )
    for entry in rows:
        await db.execute(
            """
            INSERT INTO projection_cursor (projection_name, last_sequence_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(projection_name) DO UPDATE SET
                last_sequence_id = MAX(projection_cursor.last_sequence_id,
                                       excluded.last_sequence_id),
                updated_at = excluded.updated_at
            """,
            (entry["projection_name"], entry["last_sequence_id"] or 0, now),
        )
    await db.execute("DROP TABLE projection_checkpoints")
