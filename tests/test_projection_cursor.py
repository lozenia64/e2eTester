"""프로젝션 단조 커서 — 멱등성·재전달 안전·리빌드 결정성·체크포인트 이관 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run, RunModule
from app.domain.events import DomainEvent
from app.domain.run_aggregate import RunAggregate
from app.eventsourcing.event_store import SqliteEventStore
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.projections.handlers import PROJECTION_NAMES, ProjectionHandlers
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


def _run_finished_event(run_id: str = "run_cursor") -> DomainEvent:
    requested_at = datetime(2026, 7, 1, 3, 0, tzinfo=UTC)
    return DomainEvent.create(
        "Run",
        run_id,
        "RunFinished",
        {
            "status": RunStatus.PASSED.value,
            "system_code": "hom",
            "schedule_id": None,
            "suite_id": None,
            "requested_at": requested_at.isoformat(),
            "ended_at": datetime(2026, 7, 1, 3, 5, tzinfo=UTC).isoformat(),
            "created_by_user_id": None,
        },
    )


def _sample_run(run_id: str) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.login",
                name="login",
                group="auth",
                order=0,
                status=ModuleStatus.PENDING,
            ),
        ],
        selected_module_ids=["hom.login"],
        triggered_by="manual",
    )


async def _make_handlers(tmp_path: Path, name: str) -> tuple[SqliteDatabase, ProjectionHandlers]:
    db = SqliteDatabase(tmp_path / name)
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    return db, ProjectionHandlers(db, write_repo)


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_double_count_rollup(tmp_path: Path) -> None:
    """재전달(같은 시퀀스 재적용)이 와도 비멱등 증분(stats_rollup)이 한 번만 적용된다."""
    db, projections = await _make_handlers(tmp_path, "dup.db")
    event = _run_finished_event()

    await projections.apply(event, 1)
    await projections.apply(event, 1)
    # 프로세스 재기동(커서 캐시 소실) 후 재전달도 동일해야 한다.
    fresh = ProjectionHandlers(db, SqliteRunWriteRepository(db))
    await fresh.apply(event, 1)

    row = await db.fetchone("SELECT passed_count FROM stats_rollup WHERE system_code = ?", ("hom",))
    assert row is not None
    assert row["passed_count"] == 1


@pytest.mark.asyncio
async def test_cursor_advances_even_for_unhandled_event_types(tmp_path: Path) -> None:
    """어떤 프로젝션도 소비하지 않는 이벤트도 커서를 전진시킨다(커서 정체 방지)."""
    db, projections = await _make_handlers(tmp_path, "advance.db")
    # 어떤 프로젝션도 소비하지 않는 합성 이벤트 타입(커서 전진만 확인).
    noop = DomainEvent.create("Run", "run_x", "RunDiagnosticNoted", {"note": "x"})

    await projections.apply(noop, 7)

    rows = await db.fetchall("SELECT projection_name, last_sequence_id FROM projection_cursor")
    assert {row["projection_name"] for row in rows} == set(PROJECTION_NAMES)
    assert all(row["last_sequence_id"] == 7 for row in rows)


@pytest.mark.asyncio
async def test_rebuild_replay_reproduces_identical_rows(tmp_path: Path) -> None:
    """프로젝션 truncate 후 이벤트 스토어 재생이 라이브 적용과 동일한 행을 만든다(결정성)."""
    db, projections = await _make_handlers(tmp_path, "rebuild.db")
    write_repo = SqliteRunWriteRepository(db)
    event_store = SqliteEventStore(db)

    run = _sample_run("run_rebuild")
    aggregate = RunAggregate.for_new_run(run)
    await write_repo.create_run(run, events=aggregate.pull_events())
    aggregate = RunAggregate(await write_repo.get_run("run_rebuild"))
    aggregate.begin()
    module = aggregate.module("hom.login")
    aggregate.mark_running(module)
    aggregate.record_result(
        module,
        status=ModuleStatus.PASSED,
        message="ok",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    aggregate.finish_timing(module)
    aggregate.finalize(None)
    await write_repo.save_run(aggregate.persistable_state(), events=aggregate.pull_events())

    entries = await event_store.list_all()
    for entry in entries:
        await projections.apply(entry.event, entry.sequence_id)

    async def _snapshot() -> dict[str, list[dict]]:
        tables = ("run_history_index", "daily_system_status", "stats_rollup")
        result = {}
        for table in tables:
            rows = await db.fetchall(f"SELECT * FROM {table} ORDER BY rowid")
            result[table] = [dict(row) for row in rows]
        return result

    live = await _snapshot()
    assert live["run_history_index"], "라이브 적용이 행을 만들어야 전제 성립"

    for table in (*live.keys(), "anomaly_inbox_index"):
        await db.execute(f"DELETE FROM {table}")
    await db.execute("DELETE FROM projection_cursor")
    replayer = ProjectionHandlers(db, write_repo)
    for entry in entries:
        await replayer.apply(entry.event, entry.sequence_id)

    assert await _snapshot() == live


@pytest.mark.asyncio
async def test_legacy_checkpoints_migrate_to_cursor(tmp_path: Path) -> None:
    """구 projection_checkpoints 가 있는 DB 는 프로젝션별 최대 시퀀스로 커서를 승계한다."""
    db_path = tmp_path / "legacy.db"
    db = SqliteDatabase(db_path)
    await ensure_schema(db)
    # 구 체크포인트 테이블과 이벤트 2건을 재현한다(구 스키마 배포 상태 시뮬레이션).
    await db.execute(
        """
        CREATE TABLE projection_checkpoints (
            projection_name TEXT NOT NULL,
            event_id TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY (projection_name, event_id)
        )
        """
    )
    event_store = SqliteEventStore(db)
    first = _run_finished_event("run_a")
    second = _run_finished_event("run_b")
    await event_store.append_all([first, second])
    now = datetime.now(UTC).isoformat()
    await db.execute(
        "INSERT INTO projection_checkpoints VALUES (?, ?, ?)",
        ("stats_rollup", first.event_id, now),
    )
    await db.execute(
        "INSERT INTO projection_checkpoints VALUES (?, ?, ?)",
        ("stats_rollup", second.event_id, now),
    )
    await db.execute(
        "INSERT INTO projection_checkpoints VALUES (?, ?, ?)",
        ("run_history_index", first.event_id, now),
    )

    await ensure_schema(db)

    rows = await db.fetchall("SELECT projection_name, last_sequence_id FROM projection_cursor")
    cursors = {row["projection_name"]: row["last_sequence_id"] for row in rows}
    assert cursors["stats_rollup"] == 2
    assert cursors["run_history_index"] == 1
    dropped = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'projection_checkpoints'"
    )
    assert dropped is None
