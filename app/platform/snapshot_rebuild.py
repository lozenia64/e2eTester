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

from app.contexts.run.contracts.records import RunRecord
from app.contexts.run.domain.decider import rebuild_state
from app.contexts.run.infrastructure.codec import RunEventCodec
from app.contexts.suite.contracts.records import SuiteRecord
from app.contexts.suite.domain.decider import rebuild_state as rebuild_suite_state
from app.contexts.suite.infrastructure.codec import SuiteEventCodec
from app.platform.eventing.event_store import _row_to_event
from app.platform.eventing.support import SqliteDatabase


@dataclass
class RebuildReport:
    """리빌드 결과 요약 — 재구성한 스트림 수와 기존 스냅샷과의 불일치 목록."""

    rebuilt: int = 0
    mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


async def _stream_ids(db: SqliteDatabase, aggregate_type: str) -> list[str]:
    rows = await db.fetchall(
        "SELECT DISTINCT aggregate_id FROM domain_events WHERE aggregate_type = ?",
        (aggregate_type,),
    )
    return [row["aggregate_id"] for row in rows]


async def _events(db: SqliteDatabase, aggregate_type: str, aggregate_id: str):
    rows = await db.fetchall(
        """
        SELECT event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at, version
        FROM domain_events
        WHERE aggregate_type = ? AND aggregate_id = ?
        ORDER BY sequence_id ASC
        """,
        (aggregate_type, aggregate_id),
    )
    return [_row_to_event(row) for row in rows]


async def _stream_position(db: SqliteDatabase, aggregate_type: str, aggregate_id: str) -> int:
    row = await db.fetchone(
        "SELECT COALESCE(MAX(stream_position), 0) AS pos, COUNT(*) AS n "
        "FROM domain_events WHERE aggregate_type = ? AND aggregate_id = ?",
        (aggregate_type, aggregate_id),
    )
    if row is None:
        return 0
    # stream_position 이 아직 채워지지 않은 레거시 이벤트는 개수로 위치를 근사한다.
    return int(row["pos"]) or int(row["n"])


def snapshot_state_json(run_id: str, events) -> str | None:
    """Run 이벤트 스트림을 접어 스냅샷 JSON(=blob 형태)을 만든다(없으면 None)."""
    if not events:
        return None
    aggregate_id = run_id or events[0].aggregate_id
    codec = RunEventCodec()
    records = [codec.decode(event) for event in events]
    state = rebuild_state(records, run_id=aggregate_id)
    if state is None:
        return None
    return RunRecord.serialize(state.to_run())


def _suite_state_json(events) -> str | None:
    if not events:
        return None
    suite_id = events[0].aggregate_id
    codec = SuiteEventCodec()
    records = [codec.decode(event) for event in events]
    state = rebuild_suite_state(records, suite_id=suite_id)
    if state is None:
        return None
    return SuiteRecord.serialize(state.to_suite())


