from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import RunStatus, SuiteStatus
from app.core.models import Run, Schedule, SuiteRun, SuiteStep
from app.core.settings import E2ESettings
from app.execution.run_queue import RunExecutionQueue
from app.orchestrator.ops_service import OpsService


class _FakeRunRepo:
    async def list_runs(self) -> list[Run]:
        return [
            Run(
                run_id="run_active",
                system_code="hom",
                system_name="HOM",
                status=RunStatus.RUNNING,
                requested_at=datetime.now(UTC),
                modules=[],
                triggered_by="manual",
            ),
            Run(
                run_id="run_done",
                system_code="hom",
                system_name="HOM",
                status=RunStatus.PASSED,
                requested_at=datetime.now(UTC),
                modules=[],
            ),
        ]


class _FakeSuiteRepo:
    async def list_suites(self) -> list[SuiteRun]:
        return [
            SuiteRun(
                suite_id="suite_active",
                status=SuiteStatus.RUNNING,
                steps=[SuiteStep(system_code="hom", system_name="HOM", order=0, module_total=1)],
                requested_at=datetime.now(UTC),
                current_step_index=0,
            )
        ]


class _FakeScheduleRepo:
    async def list(self) -> list[Schedule]:
        return [
            Schedule(
                schedule_id="sch_1",
                schedule_kind="system",
                system_code="hom",
                system_name="HOM",
                name="nightly",
                cron="0 9 * * *",
                timezone="Asia/Seoul",
                enabled=True,
                created_at=datetime.now(UTC),
                next_run_at=datetime.now(UTC),
            )
        ]


async def test_ops_service_build_snapshot() -> None:
    queue = RunExecutionQueue(worker_count=2)
    queue.start()
    try:
        service = OpsService(
            settings=E2ESettings(),
            run_repo=_FakeRunRepo(),
            suite_repo=_FakeSuiteRepo(),
            schedule_repo=_FakeScheduleRepo(),
            run_queue=queue,
            scheduler=None,
        )
        snapshot = await service.build_snapshot()
    finally:
        await queue.stop()

    assert snapshot["runs"]["active_count"] == 1
    assert snapshot["suites"]["active_count"] == 1
    assert snapshot["schedules"]["enabled_count"] == 1
    assert snapshot["runtime"]["run_queue_workers"] == 2
