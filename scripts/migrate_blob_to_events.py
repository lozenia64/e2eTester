#!/usr/bin/env python3
"""레거시 blob → 이벤트 스트림 1회성 마이그레이션 CLI(WP-B6).

각 ``runs`` blob 을 FAILED→ANOMALY 정규화 후 ``RunImported`` genesis 이벤트 + 스냅샷으로
개시하고(멱등), 마지막에 프로젝션을 전체 리빌드한다. 실행 전 DB 백업을 권장한다.
"""

from __future__ import annotations

import argparse
import asyncio

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from app.eventsourcing.blob_migration import migrate_run_blobs
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from scripts.rebuild_projections import rebuild as rebuild_projections


async def main_async(db_path: str, *, rebuild: bool) -> int:
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    report = await migrate_run_blobs(db)
    print(
        f"migrated {report.migrated} runs "
        f"(skipped {report.skipped} already-evented, "
        f"normalized {report.normalized_failed} FAILED→ANOMALY)"
    )
    if rebuild:
        count = await rebuild_projections(db_path)
        print(f"rebuilt projections from {count} domain events")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/e2etester.db")
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="skip projection rebuild after migration (run rebuild_projections.py manually)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args.db, rebuild=not args.no_rebuild)))