async def _rebuild_streams(
    db: SqliteDatabase,
    *,
    aggregate_type: str,
    to_state_json,
    verify_only: bool,
    report: RebuildReport,
) -> None:
    now = datetime.now(UTC).isoformat()
    for aggregate_id in await _stream_ids(db, aggregate_type):
        events = await _events(db, aggregate_type, aggregate_id)
        state_json = to_state_json(events)
        if state_json is None:
            continue
        report.rebuilt += 1
        stream_id = f"{aggregate_type}:{aggregate_id}"
        existing = await db.fetchone(
            "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", (stream_id,)
        )
        if existing is not None and not _same_state(existing["state_json"], state_json):
            report.mismatches.append(aggregate_id)
        if verify_only:
            continue
        version = await _stream_position(db, aggregate_type, aggregate_id)
        await db.execute(
            """
            INSERT INTO aggregate_snapshots
                (stream_id, aggregate_type, version, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(stream_id) DO UPDATE SET
                version = excluded.version,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (stream_id, aggregate_type, version, state_json, now),
        )


async def rebuild_missing_run_snapshots(db: SqliteDatabase) -> int:
    """이벤트는 있으나 스냅샷이 없는 Run 스트림만 폴드해 upsert 한다(시작 시 안전망)."""
    rows = await db.fetchall(
        """
        SELECT DISTINCT e.aggregate_id
        FROM domain_events e
        LEFT JOIN aggregate_snapshots s ON s.stream_id = 'Run:' || e.aggregate_id
        WHERE e.aggregate_type = 'Run' AND s.stream_id IS NULL
        """
    )
    now = datetime.now(UTC).isoformat()
    count = 0
    for row in rows:
        aggregate_id = row["aggregate_id"]
        events = await _events(db, "Run", aggregate_id)
        state_json = snapshot_state_json(aggregate_id, events)
        if state_json is None:
            continue
        version = await _stream_position(db, "Run", aggregate_id)
        await db.execute(
            """
            INSERT INTO aggregate_snapshots
                (stream_id, aggregate_type, version, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(stream_id) DO UPDATE SET
                version = excluded.version,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (f"Run:{aggregate_id}", "Run", version, state_json, now),
        )
        count += 1
    return count


async def repair_incomplete_run_snapshots(db: SqliteDatabase) -> int:
    """폴드 결과가 비어 있는 스냅샷을 레거시 blob·프로젝션으로 수리한다."""
    from app.contexts.run.contracts.records import RunRecord
    from app.contexts.run.infrastructure.run_snapshot_fallback import (
        is_incomplete_snapshot,
        resolve_run_snapshot,
    )

    rows = await db.fetchall(
        """
        SELECT substr(stream_id, 5) AS run_id, state_json
        FROM aggregate_snapshots
        WHERE aggregate_type = 'Run'
        """
    )
    now = datetime.now(UTC).isoformat()
    count = 0
    for row in rows:
        run_id = row["run_id"]
        snapshot = RunRecord.deserialize(row["state_json"])
        if not is_incomplete_snapshot(snapshot):
            continue
        repaired = await resolve_run_snapshot(db, run_id, snapshot)
        if not repaired.modules or repaired is snapshot:
            continue
        payload = RunRecord.serialize(repaired)
        await db.execute(
            """
            UPDATE aggregate_snapshots
            SET state_json = ?, updated_at = ?
            WHERE stream_id = ?
            """,
            (payload, now, f"Run:{run_id}"),
        )
        count += 1
    return count


async def rebuild_run_snapshots(db: SqliteDatabase, *, verify_only: bool = False) -> RebuildReport:
    """모든 Run 스트림을 폴드해 ``aggregate_snapshots`` 를 재구성/검증한다.

    ``verify_only`` 면 기록하지 않고 기존 스냅샷과의 도메인 동등성만 대조한다.
    """
    report = RebuildReport()
    await _rebuild_streams(
        db,
        aggregate_type="Run",
        to_state_json=lambda events: snapshot_state_json("", events),
        verify_only=verify_only,
        report=report,
    )
    return report


async def rebuild_all_snapshots(db: SqliteDatabase, *, verify_only: bool = False) -> RebuildReport:
    """Run + Suite 모든 스트림을 폴드해 스냅샷을 재구성/검증한다(이벤트=진실)."""
    report = RebuildReport()
    await _rebuild_streams(
        db,
        aggregate_type="Run",
        to_state_json=lambda events: snapshot_state_json("", events),
        verify_only=verify_only,
        report=report,
    )
    await _rebuild_streams(
        db,
        aggregate_type="Suite",
        to_state_json=_suite_state_json,
        verify_only=verify_only,
        report=report,
    )
    return report


def _same_state(a: str, b: str) -> bool:
    """두 blob JSON 이 도메인적으로 동등한지 비교한다(키 순서·공백 무시)."""
    return json.loads(a) == json.loads(b)
