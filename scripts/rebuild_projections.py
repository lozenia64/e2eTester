#!/usr/bin/env python3
"""프로젝션 테이블을 비우고 domain event store 에서 재구축."""

from __future__ import annotations

import argparse
import asyncio

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from app.eventsourcing.event_store import SqliteEventStore
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import ProjectionHandlers
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


async def rebuild(db_path: str) -> None:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    projections = ProjectionHandlers(db, write_repo)
    event_store = SqliteEventStore(db)

    for table in (
        "run_history_index",
        "anomaly_inbox_index",
        "daily_system_status",
        "stats_rollup",
        "schedule_execution_history",
        "system_last_finished",
        "run_comparison_cache",
        "projection_checkpoints",
    ):
        await db.execute(f"DELETE FROM {table}")

    events = await event_store.list_all()
    for event in events:
        await projections.apply(event)
    print(f"rebuilt projections from {len(events)} domain events")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/e2etester.db")
    args = parser.parse_args()
    asyncio.run(rebuild(args.db))
