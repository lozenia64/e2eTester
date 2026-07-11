#!/usr/bin/env python3
"""프로젝션 테이블을 비우고 domain event store 에서 재구축."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from app.eventsourcing.event_store import SqliteEventStore
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import PROJECTION_NAMES, ProjectionHandlers
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository

_PROJECTION_TABLES = (
    "run_history_index",
    "anomaly_inbox_index",
    "daily_system_status",
    "stats_rollup",
    "schedule_execution_history",
    "system_last_finished",
    "run_comparison_cache",
)


async def _fingerprint_table(db: SqliteDatabase, table: str) -> str:
    rows = await db.fetchall(f"SELECT * FROM {table} ORDER BY rowid")
    payload = json.dumps(
        [dict(row) for row in rows], ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def snapshot_projection_fingerprints(db: SqliteDatabase) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for table in _PROJECTION_TABLES:
        fingerprints[table] = await _fingerprint_table(db, table)
    return fingerprints


async def rebuild(db_path: str) -> int:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = ProjectionHandlers(db, write_repo)
    event_store = SqliteEventStore(db)

    for table in (*_PROJECTION_TABLES, "projection_checkpoints"):
        await db.execute(f"DELETE FROM {table}")

    events = await event_store.list_all()
    for event in events:
        await projections.apply(event)
    return len(events)


def _backup_db_file(src_path: str, dst_path: str) -> None:
    """WAL 체크포인트를 포함해 라이브 DB를 안전하게 복사한다(원본 미변경)."""
    src_conn = sqlite3.connect(src_path)
    dst_conn = sqlite3.connect(dst_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


async def validate_rebuild(db_path: str) -> list[str]:
    """라이브 프로젝션과 이벤트 재생 결과를 비교한다.

    검증은 원본 DB를 건드리지 않는다: 복사본에서 rebuild 를 수행하고, 그 결과만
    원본의 라이브 프로젝션과 비교한다.
    """
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    before = await snapshot_projection_fingerprints(db)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_path = str(Path(tmp_dir) / "validate_copy.db")
        await asyncio.to_thread(_backup_db_file, db_path, copy_path)
        event_count = await rebuild(copy_path)
        copy_db = SqliteDatabase(copy_path)
        after = await snapshot_projection_fingerprints(copy_db)

    mismatches: list[str] = []
    for table in _PROJECTION_TABLES:
        if before.get(table) != after.get(table):
            mismatches.append(f"{table}: live={before.get(table)} rebuilt={after.get(table)}")
    if mismatches:
        return mismatches
    print(
        f"projection validation passed ({event_count} events, "
        f"{len(PROJECTION_NAMES)} handlers, {len(_PROJECTION_TABLES)} tables)"
    )
    return []


async def main_async(db_path: str, *, validate: bool) -> int:
    if validate:
        mismatches = await validate_rebuild(db_path)
        if mismatches:
            print("projection validation failed:")
            for item in mismatches:
                print(f"  - {item}")
            return 1
        return 0
    count = await rebuild(db_path)
    print(f"rebuilt projections from {count} domain events")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/e2etester.db")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="rebuild from events and diff fingerprints against prior live projections",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args.db, validate=args.validate)))
