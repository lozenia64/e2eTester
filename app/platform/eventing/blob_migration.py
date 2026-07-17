"""레거시 blob(``runs``) → 이벤트 스트림 1회성 마이그레이션 코어(WP-B6).

이벤트를 진실의 원천으로 승격한 뒤에도, 기존 배포 DB 의 Run 상태는 ``runs.data`` blob 에만
있고 이벤트 스트림이 없다. 이 모듈은 각 blob 을 읽어 ①FAILED→ANOMALY 정규화 ②종료 상태
전체를 담은 genesis 이벤트(``RunImported``) 1건으로 스트림을 개시 ③스냅샷 upsert 를 수행한다.
``evolve`` 가 ``RunImported`` 를 접어 권위 있는 스냅샷을 재구성하므로, 이후 프로젝션 리빌드가
이 스트림에서 결정적으로 파생된다.

이미 이벤트가 있는 Run 은 건너뛴다(멱등) — 재실행해도 스트림이 이중 개시되지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import ModuleStatus, RunStatus
from app.domain import events as domain_events
from app.domain.summary_fields import run_summary_fields
from app.platform.eventing.support import SqliteDatabase
from app.storage.records import RunRecord
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


@dataclass
class MigrationReport:
    migrated: int = 0
    skipped: int = 0
    normalized_failed: int = 0
    run_ids: list[str] = field(default_factory=list)


def _module_wire(module) -> dict:
    wire = module.model_dump(mode="json")
    wire.pop("logs", None)
    return wire


def _normalize_failed(run) -> bool:
    """FAILED(레거시) → ANOMALY 정규화. 실제로 바꿨으면 True."""
    changed = False
    if run.status == RunStatus.FAILED:
        run.status = RunStatus.ANOMALY
        changed = True
    for module in run.modules:
        if module.status == ModuleStatus.FAILED:
            module.status = ModuleStatus.ANOMALY
            changed = True
    return changed


async def _has_events(db: SqliteDatabase, run_id: str) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM domain_events WHERE aggregate_type = 'Run' AND aggregate_id = ? LIMIT 1",
        (run_id,),
    )
    return row is not None


async def migrate_run_blobs(db: SqliteDatabase) -> MigrationReport:
    """모든 ``runs`` blob 을 이벤트 스트림 + 스냅샷으로 마이그레이션한다(멱등)."""
    report = MigrationReport()
    write_repo = SqliteRunWriteRepository(db)
    rows = await db.fetchall("SELECT id, data FROM runs")
    for row in rows:
        run_id = row["id"]
        if await _has_events(db, run_id):
            report.skipped += 1
            continue
        data = row["data"]
        if isinstance(data, str) and data.startswith('"'):
            import json

            data = json.loads(data)
        run = RunRecord.deserialize(data)
        if _normalize_failed(run):
            report.normalized_failed += 1
        event = domain_events.run_imported(
            run_id,
            run_summary=run_summary_fields(run),
            all_modules=[_module_wire(module) for module in run.modules],
        )
        # save_run: 정규화된 blob 재기록 + genesis 이벤트 append(stream_position=1) + 스냅샷 upsert.
        await write_repo.save_run(run, events=[event])
        report.migrated += 1
        report.run_ids.append(run_id)
    return report
