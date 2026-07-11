"""Suite 쓰기 경로 — Suite blob + domain events + outbox 를 단일 트랜잭션으로 영속."""

from __future__ import annotations

import json

from app.core.models import SuiteRun
from app.domain.events import DomainEvent
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.support import SqliteDatabase
from app.storage.records import SuiteRecord


class SqliteSuiteWriteRepository:
    """``SuiteWriteRepositoryPort`` SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        self._outbox = SqliteOutbox(db)

    async def create_suite(
        self, suite: SuiteRun, *, events: list[DomainEvent] | None = None
    ) -> SuiteRun:
        await self._persist(suite, events or [])
        return suite

    async def save_suite(
        self, suite: SuiteRun, *, events: list[DomainEvent] | None = None
    ) -> SuiteRun:
        await self._persist(suite, events or [])
        return suite

    async def get_suite(self, suite_id: str) -> SuiteRun:
        row = await self._db.fetchone("SELECT data FROM suites WHERE id = ?", (suite_id,))
        if row is None:
            raise KeyError(suite_id)
        data = row["data"]
        if isinstance(data, str) and data.startswith('"'):
            data = json.loads(data)
        return SuiteRecord.deserialize(data)

    async def append_events(self, events: list[DomainEvent]) -> None:
        """상태 blob 없이 이벤트·아웃박스만 적재(로그 핫패스 등)."""
        if not events:
            return
        async with await self._db.transaction() as tx:
            self._append_events_sync(tx, events)

    async def _persist(self, suite: SuiteRun, events: list[DomainEvent]) -> None:
        payload = SuiteRecord.serialize(suite)
        async with await self._db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO suites (id, data) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET data = excluded.data
                """,
                (suite.suite_id, payload),
            )
            if events:
                self._append_events_sync(tx, events)

    def _append_events_sync(self, tx, events: list[DomainEvent]) -> None:
        event_rows = [
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
        tx.executemany(
            """
            INSERT INTO domain_events
                (event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            event_rows,
        )
        outbox_rows = [
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
        tx.executemany(
            """
            INSERT INTO outbox
                (event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            outbox_rows,
        )
