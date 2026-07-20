"""Append-only domain event store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from app.platform.eventing.envelope import EventEnvelope
from app.platform.eventing.support import SqliteDatabase


@dataclass(frozen=True)
class StoredEvent:
    """영속된 도메인 이벤트 + 정본 시퀀스.

    ``sequence_id`` 는 ``domain_events`` 테이블의 전역 단조 시퀀스로, 프로젝션 커서
    (``projection_cursor.last_sequence_id``)의 기준 좌표다. 아웃박스 배달 순서(outbox 자체
    autoincrement)와 이벤트 재생 순서(리빌드)가 모두 이 하나의 시퀀스로 정렬된다.
    시퀀스는 인프라 관심사이므로 도메인 이벤트 dataclass 에 싣지 않고 여기서만 동봉한다.
    """

    sequence_id: int
    event: EventEnvelope


def _row_to_event(row) -> EventEnvelope:
    return EventEnvelope(
        event_id=row["event_id"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        event_type=row["event_type"],
        payload=json.loads(row["payload"]),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        version=row["version"],
    )


class SqliteEventStore:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def append_all(self, events: list[EventEnvelope]) -> None:
        if not events:
            return
        rows = [
            (
                event.event_id,
                event.aggregate_type,
                event.aggregate_id,
                event.event_type,
                self._db.json_dumps(event.payload),
                event.occurred_at.isoformat(),
                event.version,
            )
            for event in events
        ]
        await self._db.executemany(
            """
            INSERT INTO domain_events
                (event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    async def list_for_aggregate(
        self, aggregate_type: str, aggregate_id: str
    ) -> list[EventEnvelope]:
        rows = await self._db.fetchall(
            """
            SELECT event_id, aggregate_type, aggregate_id, event_type, payload,
                   occurred_at, version
            FROM domain_events
            WHERE aggregate_type = ? AND aggregate_id = ?
            ORDER BY sequence_id ASC
            """,
            (aggregate_type, aggregate_id),
        )
        return [_row_to_event(row) for row in rows]

    async def list_all(self) -> list[StoredEvent]:
        """전 이벤트를 정본 시퀀스 순으로 돌려준다(프로젝션 리빌드용)."""
        rows = await self._db.fetchall(
            """
            SELECT sequence_id, event_id, aggregate_type, aggregate_id, event_type, payload,
                   occurred_at, version
            FROM domain_events
            ORDER BY sequence_id ASC
            """
        )
        return [
            StoredEvent(sequence_id=row["sequence_id"], event=_row_to_event(row)) for row in rows
        ]
