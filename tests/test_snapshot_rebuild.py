"""이벤트 스토어 = 진실의 원천 — 스트림 위치·스냅샷 파생·리빌드 동등성(WP-B2).

핵심 불변식: ``aggregate_snapshots`` 는 ``domain_events`` 폴드의 파생 캐시다. 스냅샷을 지워도
이벤트만으로 동일하게 재구성되고(``rebuild_run_snapshots``), 각 이벤트는 스트림 내 단조
``stream_position`` 을 부여받는다(낙관적 동시성 좌표).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.domain.run_aggregate import RunAggregate
from app.eventsourcing.snapshot_rebuild import rebuild_run_snapshots
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.storage.records import RunRecord
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


def _run(run_id: str) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PENDING,
        requested_at=datetime(2026, 7, 12, 3, 0, tzinfo=UTC),
        modules=[
            RunModule(
                module_id="hom.access",
                name="접속",
                group="access",
                order=0,
                status=ModuleStatus.PENDING,
                max_attempts=1,
            ),
            RunModule(
                module_id="hom.login",
                name="로그인",
                group="auth",
                order=1,
                depends_on=["hom.access"],
                status=ModuleStatus.PENDING,
                max_attempts=1,
            ),
        ],
        selected_module_ids=["hom.access", "hom.login"],
        triggered_by="manual",
    )


async def _persist_full_run(db: SqliteDatabase, run_id: str) -> Run:
    repo = SqliteRunWriteRepository(db)
    run = _run(run_id)
    aggregate = RunAggregate.for_new_run(run)
    await repo.create_run(run, events=aggregate.pull_events())

    aggregate = RunAggregate(await repo.get_run(run_id))
    aggregate.begin()
    for module_id in ("hom.access", "hom.login"):
        module = aggregate.module(module_id)
        aggregate.mark_queued(module)
        aggregate.mark_running(module)
        aggregate.record_result(
            module,
            status=ModuleStatus.PASSED,
            message="완료",
            artifacts=[f"{run_id}/{module_id}/final.png"],
            current_url="https://www.hwgeneralins.com/",
            dialog_messages=[],
        )
        aggregate.finish_timing(module)
    aggregate.finalize(None)
    await repo.save_run(aggregate.persistable_state(), events=aggregate.pull_events())
    return await repo.get_run(run_id)


@pytest.mark.asyncio
async def test_stream_position_is_monotonic_per_stream(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "pos.db")
    await ensure_schema(db)
    await _persist_full_run(db, "run_pos")

    rows = await db.fetchall(
        "SELECT stream_position FROM domain_events "
        "WHERE aggregate_type = 'Run' AND aggregate_id = ? ORDER BY sequence_id ASC",
        ("run_pos",),
    )
    positions = [row["stream_position"] for row in rows]
    assert positions == list(range(1, len(positions) + 1))


@pytest.mark.asyncio
async def test_snapshot_written_and_versioned(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "snap.db")
    await ensure_schema(db)
    run = await _persist_full_run(db, "run_snap")

    row = await db.fetchone(
        "SELECT version, state_json FROM aggregate_snapshots WHERE stream_id = ?",
        ("Run:run_snap",),
    )
    assert row is not None
    # 스냅샷 version = 마지막 stream_position(스트림 이벤트 총수).
    count = await db.fetchone(
        "SELECT COUNT(*) AS n FROM domain_events WHERE aggregate_type='Run' AND aggregate_id=?",
        ("run_snap",),
    )
    assert row["version"] == count["n"]
    # 스냅샷 state_json 은 blob 형태와 도메인 동등하다.
    assert RunRecord.deserialize(row["state_json"]) == run


@pytest.mark.asyncio
async def test_snapshots_rebuildable_from_events_alone(tmp_path: Path) -> None:
    """스냅샷을 전부 지워도 domain_events 폴드로 동일하게 재구성된다(이벤트=진실)."""
    db = SqliteDatabase(tmp_path / "rebuild.db")
    await ensure_schema(db)
    run = await _persist_full_run(db, "run_rebuild")

    before = await db.fetchone(
        "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", ("Run:run_rebuild",)
    )
    await db.execute("DELETE FROM aggregate_snapshots")

    report = await rebuild_run_snapshots(db)
    assert report.rebuilt == 1
    assert report.ok

    after = await db.fetchone(
        "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", ("Run:run_rebuild",)
    )
    assert after is not None
    # 재구성 스냅샷 == 원래 blob == 라이브 Run(도메인 동등).
    assert RunRecord.deserialize(after["state_json"]) == run
    assert RunRecord.deserialize(after["state_json"]) == RunRecord.deserialize(before["state_json"])


@pytest.mark.asyncio
async def test_verify_only_detects_no_mismatch_for_consistent_store(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "verify.db")
    await ensure_schema(db)
    await _persist_full_run(db, "run_verify")

    report = await rebuild_run_snapshots(db, verify_only=True)
    assert report.ok
    assert report.mismatches == []


@pytest.mark.asyncio
async def test_suite_snapshot_rebuildable_from_events(tmp_path: Path) -> None:
    """Suite 스트림도 이벤트 폴드로 스냅샷이 재구성된다(Run 과 동형)."""
    from app.core.enums import SuiteStatus
    from app.core.suite_models import SuiteRun, SuiteStep
    from app.domain.suite_aggregate import SuiteAggregate
    from app.eventsourcing.snapshot_rebuild import rebuild_all_snapshots
    from app.storage.sqlite_suite_write_repository import SqliteSuiteWriteRepository

    db = SqliteDatabase(tmp_path / "suite.db")
    await ensure_schema(db)
    repo = SqliteSuiteWriteRepository(db)
    suite = SuiteRun(
        suite_id="suite_s",
        status=SuiteStatus.PENDING,
        steps=[SuiteStep(system_code="hom", system_name="HOM", order=0)],
        requested_at=datetime(2026, 7, 12, 3, 0, tzinfo=UTC),
        selected_system_codes=["hom"],
    )
    aggregate = SuiteAggregate.for_new_suite(suite)
    await repo.create_suite(suite, events=aggregate.pull_events())
    aggregate = SuiteAggregate(await repo.get_suite("suite_s"))
    aggregate.begin()
    step = aggregate.start_step(0)
    aggregate.link_run(step, "run_child")
    aggregate.record_step_result(step, SuiteStatus.PASSED, step_index=0)
    aggregate.finalize(SuiteStatus.PASSED)
    await repo.save_suite(aggregate.persistable_state(), events=aggregate.pull_events())

    # stream_position 이 단조.
    rows = await db.fetchall(
        "SELECT stream_position FROM domain_events WHERE aggregate_type='Suite' "
        "AND aggregate_id=? ORDER BY sequence_id ASC",
        ("suite_s",),
    )
    assert [r["stream_position"] for r in rows] == list(range(1, len(rows) + 1))

    # 스냅샷을 지우고 이벤트만으로 재구성 → 일치.
    await db.execute("DELETE FROM aggregate_snapshots")
    report = await rebuild_all_snapshots(db)
    assert report.ok
    snap = await db.fetchone(
        "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?", ("Suite:suite_s",)
    )
    assert snap is not None
