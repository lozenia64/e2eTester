"""Suite 쓰기 경로 — Suite blob + domain events + outbox 를 단일 트랜잭션으로 영속."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
            # 스냅샷 = 이벤트 폴드의 파생 캐시(Run 쓰기 경로와 동형).
            version = self._current_stream_position(tx, "Suite", suite.suite_id)
            tx.execute(
                """
                INSERT INTO aggregate_snapshots
                    (stream_id, aggregate_type, version, state_json, updated_at)
                VALUES (?, 'Suite', ?, ?, ?)
                ON CONFLICT(stream_id) DO UPDATE SET
                    version = excluded.version,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (f"Suite:{suite.suite_id}", version, payload, datetime.now(UTC).isoformat()),
            )

    @staticmethod
    def _current_stream_position(tx, aggregate_type: str, aggregate_id: str) -> int:
        row = tx.fetchone(
            "SELECT COALESCE(MAX(stream_position), 0) AS pos FROM domain_events "
            "WHERE aggregate_type = ? AND aggregate_id = ?",
            (aggregate_type, aggregate_id),
        )
        return int(row["pos"]) if row is not None else 0

    def _append_events_sync(self, tx, events: list[DomainEvent]) -> None:
        # 스트림별 stream_position 연속 부여(Run 쓰기 경로와 동형 — 낙관적 동시성 좌표).
        next_pos: dict[tuple[str, str], int] = {}
        event_rows = []
        for event in events:
            key = (event.aggregate_type, event.aggregate_id)
            if key not in next_pos:
                next_pos[key] = self._current_stream_position(tx, *key)
            next_pos[key] += 1
            event_rows.append(
                (
                    event.event_id,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.event_type,
                    self._db.json_dumps(event.payload),
                    event.occurred_at.isoformat(),
                    event.version,
                    next_pos[key],
                )
            )
        tx.executemany(
            """
            INSERT INTO domain_events
                (event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at,
                 version, stream_position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
