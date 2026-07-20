"""불완전 스냅샷 fallback — 레거시 blob·module_history 복원."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.run.contracts.records import RunRecord
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.run_snapshot_fallback import (
    is_incomplete_snapshot,
    resolve_run_snapshot,
)
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.domain.summary_fields import module_history_fields, run_summary_fields
from app.orchestrator.queries.run_queries import RunQueries
from app.platform.eventing.handlers import _module_history_upsert, _run_history_upsert
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.platform.snapshot_rebuild import repair_incomplete_run_snapshots


def _passed_run(run_id: str) -> Run:
    return Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="chbot.main.access",
                name="메인화면 접속",
                group="access",
                order=0,
                status=ModuleStatus.PASSED,
                duration_ms=1000,
                message="완료",
            ),
            RunModule(
                module_id="chbot.simple.auth",
                name="간편인증",
                group="auth",
                order=1,
                status=ModuleStatus.PASSED,
                duration_ms=2000,
                message="완료",
            ),
        ],
        selected_module_ids=["chbot.main.access", "chbot.simple.auth"],
    )


@pytest.mark.asyncio
async def test_resolve_run_snapshot_from_legacy_blob(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "fallback.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    run_id = "run_legacy_view"
    source = _passed_run(run_id)

    empty = Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇",
        status=RunStatus.PENDING,
        requested_at=source.requested_at,
        modules=[],
    )
    await write_repo.create_run(empty, events=RunAggregate.for_new_run(empty).pull_events())
    await db.execute(
        "INSERT OR REPLACE INTO runs (id, data) VALUES (?, ?)",
        (run_id, RunRecord.serialize(source)),
    )

    snapshot = await write_repo.get_run(run_id)
    assert len(snapshot.modules) == 2
    assert snapshot.status == RunStatus.PASSED
    assert not is_incomplete_snapshot(snapshot)


@pytest.mark.asyncio
async def test_resolve_run_snapshot_from_module_history(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "history.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    run_id = "run_history_view"
    source = _passed_run(run_id)

    empty = Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇",
        status=RunStatus.PENDING,
        requested_at=source.requested_at,
        modules=[],
    )
    await write_repo.create_run(empty, events=RunAggregate.for_new_run(empty).pull_events())

    summary = run_summary_fields(source)
    await db.execute(*_run_history_upsert(run_id, summary))
    for module in source.modules:
        await db.execute(
            *_module_history_upsert(run_id, summary, module_history_fields(source, module))
        )

    resolved = await resolve_run_snapshot(db, run_id, empty)
    assert len(resolved.modules) == 2
    assert resolved.status == RunStatus.PASSED
    assert resolved.modules[0].group == "default"


@pytest.mark.asyncio
async def test_module_history_reconstruction_avoids_wrong_group_guess(tmp_path: Path) -> None:
    """module_id 세그먼트로 group 을 유추하면 manifest 와 불일치할 수 있다."""
    db = SqliteDatabase(tmp_path / "group.db")
    await ensure_schema(db)
    run_id = "run_group"
    source = Run(
        run_id=run_id,
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.main.access",
                name="메인화면 접속",
                group="access",
                order=0,
                status=ModuleStatus.PASSED,
            ),
        ],
        selected_module_ids=["hom.main.access"],
    )
    summary = run_summary_fields(source)
    await db.execute(*_run_history_upsert(run_id, summary))
    await db.execute(
        *_module_history_upsert(run_id, summary, module_history_fields(source, source.modules[0]))
    )

    shell = Run(
        run_id=run_id,
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PENDING,
        requested_at=source.requested_at,
        modules=[],
    )
    resolved = await resolve_run_snapshot(db, run_id, shell)
    assert resolved.modules[0].group == "default"
    assert resolved.modules[0].group != "main"


@pytest.mark.asyncio
async def test_repair_incomplete_snapshots_persists(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "repair.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    run_id = "run_repair"
    source = _passed_run(run_id)
    empty = Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇",
        status=RunStatus.PENDING,
        requested_at=source.requested_at,
        modules=[],
    )
    await write_repo.create_run(empty, events=RunAggregate.for_new_run(empty).pull_events())
    await db.execute(
        "INSERT OR REPLACE INTO runs (id, data) VALUES (?, ?)",
        (run_id, RunRecord.serialize(source)),
    )

    repaired = await repair_incomplete_run_snapshots(db)
    assert repaired == 1

    row = await db.fetchone(
        "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?",
        (f"Run:{run_id}",),
    )
    stored = RunRecord.deserialize(row["state_json"])
    assert len(stored.modules) == 2
    assert stored.status == RunStatus.PASSED


@pytest.mark.asyncio
async def test_run_queries_detail_hydrates_incomplete_snapshot(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "detail.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    run_id = "run_detail"
    source = _passed_run(run_id)
    empty = Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇",
        status=RunStatus.PENDING,
        requested_at=source.requested_at,
        modules=[],
    )
    await write_repo.create_run(empty, events=RunAggregate.for_new_run(empty).pull_events())
    await db.execute(
        "INSERT OR REPLACE INTO runs (id, data) VALUES (?, ?)",
        (run_id, RunRecord.serialize(source)),
    )

    queries = RunQueries(
        summary_query=SqliteRunSummaryQuery(db),
        write_repo=write_repo,
        log_store=InMemoryRunLogStore(),
    )
    run = await queries.get_run_detail(run_id)
    assert len(run.modules) == 2
    assert run.modules[0].name == "메인화면 접속"
