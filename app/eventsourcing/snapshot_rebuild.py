"""이벤트 스트림에서 애그리거트 스냅샷을 재구성한다(이벤트=진실의 실증).

``aggregate_snapshots`` 는 ``domain_events`` 폴드(evolve)의 **파생 캐시**다. 이 모듈은 그 캐시를
이벤트만으로 언제든 다시 만들 수 있음을 코드로 못박는다 — blob 이 사라져도(WP-B6) 상태는
이벤트에서 유도된다. ``rebuild_run_snapshots`` 는 각 Run 스트림을 ``rebuild_state`` 로 접어
스냅샷 JSON(=``RunRecord`` 직렬화)과 version(마지막 stream_position)을 upsert 하고, 기존
스냅샷과 대조한 불일치를 보고한다(리빌드 동등성 게이트의 실증 수단).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.run_decider import rebuild_state
from app.eventsourcing.event_store import _row_to_event
from app.eventsourcing.support import SqliteDatabase
from app.storage.records import RunRecord


@dataclass
class RebuildReport:
    """리빌드 결과 요약 — 재구성한 스트림 수와 기존 스냅샷과의 불일치 목록."""

    rebuilt: int = 0
    mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


async def _run_stream_ids(db: SqliteDatabase) -> list[str]:
    rows = await db.fetchall(
        "SELECT DISTINCT aggregate_id FROM domain_events WHERE aggregate_type = 'Run'"
    )
    return [row["aggregate_id"] for row in rows]


async def _run_events(db: SqliteDatabase, run_id: str):
    rows = await db.fetchall(
        """
        SELECT event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at, version
        FROM domain_events
        WHERE aggregate_type = 'Run' AND aggregate_id = ?
        ORDER BY sequence_id ASC
        """,
        (run_id,),
    )
    return [_row_to_event(row) for row in rows]


async def _stream_position(db: SqliteDatabase, run_id: str) -> int:
    row = await db.fetchone(
        "SELECT COALESCE(MAX(stream_position), 0) AS pos, COUNT(*) AS n "
        "FROM domain_events WHERE aggregate_type = 'Run' AND aggregate_id = ?",
        (run_id,),
    )
    if row is None:
        return 0
    # stream_position 이 아직 채워지지 않은 레거시 이벤트는 개수로 위치를 근사한다.
    return int(row["pos"]) or int(row["n"])


def snapshot_state_json(run_id: str, events) -> str | None:
    """Run 이벤트 스트림을 접어 스냅샷 JSON(=blob 형태)을 만든다(없으면 None)."""
    state = rebuild_state(events)
    if state is None:
        return None
    return RunRecord.serialize(state.to_run())


async def rebuild_run_snapshots(db: SqliteDatabase, *, verify_only: bool = False) -> RebuildReport:
    """모든 Run 스트림을 폴드해 ``aggregate_snapshots`` 를 재구성/검증한다.

    ``verify_only`` 면 기록하지 않고 기존 스냅샷과의 도메인 동등성만 대조한다.
    """
    report = RebuildReport()
    now = datetime.now(UTC).isoformat()
    for run_id in await _run_stream_ids(db):
        events = await _run_events(db, run_id)
        state_json = snapshot_state_json(run_id, events)
        if state_json is None:
            continue
        report.rebuilt += 1
        stream_id = f"Run:{run_id}"
        existing = await db.fetchone(
            "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", (stream_id,)
        )
        if existing is not None and not _same_state(existing["state_json"], state_json):
            report.mismatches.append(run_id)
        if verify_only:
            continue
        version = await _stream_position(db, run_id)
        await db.execute(
            """
            INSERT INTO aggregate_snapshots
                (stream_id, aggregate_type, version, state_json, updated_at)
            VALUES (?, 'Run', ?, ?, ?)
            ON CONFLICT(stream_id) DO UPDATE SET
                version = excluded.version,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (stream_id, version, state_json, now),
        )
    return report


def _same_state(a: str, b: str) -> bool:
    """두 blob JSON 이 도메인적으로 동등한지 비교한다(키 순서·공백 무시)."""
    return json.loads(a) == json.loads(b)
