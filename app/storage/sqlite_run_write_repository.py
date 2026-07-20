"""Run 쓰기 경로 — 이벤트 스토어 + outbox + 스냅샷을 단일 트랜잭션으로 영속.

**이벤트가 진실의 원천이고 ``aggregate_snapshots`` 이 유일한 파생 상태 캐시다**(WP-B6): 레거시
``runs`` blob 테이블은 더 이상 쓰지 않고 읽지 않는다(``get_run`` 은 스냅샷을 읽고, ``_persist``
는 스냅샷만 upsert 한다). ``runs`` 테이블은 1회성 마이그레이션(``migrate_blob_to_events``)의
**입력**으로만 남으며(과거 배포 데이터 → 이벤트 스트림), 신규 데이터는 스냅샷에만 존재한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.run_models import Run
from app.domain.events import DomainEvent
from app.platform.eventing.event_store import SqliteEventStore
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.support import SqliteDatabase
from app.storage.records import RunRecord


class SqliteRunWriteRepository:
    """``RunWriteRepositoryPort`` SQLite 어댑터.

    이벤트 스토어·아웃박스·스냅샷을 한 트랜잭션에 기록한다. 프로젝션 갱신은 ``OutboxRelay`` 가
    비동기로 수행한다. 상태 blob(``runs``)은 폐기됐고 스냅샷이 유일한 파생 캐시다.
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
        # 이벤트 폴드의 파생 캐시(aggregate_snapshots)가 유일한 상태 저장소다(runs blob 폐기).
        # 단, thin-event·불완전 폴드 스냅샷은 레거시 blob/프로젝션으로 복원한다(상세 화면).
        from app.storage.run_snapshot_fallback import (
            is_incomplete_snapshot,
            load_run_without_snapshot,
            resolve_run_snapshot,
        )

        row = await self._db.fetchone(
            "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?",
            (f"Run:{run_id}",),
        )
        if row is None:
            fallback = await load_run_without_snapshot(self._db, run_id)
            if fallback is None:
                raise KeyError(run_id)
            return fallback
        run = RunRecord.deserialize(row["state_json"])
        if is_incomplete_snapshot(run):
            return await resolve_run_snapshot(self._db, run_id, run)
        return run

    async def append_events(self, events: list[DomainEvent]) -> None:
        """상태 스냅샷 없이 이벤트·아웃박스만 적재."""
        if not events:
            return
        async with await self._db.transaction() as tx:
            self._append_events_sync(tx, events)

    async def delete_run(self, run_id: str) -> None:
        """Run 스트림·스냅샷·프로젝션·레거시 blob 을 한 트랜잭션으로 영구 삭제한다."""
        async with await self._db.transaction() as tx:
            tx.execute(
                "DELETE FROM outbox WHERE aggregate_type = 'Run' AND aggregate_id = ?",
                (run_id,),
            )
            tx.execute(
                "DELETE FROM domain_events WHERE aggregate_type = 'Run' AND aggregate_id = ?",
                (run_id,),
            )
            tx.execute("DELETE FROM aggregate_snapshots WHERE stream_id = ?", (f"Run:{run_id}",))
            tx.execute("DELETE FROM run_history_index WHERE run_id = ?", (run_id,))
            tx.execute("DELETE FROM module_history_index WHERE run_id = ?", (run_id,))
            tx.execute("DELETE FROM run_comparison_cache WHERE run_id = ?", (run_id,))
            tx.execute(
                "DELETE FROM anomaly_inbox_index WHERE run_id = ?",
                (run_id,),
            )
            tx.execute(
                "DELETE FROM schedule_execution_history WHERE run_id = ?",
                (run_id,),
            )
            tx.execute("DELETE FROM session_checkpoints WHERE run_id = ?", (run_id,))
            self._delete_from_table_if_exists(
                tx,
                "outbox_dead_letter",
                "DELETE FROM outbox_dead_letter WHERE aggregate_type = 'Run' AND aggregate_id = ?",
                (run_id,),
            )
            self._delete_from_table_if_exists(
                tx,
                "runs",
                "DELETE FROM runs WHERE id = ?",
                (run_id,),
            )
            self._delete_from_table_if_exists(
                tx,
                "healing_events",
                "DELETE FROM healing_events WHERE run_id = ?",
                (run_id,),
            )
            self._delete_from_table_if_exists(
                tx,
                "healing_patches",
                "DELETE FROM healing_patches WHERE run_id = ?",
                (run_id,),
            )

    @staticmethod
    def _delete_from_table_if_exists(tx, table: str, sql: str, params: tuple) -> None:
        row = tx.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table,),
        )
        if row is not None:
            tx.execute(sql, params)

    async def _persist(self, run: Run, events: list[DomainEvent]) -> None:
        payload = RunRecord.serialize(run)
        async with await self._db.transaction() as tx:
            if events:
                self._append_events_sync(tx, events)
            # 스냅샷 = 이벤트 폴드의 파생 캐시(유일 상태 저장소). version = append 후 마지막
            # stream_position — scripts/rebuild_snapshots.py 의 재구성 결과와 대조 가능하다.
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
