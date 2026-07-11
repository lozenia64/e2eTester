"""Transactional outbox for reliable domain event publishing."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.domain.events import DomainEvent
from app.eventsourcing.event_store import StoredEvent
from app.eventsourcing.support import SqliteDatabase


class SqliteOutbox:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def append_all(self, events: list[DomainEvent]) -> None:
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
            )
            for event in events
        ]
        await self._db.executemany(
            """
            INSERT INTO outbox
                (event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    async def claim_pending(self, limit: int = 100) -> list[StoredEvent]:
        """Claim pending outbox rows (SQLite lacks SKIP LOCKED; single-process relay).

        아웃박스 행과 이벤트 스토어 행은 같은 트랜잭션으로 기록되므로 ``event_id`` JOIN 은
        항상 성립하며, 여기서 동봉하는 ``domain_events.sequence_id`` 가 프로젝션 커서의
        정본 좌표가 된다(아웃박스 자체 시퀀스는 배달 순서일 뿐 커서 기준이 아니다).
        """
        rows = await self._db.fetchall(
            """
            SELECT de.sequence_id AS domain_sequence_id,
                   o.event_id, o.aggregate_type, o.aggregate_id, o.event_type,
                   o.payload, o.occurred_at
            FROM outbox o
            JOIN domain_events de ON de.event_id = o.event_id
            WHERE o.published_at IS NULL
            ORDER BY o.sequence_id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            StoredEvent(
                sequence_id=row["domain_sequence_id"],
                event=DomainEvent(
                    event_id=row["event_id"],
                    aggregate_type=row["aggregate_type"],
                    aggregate_id=row["aggregate_id"],
                    event_type=row["event_type"],
                    payload=json.loads(row["payload"]),
                    occurred_at=datetime.fromisoformat(row["occurred_at"]),
                ),
            )
            for row in rows
        ]

    async def mark_published(self, event_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            "UPDATE outbox SET published_at = ? WHERE event_id = ?",
            (now, event_id),
        )

    async def move_to_dead_letter(self, event: DomainEvent, error_message: str) -> None:
        now = datetime.now(UTC).isoformat()
        async with await self._db.transaction() as tx:
            tx.execute(
                """
                INSERT OR REPLACE INTO outbox_dead_letter
                    (event_id, aggregate_type, aggregate_id, event_type, payload,
                     occurred_at, failed_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.event_type,
                    self._db.json_dumps(event.payload),
                    event.occurred_at.isoformat(),
                    now,
                    error_message[:2000],
                ),
            )
            tx.execute("DELETE FROM outbox WHERE event_id = ?", (event.event_id,))
