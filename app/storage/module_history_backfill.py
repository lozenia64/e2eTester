"""스냅샷(aggregate_snapshots)에서 ``module_history_index`` 를 채운다(누락 행 backfill).

``run_history_backfill`` 과 대칭: 마이그레이션·스냅샷 backfill 로 ``run_history_index`` 만
생긴 Run 은 모듈 이력 행이 없어 사용량 통계(통과 모듈·절감 시간)가 0 으로 나온다.
신규 Run 은 ``ModuleFinished`` fat event 가 채우므로 보통 no-op.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# CLI 직접 실행 시 PYTHONPATH 없이도 ``app`` import 가능하도록 repo root 를 path 에 추가.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.domain.summary_fields import (
    MODULE_HISTORY_STATUSES,
    module_history_fields,
    run_summary_fields,
)
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import _module_history_upsert
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


async def backfill_module_history_index(
    db: SqliteDatabase, write_repo: SqliteRunWriteRepository
) -> int:
    """스냅샷 종료 모듈 중 ``module_history_index`` 에 없는 행만 upsert 한다."""
    run_rows = await db.fetchall(
        """
        SELECT substr(s.stream_id, 5) AS run_id
        FROM aggregate_snapshots s
        WHERE s.aggregate_type = 'Run'
        """
    )
    count = 0
    for row in run_rows:
        run_id = row["run_id"]
        existing_rows = await db.fetchall(
            "SELECT module_id FROM module_history_index WHERE run_id = ?",
            (run_id,),
        )
        existing_ids = {existing["module_id"] for existing in existing_rows}
        run = await write_repo.get_run(run_id)
        summary = run_summary_fields(run)
        for module in run.modules:
            if module.status not in MODULE_HISTORY_STATUSES:
                continue
            if module.module_id in existing_ids:
                continue
            sql, params = _module_history_upsert(
                run.run_id, summary, module_history_fields(run, module)
            )
            await db.execute(sql, params)
            count += 1
    return count


async def _main(db_path: str) -> None:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    count = await backfill_module_history_index(db, write_repo)
    print(f"backfilled {count} module_history_index rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill module_history_index from aggregate snapshots"
    )
    parser.add_argument("--db", default="data/e2etester.db")
    args = parser.parse_args()
    asyncio.run(_main(args.db))
