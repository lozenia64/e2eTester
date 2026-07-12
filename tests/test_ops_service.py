from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import RunStatus, SuiteStatus
from app.core.schedule_models import Schedule
from app.core.settings import E2ESettings
from app.execution.run_queue import RunExecutionQueue
from app.orchestrator.ops_service import OpsService
from app.storage.query_rows import Page, RunSummaryFilter, RunSummaryRow, SuiteSummaryRow


def _run_row(run_id: str, status: RunStatus) -> RunSummaryRow:
    return RunSummaryRow(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=datetime.now(UTC),
        started_at=None,
        ended_at=None,
        schedule_id=None,
        suite_id=None,
        created_by_user_id=None,
        created_by_user_name=None,
        triggered_by="manual",
        awaiting_input_module_id=None,
        awaiting_input_prompt=None,
        module_total=0,
        module_defined_total=0,
        module_skipped=0,
        module_passed=0,
        current_module_name=None,
        failed_module_name=None,
    )


class _FakeRunSummaryQuery:
    async def counts_by_status(self) -> dict[str, int]:
        return {RunStatus.RUNNING.value: 1, RunStatus.PASSED.value: 1}

    async def list_summaries(self, query: RunSummaryFilter, page: Page) -> list[RunSummaryRow]:
        rows = [_run_row("run_active", RunStatus.RUNNING), _run_row("run_done", RunStatus.PASSED)]
        if query.statuses is not None:
            rows = [row for row in rows if row.status in query.statuses]
        return rows[: page.limit]


class _FakeSuiteSummaryQuery:
    async def counts_by_status(self) -> dict[str, int]:
        return {SuiteStatus.RUNNING.value: 1}

    async def list_summaries(self, *, limit: int | None = None) -> list[SuiteSummaryRow]:
        return [
            SuiteSummaryRow(
                suite_id="suite_active",
                status=SuiteStatus.RUNNING,
                requested_at=datetime.now(UTC),
                started_at=None,
                ended_at=None,
                current_step_index=0,
                active_run_id=None,
                awaiting_input_run_id=None,
                awaiting_input_prompt=None,
                browser_mode="headed",
                selected_system_codes=("hom",),
                triggered_by="manual",
                schedule_id=None,
                created_by_user_id=None,
                created_by_user_name=None,
                step_total=1,
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
            run_summary_query=_FakeRunSummaryQuery(),
            suite_summary_query=_FakeSuiteSummaryQuery(),
            schedule_repo=_FakeScheduleRepo(),
            run_queue=queue,
            scheduler=None,
        )
        snapshot = await service.build_snapshot()
    finally:
        await queue.stop()

    assert snapshot["runs"]["active_count"] == 1
    assert snapshot["runs"]["total"] == 2
    assert snapshot["suites"]["active_count"] == 1
    assert snapshot["schedules"]["enabled_count"] == 1
    assert snapshot["runtime"]["run_queue_workers"] == 2
