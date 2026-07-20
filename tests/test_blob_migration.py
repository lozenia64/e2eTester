"""레거시 blob → 이벤트 스트림 마이그레이션(WP-B6) — 정규화·genesis·멱등·리빌드 검증."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.run.contracts.records import RunRecord
from app.contexts.run.infrastructure.migration.legacy_blob_migration import migrate_run_blobs
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.platform.snapshot_rebuild import rebuild_run_snapshots


async def _seed_legacy_blob(db: SqliteDatabase, run: Run) -> None:
    """이벤트 스트림 없이 runs blob 만 있는 레거시 배포 상태를 재현한다."""
    await db.execute(
        "INSERT INTO runs (id, data) VALUES (?, ?)",
        (run.run_id, RunRecord.serialize(run)),
    )


def _legacy_run(run_id: str, *, status: RunStatus, module_status: ModuleStatus) -> Run:
    now = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=now,
        started_at=now,
        ended_at=now,
        modules=[
            RunModule(
                module_id="hom.access",
                name="접속",
                group="access",
                order=0,
                status=module_status,
                max_attempts=1,
            ),
        ],
        selected_module_ids=["hom.access"],
        triggered_by="manual",
    )


@pytest.mark.asyncio
async def test_migration_normalizes_failed_and_creates_stream(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "legacy.db")
    await ensure_schema(db)
    await _seed_legacy_blob(
        db, _legacy_run("run_legacy", status=RunStatus.FAILED, module_status=ModuleStatus.FAILED)
    )

    report = await migrate_run_blobs(db)
    assert report.migrated == 1
    assert report.normalized_failed == 1

    # genesis 이벤트가 생겼다.
    events = await db.fetchall(
        "SELECT event_type, stream_position FROM domain_events WHERE aggregate_id = ?",
        ("run_legacy",),
    )
    assert [e["event_type"] for e in events] == ["RunImported"]
    assert events[0]["stream_position"] == 1

    # 마이그레이션 결과(스냅샷 — 유일 상태 저장소)가 정규화됐다(FAILED→ANOMALY).
    # 레거시 runs blob 은 마이그레이션 입력일 뿐 더 이상 갱신/조회되지 않는다(WP-B6).
    snap = await db.fetchone(
        "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", ("Run:run_legacy",)
    )
    migrated_run = RunRecord.deserialize(snap["state_json"])
    assert migrated_run.status == RunStatus.ANOMALY
    assert migrated_run.modules[0].status == ModuleStatus.ANOMALY


@pytest.mark.asyncio
async def test_migration_snapshot_rebuildable_from_events(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "rebuild.db")
    await ensure_schema(db)
    await _seed_legacy_blob(
        db, _legacy_run("run_r", status=RunStatus.PASSED, module_status=ModuleStatus.PASSED)
    )
    await migrate_run_blobs(db)

    # 스냅샷을 지우고 genesis 이벤트만으로 재구성 → 동일 상태(이벤트=진실).
    await db.execute("DELETE FROM aggregate_snapshots")
    report = await rebuild_run_snapshots(db)
    assert report.rebuilt == 1
    assert report.ok
    snap = await db.fetchone(
        "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", ("Run:run_r",)
    )
    rebuilt = RunRecord.deserialize(snap["state_json"])
    assert rebuilt.status == RunStatus.PASSED
    assert rebuilt.modules[0].module_id == "hom.access"


@pytest.mark.asyncio
async def test_migration_is_idempotent(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "idem.db")
    await ensure_schema(db)
    await _seed_legacy_blob(
        db, _legacy_run("run_i", status=RunStatus.PASSED, module_status=ModuleStatus.PASSED)
    )
    first = await migrate_run_blobs(db)
    second = await migrate_run_blobs(db)
    assert first.migrated == 1
    assert second.migrated == 0
    assert second.skipped == 1
    # 스트림이 이중 개시되지 않았다.
    events = await db.fetchall(
        "SELECT event_type FROM domain_events WHERE aggregate_id = ?", ("run_i",)
    )
    assert len(events) == 1
