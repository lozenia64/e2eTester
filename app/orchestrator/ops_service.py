"""운영 스냅샷 — Run/Suite/스케줄·큐 상태를 관리자 UI에 제공."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.enums import RunStatus, SuiteStatus
from app.core.ops_buffer import ops_event_buffer
from app.core.settings import E2ESettings
from app.execution.run_queue import RunExecutionQueue
from app.scheduling.scheduler import SchedulerService
from app.storage.ports import RunRepositoryPort, ScheduleRepositoryPort, SuiteRepositoryPort

_ACTIVE_RUN_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
_ACTIVE_SUITE_STATUSES = {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}


class OpsService:
    def __init__(
        self,
        *,
        settings: E2ESettings,
        run_repo: RunRepositoryPort,
        suite_repo: SuiteRepositoryPort,
        schedule_repo: ScheduleRepositoryPort,
        run_queue: RunExecutionQueue,
        scheduler: SchedulerService | None = None,
    ) -> None:
        self._settings = settings
        self._run_repo = run_repo
        self._suite_repo = suite_repo
        self._schedule_repo = schedule_repo
        self._run_queue = run_queue
        self._scheduler = scheduler

    async def build_snapshot(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        runs = await self._run_repo.list_runs()
        suites = await self._suite_repo.list_suites()
        schedules = await self._schedule_repo.list()

        run_counts: dict[str, int] = {}
        active_runs: list[dict[str, Any]] = []
        for run in runs:
            key = run.status.value
            run_counts[key] = run_counts.get(key, 0) + 1
            if run.status not in _ACTIVE_RUN_STATUSES:
                continue
            active_runs.append(
                {
                    "run_id": run.run_id,
                    "system_code": run.system_code,
                    "status": run.status.value,
                    "triggered_by": run.triggered_by,
                    "suite_id": run.suite_id,
                    "schedule_id": run.schedule_id,
                    "requested_at": run.requested_at.isoformat(),
                    "created_by_user_name": run.created_by_user_name,
                }
            )
        active_runs.sort(key=lambda item: item["requested_at"], reverse=True)

        suite_counts: dict[str, int] = {}
        active_suites: list[dict[str, Any]] = []
        for suite in suites:
            key = suite.status.value
            suite_counts[key] = suite_counts.get(key, 0) + 1
            if suite.status not in _ACTIVE_SUITE_STATUSES:
                continue
            active_suites.append(
                {
                    "suite_id": suite.suite_id,
                    "status": suite.status.value,
                    "active_run_id": suite.active_run_id,
                    "awaiting_input_run_id": suite.awaiting_input_run_id,
                    "current_step_index": suite.current_step_index,
                    "step_total": len(suite.steps),
                    "requested_at": suite.requested_at.isoformat(),
                    "created_by_user_name": suite.created_by_user_name,
                }
            )
        active_suites.sort(key=lambda item: item["requested_at"], reverse=True)

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
                    "last_run_status": schedule.last_run_status.value if schedule.last_run_status else None,
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
                "schedule_timezone": self._scheduler.timezone_name if self._scheduler else self._settings.schedule_tz,
            },
            "runs": {
                "total": len(runs),
                "active_count": len(active_runs),
                "counts_by_status": run_counts,
                "active": active_runs[:30],
            },
            "suites": {
                "total": len(suites),
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
