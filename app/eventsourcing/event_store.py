"""Append-only domain event store."""

from __future__ import annotations

from app.domain.events import DomainEvent
from app.eventsourcing.support import SqliteDatabase


class SqliteEventStore:
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

    async def list_for_aggregate(self, aggregate_type: str, aggregate_id: str) -> list[DomainEvent]:
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
        import json

        return [
            DomainEvent(
                event_id=row["event_id"],
                aggregate_type=row["aggregate_type"],
                aggregate_id=row["aggregate_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                occurred_at=__import__("datetime").datetime.fromisoformat(row["occurred_at"]),
                version=row["version"],
            )
            for row in rows
        ]

    async def list_all(self) -> list[DomainEvent]:
        rows = await self._db.fetchall(
            """
            SELECT event_id, aggregate_type, aggregate_id, event_type, payload,
                   occurred_at, version
            FROM domain_events
            ORDER BY sequence_id ASC
            """
        )
        import json
        from datetime import datetime

        return [
            DomainEvent(
                event_id=row["event_id"],
                aggregate_type=row["aggregate_type"],
                aggregate_id=row["aggregate_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                version=row["version"],
            )
            for row in rows
        ]
