"""스냅샷(aggregate_snapshots)에서 ``run_history_index`` 를 채운다(누락 행 backfill).

WP-B6 로 ``runs`` blob 이 폐기돼 상태의 유일한 저장소는 ``aggregate_snapshots`` 다. 이 backfill
은 프로젝션 행이 없는 Run 스냅샷을 찾아 ``run_history_index`` 를 채운다(신규 Run 은 아웃박스
릴레이가 채우므로 보통 no-op; 마이그레이션/리빌드 직후 안전망).
"""

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
        SELECT substr(s.stream_id, 5) AS run_id
        FROM aggregate_snapshots s
        LEFT JOIN run_history_index h ON substr(s.stream_id, 5) = h.run_id
        WHERE s.aggregate_type = 'Run' AND h.run_id IS NULL
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
