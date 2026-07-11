"""Run 쓰기 경로 — Run blob + domain events + outbox 를 단일 트랜잭션으로 영속."""

from __future__ import annotations

import json

from app.core.models import Run
from app.domain.events import DomainEvent
from app.eventsourcing.event_store import SqliteEventStore
from app.eventsourcing.outbox import SqliteOutbox
from app.eventsourcing.support import SqliteDatabase
from app.storage.records import RunRecord


class SqliteRunWriteRepository:
    """``RunWriteRepositoryPort`` SQLite 어댑터.

    상태 blob(``runs``)과 이벤트 스토어·아웃박스를 한 트랜잭션에 기록한다. 프로젝션 갱신은
    ``OutboxRelay`` 가 비동기로 수행한다.
    """

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        self._event_store = SqliteEventStore(db)
        self._outbox = SqliteOutbox(db)

    async def create_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run:
        await self._persist(run, events or [])
        return run

    async def save_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run:
        await self._persist(run, events or [])
        return run

    async def get_run(self, run_id: str) -> Run:
        row = await self._db.fetchone("SELECT data FROM runs WHERE id = ?", (run_id,))
        if row is None:
            raise KeyError(run_id)
        data = row["data"]
        # 과거 버그로 JSON 문자열을 한 번 더 dumps 한 행 호환
        if isinstance(data, str) and data.startswith('"'):
            data = json.loads(data)
        return RunRecord.deserialize(data)

    async def append_events(self, events: list[DomainEvent]) -> None:
        """상태 blob 없이 이벤트·아웃박스만 적재(로그 핫패스 등)."""
        if not events:
            return
        async with await self._db.transaction() as tx:
            self._append_events_sync(tx, events)

    async def delete_run(self, run_id: str) -> None:
        async with await self._db.transaction() as tx:
            tx.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            tx.execute("DELETE FROM run_history_index WHERE run_id = ?", (run_id,))
            tx.execute("DELETE FROM run_comparison_cache WHERE run_id = ?", (run_id,))
            tx.execute(
                "DELETE FROM anomaly_inbox_index WHERE run_id = ?",
                (run_id,),
            )
            tx.execute(
                "DELETE FROM schedule_execution_history WHERE run_id = ?",
                (run_id,),
            )

    async def _persist(self, run: Run, events: list[DomainEvent]) -> None:
        payload = RunRecord.serialize(run)
        async with await self._db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO runs (id, data) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET data = excluded.data
                """,
                (run.run_id, payload),
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
