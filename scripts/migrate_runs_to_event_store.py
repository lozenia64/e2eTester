#!/usr/bin/env python3
"""기존 Run blob 을 domain event store + outbox 로 1회 이관."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.domain.events import RunEventRecord, RunFinished
from app.contexts.run.infrastructure.backfill.run_history_backfill import backfill_run_history_index
from app.contexts.run.infrastructure.codec import RunEventCodec
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.domain.summary_fields import run_summary_fields
from app.platform.eventing.event_store import SqliteEventStore
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.support import SqliteDatabase, ensure_schema

_CODEC = RunEventCodec()


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
        aggregate = RunAggregate.for_new_run(run)
        records = list(aggregate.pull_events())
        if run.ended_at is not None:
            summary = run_summary_fields(run)
            records.append(
                RunEventRecord(
                    event=RunFinished(
                        status=run.status,
                        system_code=run.system_code,
                        schedule_id=run.schedule_id,
                        suite_id=run.suite_id,
                        requested_at=run.requested_at,
                        ended_at=run.ended_at,
                        created_by_user_id=run.created_by_user_id,
                    ),
                    run_summary=summary,
                    event_id=uuid4().hex,
                    occurred_at=datetime.now(UTC),
                )
            )
        batch = [_CODEC.encode(run.run_id, record) for record in records]
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
