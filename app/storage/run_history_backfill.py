"""기존 ``runs`` blob 에서 ``run_history_index`` 를 채운다(업그레이드 1회)."""

from __future__ import annotations

import argparse
import asyncio

from app.domain.summary_fields import run_summary_fields
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import _run_history_upsert
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


async def backfill_run_history_index(
    db: SqliteDatabase, write_repo: SqliteRunWriteRepository
) -> int:
    missing = await db.fetchall(
        """
        SELECT r.id AS run_id
        FROM runs r
        LEFT JOIN run_history_index h ON r.id = h.run_id
        WHERE h.run_id IS NULL
        """
    )
    count = 0
    for row in missing:
        run = await write_repo.get_run(row["run_id"])
        sql, params = _run_history_upsert(run.run_id, run_summary_fields(run))
        await db.execute(sql, params)
        count += 1
    return count


async def _main(db_path: str) -> None:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    count = await backfill_run_history_index(db, write_repo)
    print(f"backfilled {count} run_history_index rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill run_history_index from runs table")
    parser.add_argument("--db", default="data/e2etester.db")
    args = parser.parse_args()
    asyncio.run(_main(args.db))
