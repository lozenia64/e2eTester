"""불완전한 Run 스냅샷을 레거시 blob·프로젝션 이력으로 복원한다.

일부 배포 DB 는 thin 이벤트만 있어 ``rebuild_state`` 가 빈 ``PENDING`` 스냅샷을 만들지만,
레거시 ``runs`` blob 또는 ``module_history_index`` 에는 종료 모듈이 남아 있다. 상세 화면·
startup 스냅샷 수리가 이 모듈로 권위 있는 Run 본문을 되살린다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import FailureAnalysis, Run, RunModule
from app.eventsourcing.support import SqliteDatabase
from app.storage.records import RunRecord

_ACTIVE_MODULE_STATUSES = frozenset(
    {
        ModuleStatus.PENDING,
        ModuleStatus.QUEUED,
        ModuleStatus.RUNNING,
        ModuleStatus.WAITING_INPUT,
    }
)


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def is_incomplete_snapshot(run: Run) -> bool:
    """스냅샷이 상세 화면에 쓸 수 없을 정도로 비어 있으면 True."""
    if not run.modules:
        return True
    if run.status in _ACTIVE_MODULE_STATUSES:
        has_terminal_module = any(
            module.status not in _ACTIVE_MODULE_STATUSES for module in run.modules
        )
        return not has_terminal_module
    return False


async def _runs_table_exists(db: SqliteDatabase) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs' LIMIT 1"
    )
    return row is not None


async def _load_legacy_blob(db: SqliteDatabase, run_id: str) -> Run | None:
    if not await _runs_table_exists(db):
        return None
    row = await db.fetchone("SELECT data FROM runs WHERE id = ?", (run_id,))
    if row is None:
        return None
    data = row["data"]
    if isinstance(data, str) and data.startswith('"'):
        data = json.loads(data)
    run = RunRecord.deserialize(data)
    return run if run.modules else None


def _module_from_history_row(row, *, order: int) -> RunModule:
    parts = row["module_id"].split(".")
    group = parts[-2] if len(parts) >= 2 else "default"
    artifacts_raw = row["artifacts"] if "artifacts" in row.keys() else "[]"
    if isinstance(artifacts_raw, str):
        artifacts = json.loads(artifacts_raw or "[]")
    else:
        artifacts = list(artifacts_raw or [])
    failure_analysis = None
    if row["ai_category"] or row["ai_summary"] or row["ai_action"]:
        failure_analysis = FailureAnalysis(
            category=row["ai_category"] or "",
            user_summary=row["ai_summary"] or "",
            recommended_action=row["ai_action"] or "",
            developer_details="",
        )
    return RunModule(
        module_id=row["module_id"],
        name=row["module_name"] or row["module_id"],
        group=group,
        order=order,
        status=ModuleStatus(row["status"]),
        started_at=_parse_dt(row["started_at"]),
        ended_at=_parse_dt(row["ended_at"]),
        duration_ms=row["duration_ms"],
        message=row["message"] or "",
        artifact_count=len(artifacts),
        artifacts=artifacts,
        current_url=row["current_url"],
        failure_analysis=failure_analysis,
    )


async def _reconstruct_from_history(db: SqliteDatabase, run_id: str, shell: Run) -> Run | None:
    summary = await db.fetchone("SELECT * FROM run_history_index WHERE run_id = ?", (run_id,))
    if summary is None:
        return None
    module_rows = await db.fetchall(
        """
        SELECT module_id, module_name, status, message, started_at, ended_at, duration_ms,
               current_url, artifacts, ai_category, ai_summary, ai_action
        FROM module_history_index
        WHERE run_id = ?
        ORDER BY COALESCE(ended_at, started_at), module_id
        """,
        (run_id,),
    )
    if not module_rows:
        return None
    modules = [_module_from_history_row(row, order=index) for index, row in enumerate(module_rows)]
    comparison = shell.comparison
    return Run(
        run_id=run_id,
        system_code=summary["system_code"],
        system_name=summary["system_name"] or summary["system_code"],
        status=RunStatus(summary["status"]),
        requested_at=_parse_dt(summary["requested_at"]) or shell.requested_at,
        started_at=_parse_dt(summary["started_at"]),
        ended_at=_parse_dt(summary["ended_at"]),
        modules=modules,
        selected_module_ids=[module.module_id for module in modules],
        awaiting_input_module_id=summary["awaiting_input_module_id"],
        awaiting_input_prompt=summary["awaiting_input_prompt"],
        triggered_by=summary["triggered_by"] or shell.triggered_by,
        schedule_id=summary["schedule_id"],
        suite_id=summary["suite_id"],
        comparison=comparison,
        created_by_user_id=summary["created_by_user_id"],
        created_by_user_name=summary["created_by_user_name"],
    )


async def resolve_run_snapshot(db: SqliteDatabase, run_id: str, snapshot: Run) -> Run:
    """스냅샷이 불완전하면 레거시 blob → 프로젝션 이력 순으로 복원한다."""
    if not is_incomplete_snapshot(snapshot):
        return snapshot
    legacy = await _load_legacy_blob(db, run_id)
    if legacy is not None:
        if legacy.comparison is None and snapshot.comparison is not None:
            legacy = legacy.model_copy(update={"comparison": snapshot.comparison})
        return legacy
    reconstructed = await _reconstruct_from_history(db, run_id, snapshot)
    return reconstructed if reconstructed is not None else snapshot


async def load_run_without_snapshot(db: SqliteDatabase, run_id: str) -> Run | None:
    """스냅샷 행이 없을 때 blob·프로젝션만으로 Run 을 복원한다."""
    legacy = await _load_legacy_blob(db, run_id)
    if legacy is not None:
        return legacy
    shell = Run(
        run_id=run_id,
        system_code="",
        system_name="",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[],
    )
    return await _reconstruct_from_history(db, run_id, shell)
