"""Run 영구 삭제 — 재기동 backfill 후에도 부활하지 않음."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contexts.run.application.service import RunService
from app.contexts.run.contracts.query_rows import Page, RunSummaryFilter
from app.contexts.run.contracts.records import RunRecord
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.infrastructure.backfill.legacy_runs_projection_backfill import (
    backfill_from_legacy_runs,
)
from app.contexts.run.infrastructure.backfill.module_history_backfill import (
    backfill_module_history_index,
)
from app.contexts.run.infrastructure.backfill.run_history_backfill import backfill_run_history_index
from app.contexts.run.infrastructure.in_memory_run_control_store import InMemoryRunControlStore
from app.contexts.run.infrastructure.in_memory_run_input_store import InMemoryRunInputStore
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.run_queue import RunExecutionQueue
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.platform.artifact_manager import ArtifactManager
from app.platform.eventing.bus import EventBus
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.platform.snapshot_rebuild import rebuild_missing_run_snapshots
from app.registry.loader import ModuleRegistry
from tests.eventing_helpers import make_outbox_relay, make_projection_handlers


class _RealtimeSink:
    async def publish(self, event) -> None:
        return None


class _Env:
    def __init__(self, db: SqliteDatabase) -> None:
        self.db = db
        self.write_repo = SqliteRunWriteRepository(db)
        self.projections = make_projection_handlers(db, self.write_repo)
        self.sequence = 0

    async def apply(self, events) -> None:
        for event in events:
            self.sequence += 1
            await self.projections.apply(event, self.sequence)


async def _finish_run(env: _Env, run_id: str) -> Run:
    run = Run(
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
    )
    aggregate = RunAggregate.for_new_run(run)
    await env.write_repo.create_run(run, events=aggregate.pull_events())
    aggregate = RunAggregate(await env.write_repo.get_run(run_id))
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
    events = aggregate.pull_events()
    finished = aggregate.persistable_state()
    await env.write_repo.save_run(finished, events=events)
    await env.apply(events)
    return finished


def _service(
    write_repo: SqliteRunWriteRepository, summary_query: SqliteRunSummaryQuery, tmp_path: Path
) -> RunService:
    queue = RunExecutionQueue(worker_count=1, backend=InMemoryJobQueue())
    return RunService(
        registry=ModuleRegistry(),
        write_repo=write_repo,
        summary_query=summary_query,
        realtime=_RealtimeSink(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=SimulatedExecutionGateway(),
        event_bus=EventBus(),
        control_store=InMemoryRunControlStore(),
        input_store=InMemoryRunInputStore(),
        run_queue=queue,
        artifact_manager=ArtifactManager(root_dir=tmp_path / "artifacts"),
    )


async def _counts_for_run(db: SqliteDatabase, run_id: str) -> dict[str, int]:
    async def _count(sql: str, params: tuple = ()) -> int:
        row = await db.fetchone(sql, params)
        return int(row["c"])

    return {
        "domain_events": await _count(
            "SELECT COUNT(*) AS c FROM domain_events "
            "WHERE aggregate_type = 'Run' AND aggregate_id = ?",
            (run_id,),
        ),
        "snapshots": await _count(
            "SELECT COUNT(*) AS c FROM aggregate_snapshots WHERE stream_id = ?",
            (f"Run:{run_id}",),
        ),
        "run_history": await _count(
            "SELECT COUNT(*) AS c FROM run_history_index WHERE run_id = ?",
            (run_id,),
        ),
        "module_history": await _count(
            "SELECT COUNT(*) AS c FROM module_history_index WHERE run_id = ?",
            (run_id,),
        ),
        "legacy_runs": await _count(
            "SELECT COUNT(*) AS c FROM runs WHERE id = ?",
            (run_id,),
        ),
    }


async def _run_startup_backfills(db: SqliteDatabase, write_repo: SqliteRunWriteRepository) -> None:
    await rebuild_missing_run_snapshots(db)
    await backfill_run_history_index(db, write_repo)
    await backfill_module_history_index(db, write_repo)
    await backfill_from_legacy_runs(db, write_repo)


@pytest.mark.asyncio
async def test_hard_delete_survives_startup_backfill(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "hard_delete.db")
    await ensure_schema(db)
    env = _Env(db)
    run_id = "run_hard_delete"
    finished = await _finish_run(env, run_id)

    await db.execute(
        "INSERT OR REPLACE INTO runs (id, data) VALUES (?, ?)",
        (run_id, RunRecord.serialize(finished)),
    )

    before = await _counts_for_run(db, run_id)
    assert before["domain_events"] > 0
    assert before["snapshots"] == 1
    assert before["run_history"] == 1
    assert before["module_history"] == 1
    assert before["legacy_runs"] == 1

    summary_query = SqliteRunSummaryQuery(db)
    service = _service(env.write_repo, summary_query, tmp_path)
    await service.delete_run(run_id)

    after_delete = await _counts_for_run(db, run_id)
    assert after_delete == {
        "domain_events": 0,
        "snapshots": 0,
        "run_history": 0,
        "module_history": 0,
        "legacy_runs": 0,
    }

    await _run_startup_backfills(db, env.write_repo)

    after_backfill = await _counts_for_run(db, run_id)
    assert after_backfill == after_delete

    rows = await summary_query.list_summaries(RunSummaryFilter(), Page(limit=10))
    assert run_id not in {row.run_id for row in rows}


@pytest.mark.asyncio
async def test_delete_orphan_projection_without_snapshot(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "orphan_delete.db")
    await ensure_schema(db)
    write_repo = SqliteRunWriteRepository(db)
    run_id = "run_orphan"

    await db.execute(
        "INSERT INTO run_history_index "
        "(run_id, system_code, system_name, status, requested_at, triggered_by) "
        "VALUES (?, 'hom', 'HOM', 'PASSED', ?, 'manual')",
        (run_id, datetime.now(UTC).isoformat()),
    )
    await db.execute(
        "INSERT INTO module_history_index "
        "(run_id, module_id, system_code, module_name, status, triggered_by, requested_at) "
        "VALUES (?, 'hom.login', 'hom', 'login', 'PASSED', 'manual', ?)",
        (run_id, datetime.now(UTC).isoformat()),
    )
    await db.execute(
        "INSERT INTO runs (id, data) VALUES (?, ?)",
        (
            run_id,
            RunRecord.serialize(
                Run(
                    run_id=run_id,
                    system_code="hom",
                    system_name="HOM",
                    status=RunStatus.PASSED,
                    requested_at=datetime.now(UTC),
                    modules=[
                        RunModule(
                            module_id="hom.login",
                            name="login",
                            group="auth",
                            order=0,
                            status=ModuleStatus.PASSED,
                        ),
                    ],
                    selected_module_ids=["hom.login"],
                )
            ),
        ),
    )

    summary_query = SqliteRunSummaryQuery(db)
    service = _service(write_repo, summary_query, tmp_path)
    await service.delete_run(run_id)

    assert await _counts_for_run(db, run_id) == {
        "domain_events": 0,
        "snapshots": 0,
        "run_history": 0,
        "module_history": 0,
        "legacy_runs": 0,
    }

    await _run_startup_backfills(db, write_repo)
    counts = await _counts_for_run(db, run_id)
    assert counts["run_history"] == 0
