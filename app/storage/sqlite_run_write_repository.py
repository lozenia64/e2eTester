"""Run 쓰기 경로 — Run blob + domain events + outbox 를 단일 트랜잭션으로 영속."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.run_models import Run
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
            # 스냅샷 = 이벤트 폴드의 파생 캐시. 이벤트 append 후의 마지막 stream_position 을
            # version 으로 못박아, scripts/rebuild_snapshots.py 의 재구성 결과와 대조 가능하게 한다.
            version = self._current_stream_position(tx, "Run", run.run_id)
            tx.execute(
                """
                INSERT INTO aggregate_snapshots
                    (stream_id, aggregate_type, version, state_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(stream_id) DO UPDATE SET
                    version = excluded.version,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    f"Run:{run.run_id}",
                    "Run",
                    version,
                    payload,
                    datetime.now(UTC).isoformat(),
                ),
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
        # 스트림별 stream_position 을 연속 부여한다(낙관적 동시성 좌표). 배치 내 이벤트는 보통
        # 한 애그리거트에 속하지만, 로그 등 혼합 배치도 안전하게 애그리거트별로 증가시킨다.
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
