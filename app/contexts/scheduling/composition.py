"""Scheduling BC composition — SchedulerService + run retention."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contexts.run.application.service import RunService
from app.contexts.scheduling.infrastructure.sqlite_schedule_repository import (
    SqliteScheduleRepository,
)
from app.contexts.scheduling.run_retention import RunRetentionScheduler, RunRetentionService
from app.contexts.scheduling.scheduler import SchedulerService
from app.contexts.suite.application.service import SuiteService
from app.orchestrator.queries import RunQueries


@dataclass
class SchedulingContainer:
    schedule_repository: SqliteScheduleRepository = field(init=False)
    scheduler: SchedulerService = field(init=False)
    retention_scheduler: RunRetentionScheduler | None = field(init=False, default=None)


def compose_scheduler(
    run_commands: RunService,
    suite_service: SuiteService,
    repository: SqliteScheduleRepository,
    run_queries: RunQueries,
) -> SchedulerService:
    return SchedulerService(
        run_commands=run_commands,
        suite_service=suite_service,
        repository=repository,
        run_queries=run_queries,
    )


def compose_retention_scheduler(
    run_service: RunService,
) -> RunRetentionScheduler | None:
    return RunRetentionScheduler.from_env(RunRetentionService(run_service))
