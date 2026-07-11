#!/usr/bin/env python3
"""기존 Run blob 을 domain event store + outbox 로 1회 이관."""

from __future__ import annotations

import argparse
import asyncio

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from app.domain import events as domain_events
from app.eventsourcing.event_store import SqliteEventStore
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.storage.run_history_backfill import backfill_run_history_index
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


async def migrate(db_path: str) -> None:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    event_store = SqliteEventStore(db)
    outbox = SqliteOutbox(db)

    rows = await db.fetchall("SELECT id FROM runs")
    migrated = 0
    for row in rows:
        run_id = row["id"]
        existing = await db.fetchone(
            """
            SELECT 1 FROM domain_events
            WHERE aggregate_type = 'Run' AND aggregate_id = ?
            LIMIT 1
            """,
            (run_id,),
        )
        if existing is not None:
            continue
        run = await write_repo.get_run(run_id)
        batch = [
            domain_events.run_created(run.run_id, run.system_code, run.triggered_by),
        ]
        if run.ended_at is not None:
            batch.append(
                domain_events.run_finished(
                    run.run_id,
                    run.status,
                    system_code=run.system_code,
                    schedule_id=run.schedule_id,
                    suite_id=run.suite_id,
                    requested_at=run.requested_at,
                    ended_at=run.ended_at,
                    created_by_user_id=run.created_by_user_id,
                )
            )
        await event_store.append_all(batch)
        await outbox.append_all(batch)
        migrated += 1

    backfilled = await backfill_run_history_index(db, write_repo)
    print(f"migrated {migrated} runs to event store; backfilled {backfilled} index rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/e2etester.db")
    args = parser.parse_args()
    asyncio.run(migrate(args.db))
