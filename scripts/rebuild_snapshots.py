#!/usr/bin/env python3
"""애그리거트 스냅샷(aggregate_snapshots)을 domain event store 에서 재구성/검증.

``aggregate_snapshots`` 는 이벤트 폴드의 파생 캐시다 — 이 스크립트는 그 캐시를 이벤트만으로
다시 만들 수 있음을 실증한다(이벤트=진실). ``--validate`` 는 기록하지 않고 기존 스냅샷과
재구성 결과의 도메인 동등성만 대조한다(리빌드 동등성 게이트).
"""

from __future__ import annotations

import argparse
import asyncio

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from app.eventsourcing.snapshot_rebuild import rebuild_all_snapshots
from app.eventsourcing.support import SqliteDatabase, ensure_schema


async def main_async(db_path: str, *, validate: bool) -> int:
    db = SqliteDatabase(db_path)
    try:
        await ensure_schema(db)
        report = await rebuild_all_snapshots(db, verify_only=validate)
        if validate:
            if not report.ok:
                print("snapshot validation failed:")
                for aggregate_id in report.mismatches:
                    print(f"  - {aggregate_id} live snapshot != event fold")
                return 1
            print(f"snapshot validation passed ({report.rebuilt} streams)")
            return 0
        print(f"rebuilt {report.rebuilt} snapshots from domain events")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/e2etester.db")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="fold events and diff against stored aggregate_snapshots without writing",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args.db, validate=args.validate)))
