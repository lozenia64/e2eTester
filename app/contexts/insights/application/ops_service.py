"""운영 스냅샷 — Run/Suite/스케줄·큐 상태를 관리자 UI에 제공."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.contexts.scheduling.scheduler import SchedulerService
from app.core.enums import RunStatus, SuiteStatus
from app.core.ops_buffer import ops_event_buffer
from app.core.settings import E2ESettings
from app.execution.run_queue import RunExecutionQueue
from app.storage.ports import (
    RunSummaryQueryPort,
    ScheduleRepositoryPort,
    SuiteSummaryQueryPort,
)
from app.storage.query_rows import Page, RunSummaryFilter

_ACTIVE_RUN_STATUSES = frozenset({RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT})
_ACTIVE_SUITE_STATUSES = {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}


class OpsService:
    def __init__(
        self,
        *,
        settings: E2ESettings,
        run_summary_query: RunSummaryQueryPort,
        suite_summary_query: SuiteSummaryQueryPort,
        schedule_repo: ScheduleRepositoryPort,
        run_queue: RunExecutionQueue,
        scheduler: SchedulerService | None = None,
    ) -> None:
        self._settings = settings
        self._run_summary_query = run_summary_query
        self._suite_summary_query = suite_summary_query
        self._schedule_repo = schedule_repo
        self._run_queue = run_queue
        self._scheduler = scheduler

    async def build_snapshot(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        # 상태별 카운트는 SQL GROUP BY, 활성 목록은 상태 필터 SELECT — blob 스캔 없음.
        run_counts = await self._run_summary_query.counts_by_status()
        active_run_rows = await self._run_summary_query.list_summaries(
            RunSummaryFilter(statuses=_ACTIVE_RUN_STATUSES), Page(limit=30)
        )
        suite_counts = await self._suite_summary_query.counts_by_status()
        suite_rows = await self._suite_summary_query.list_summaries()
        schedules = await self._schedule_repo.list()

        active_runs = [
            {
                "run_id": row.run_id,
                "system_code": row.system_code,
                "status": row.status.value,
                "triggered_by": row.triggered_by,
                "suite_id": row.suite_id,
                "schedule_id": row.schedule_id,
                "requested_at": row.requested_at.isoformat(),
                "created_by_user_name": row.created_by_user_name,
            }
            for row in active_run_rows
        ]

        active_suites = [
            {
                "suite_id": row.suite_id,
                "status": row.status.value,
                "active_run_id": row.active_run_id,
                "awaiting_input_run_id": row.awaiting_input_run_id,
                "current_step_index": row.current_step_index,
                "step_total": row.step_total,
                "requested_at": row.requested_at.isoformat(),
                "created_by_user_name": row.created_by_user_name,
            }
            for row in suite_rows
            if row.status in _ACTIVE_SUITE_STATUSES
        ]

        enabled_schedules = [schedule for schedule in schedules if schedule.enabled]
        due_window = now + timedelta(hours=24)
        upcoming: list[dict[str, Any]] = []
        for schedule in enabled_schedules:
            if schedule.next_run_at is None:
                continue
            upcoming.append(
                {
                    "schedule_id": schedule.schedule_id,
                    "name": schedule.name,
                    "schedule_kind": schedule.schedule_kind,
                    "system_code": schedule.system_code,
                    "cron": schedule.cron,
                    "next_run_at": schedule.next_run_at.isoformat(),
                    "last_run_id": schedule.last_run_id,
                    "last_run_status": schedule.last_run_status.value
                    if schedule.last_run_status
                    else None,
                    "due_within_24h": schedule.next_run_at <= due_window,
                }
            )
        upcoming.sort(key=lambda item: item["next_run_at"])

        return {
            "generated_at": now.isoformat(),
            "runtime": {
                "log_level": self._settings.log_level,
                "log_format": self._settings.log_format,
                "run_queue_workers": self._run_queue.worker_count,
                "run_queue_pending": self._run_queue.pending_jobs,
                "run_queue_running": self._run_queue.is_running,
                "schedule_timezone": self._scheduler.timezone_name
                if self._scheduler
                else self._settings.schedule_tz,
            },
            "runs": {
                "total": sum(run_counts.values()),
                "active_count": len(active_runs),
                "counts_by_status": run_counts,
                "active": active_runs,
            },
            "suites": {
                "total": sum(suite_counts.values()),
                "active_count": len(active_suites),
                "counts_by_status": suite_counts,
                "active": active_suites[:20],
            },
            "schedules": {
                "total": len(schedules),
                "enabled_count": len(enabled_schedules),
                "due_within_24h_count": sum(1 for item in upcoming if item["due_within_24h"]),
                "upcoming": upcoming[:30],
            },
            "recent_events": ops_event_buffer.list_recent(limit=80),
        }
