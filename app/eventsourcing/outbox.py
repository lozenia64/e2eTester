"""Transactional outbox for reliable domain event publishing."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.events import DomainEvent
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

    async def claim_pending(self, limit: int = 100) -> list[DomainEvent]:
        """Claim pending outbox rows (SQLite lacks SKIP LOCKED; single-process relay)."""
        import json

        rows = await self._db.fetchall(
            """
            SELECT sequence_id, event_id, aggregate_type, aggregate_id, event_type,
                   payload, occurred_at
            FROM outbox
            WHERE published_at IS NULL
            ORDER BY sequence_id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            DomainEvent(
                event_id=row["event_id"],
                aggregate_type=row["aggregate_type"],
                aggregate_id=row["aggregate_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
            )
            for row in rows
        ]

    async def mark_published(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        now = datetime.now(UTC).isoformat()
        await self._db.executemany(
            "UPDATE outbox SET published_at = ? WHERE event_id = ?",
            [(now, eid) for eid in event_ids],
        )
