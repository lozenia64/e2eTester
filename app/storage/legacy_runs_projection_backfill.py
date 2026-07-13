"""레거시 ``runs`` blob 에만 남은 모듈 상세를 프로젝션 인덱스로 backfill 한다.

일부 Run 은 ``RunCreated``+``RunFinished`` thin 이벤트만 있어 스냅샷·모듈 이력이 비어 있지만,
마이그레이션 전 ``runs.data`` blob 에는 종료 모듈이 남아 있다. 이 backfill 은
``run_history_index``/``module_history_index`` 의 누락·불일치 행만 blob 에서 채운다(기존 행·ai_* 보존).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.run_models import Run
from app.domain.summary_fields import (
    MODULE_HISTORY_STATUSES,
    module_history_fields,
    run_summary_fields,
)
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import _module_history_upsert, _run_history_upsert
from app.storage.records import RunRecord
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


@dataclass(frozen=True)
class LegacyRunsBackfillReport:
    run_rows: int = 0
    module_rows: int = 0


async def _runs_table_exists(db: SqliteDatabase) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs' LIMIT 1"
    )
    return row is not None


def _deserialize_blob(data: object) -> Run:
    if isinstance(data, str) and data.startswith('"'):
        data = json.loads(data)
    return RunRecord.deserialize(data)


def _history_modules(run: Run) -> list:
    return [module for module in run.modules if module.status in MODULE_HISTORY_STATUSES]


async def backfill_from_legacy_runs(
    db: SqliteDatabase,
    write_repo: SqliteRunWriteRepository,
) -> LegacyRunsBackfillReport:
    """``runs`` blob 기준으로 누락된 요약·모듈 이력 행을 upsert 한다."""
    if not await _runs_table_exists(db):
        return LegacyRunsBackfillReport()

    report = LegacyRunsBackfillReport()
    rows = await db.fetchall("SELECT id, data FROM runs")
    for row in rows:
        run_id = row["id"]
        run = _deserialize_blob(row["data"])
        blob_history = _history_modules(run)
        if not blob_history:
            continue

        summary = run_summary_fields(run)
        expected_passed = summary.get("module_passed") or 0
        existing_rows = await db.fetchall(
            "SELECT module_id FROM module_history_index WHERE run_id = ?",
            (run_id,),
        )
        existing_ids = {existing["module_id"] for existing in existing_rows}
        hist_row = await db.fetchone(
            "SELECT module_passed FROM run_history_index WHERE run_id = ?",
            (run_id,),
        )
        indexed_passed = hist_row["module_passed"] if hist_row is not None else None

        modules_complete = len(existing_ids) >= len(blob_history)
        summary_complete = (
            hist_row is not None
            and (indexed_passed or 0) >= expected_passed
            and expected_passed > 0
        )
        if modules_complete and summary_complete:
            continue

        if hist_row is None or (indexed_passed or 0) < expected_passed or not modules_complete:
            sql, params = _run_history_upsert(run_id, summary)
            await db.execute(sql, params)
            report = LegacyRunsBackfillReport(
                run_rows=report.run_rows + 1,
                module_rows=report.module_rows,
            )

        for module in blob_history:
            if module.module_id in existing_ids:
                continue
            sql, params = _module_history_upsert(
                run_id, summary, module_history_fields(run, module)
            )
            await db.execute(sql, params)
            existing_ids.add(module.module_id)
            report = LegacyRunsBackfillReport(
                run_rows=report.run_rows,
                module_rows=report.module_rows + 1,
            )

    return report


async def _main(db_path: str) -> None:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    report = await backfill_from_legacy_runs(db, write_repo)
    print(
        f"backfilled {report.run_rows} run_history_index rows, "
        f"{report.module_rows} module_history_index rows from legacy runs blob"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill run/module history projections from legacy runs blob"
    )
    parser.add_argument("--db", default="data/e2etester.db")
    args = parser.parse_args()
    asyncio.run(_main(args.db))
