"""Transactional outbox for reliable domain event publishing."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.platform.eventing.envelope import EventEnvelope
from app.platform.eventing.event_store import StoredEvent
from app.platform.eventing.support import SqliteDatabase

# 미발행 행이 이 시간보다 오래 점유되면 다른 릴레이가 재청구할 수 있다.
CLAIM_STALE_SECONDS = 120


class SqliteOutbox:
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

    async def claim_pending(self, limit: int = 100, *, claim_token: str) -> list[StoredEvent]:
        """미발행 outbox 행을 원자적으로 점유한다(BEGIN IMMEDIATE).

        동일 행을 여러 릴레이/폴링 루프가 동시에 읽어도 ``claimed_by`` 가 설정된 행은
        한 소비자만 처리할 수 있다. API 프로세스당 OutboxRelay 1개 운영을 전제로 하되,
        중복 기동·동시 ``process_once`` 에도 안전하다.
        """
        stale_before = (datetime.now(UTC) - timedelta(seconds=CLAIM_STALE_SECONDS)).isoformat()
        now = datetime.now(UTC).isoformat()
        return await asyncio.to_thread(
            self._claim_pending_sync, limit, claim_token, stale_before, now
        )

    def _claim_pending_sync(
        self,
        limit: int,
        claim_token: str,
        stale_before: str,
        now: str,
    ) -> list[StoredEvent]:
        with self._db._thread_lock:
            if self._db._conn.in_transaction:
                self._db._conn.rollback()
            rows = self._db._conn.execute(
                """
                SELECT de.sequence_id AS domain_sequence_id,
                       o.event_id, o.aggregate_type, o.aggregate_id, o.event_type,
                       o.payload, o.occurred_at
                FROM outbox o
                JOIN domain_events de ON de.event_id = o.event_id
                WHERE o.published_at IS NULL
                  AND (
                        o.claimed_by IS NULL
                        OR o.claimed_at IS NULL
                        OR o.claimed_at < ?
                  )
                ORDER BY de.sequence_id ASC
                LIMIT ?
                """,
                (stale_before, limit),
            ).fetchall()
            claimed: list[StoredEvent] = []
            for row in rows:
                updated = self._db._conn.execute(
                    """
                    UPDATE outbox
                    SET claimed_by = ?, claimed_at = ?
                    WHERE event_id = ?
                      AND published_at IS NULL
                      AND (
                            claimed_by IS NULL
                            OR claimed_at IS NULL
                            OR claimed_at < ?
                      )
                    """,
                    (claim_token, now, row["event_id"], stale_before),
                ).rowcount
                if updated != 1:
                    continue
                claimed.append(
                    StoredEvent(
                        sequence_id=row["domain_sequence_id"],
                        event=EventEnvelope(
                            event_id=row["event_id"],
                            aggregate_type=row["aggregate_type"],
                            aggregate_id=row["aggregate_id"],
                            event_type=row["event_type"],
                            payload=json.loads(row["payload"]),
                            occurred_at=datetime.fromisoformat(row["occurred_at"]),
                        ),
                    )
                )
            self._db._conn.commit()
            return claimed

    async def mark_published(self, event_id: str, *, claim_token: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            UPDATE outbox
            SET published_at = ?, claimed_by = NULL, claimed_at = NULL
            WHERE event_id = ? AND claimed_by = ? AND published_at IS NULL
            """,
            (now, event_id, claim_token),
        )

    async def release_claim(self, event_id: str, *, claim_token: str) -> None:
        await self._db.execute(
            """
            UPDATE outbox
            SET claimed_by = NULL, claimed_at = NULL
            WHERE event_id = ? AND claimed_by = ? AND published_at IS NULL
            """,
            (event_id, claim_token),
        )

    async def move_to_dead_letter(self, event: EventEnvelope, error_message: str) -> None:
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
