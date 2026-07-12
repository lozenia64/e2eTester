from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.enums import ModuleStatus
from app.core.models import SystemUsageStat, UsageStats, UserUsageStat
from app.core.status_labels import MODULE_ANOMALY_STATUSES
from app.orchestrator.run_actor import load_actor_context
from app.orchestrator.stats_charts import build_usage_charts
from app.storage.module_settings_repository import ModuleSettingsRepositoryPort
from app.storage.ports import (
    ScheduleRepositoryPort,
    StatsQueryPort,
    SuiteSummaryQueryPort,
)

if TYPE_CHECKING:
    from app.auth.service import UserService
    from app.registry.loader import ModuleRegistry
    from app.storage.query_rows import ModuleHistoryRow


class StatsService:
    def __init__(
        self,
        stats_query: StatsQueryPort,
        suite_summary_query: SuiteSummaryQueryPort,
        registry: ModuleRegistry,
        module_settings_repo: ModuleSettingsRepositoryPort | None = None,
        user_service: UserService | None = None,
        schedule_repo: ScheduleRepositoryPort | None = None,
    ) -> None:
        self._stats_query = stats_query
        self._suite_summary_query = suite_summary_query
        self._registry = registry
        self._module_settings_repo = module_settings_repo
        self._user_service = user_service
        self._schedule_repo = schedule_repo

    async def get_usage_stats(
        self,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> UsageStats:
        all_runs = await self._stats_query.list_usage_run_rows(from_dt, to_dt)
        module_rows = await self._stats_query.list_usage_module_rows(from_dt, to_dt)
        modules_by_run: dict[str, list[ModuleHistoryRow]] = {}
        for row in module_rows:
            modules_by_run.setdefault(row.run_id, []).append(row)

        system_map: dict[str, SystemUsageStat] = {}
        user_map: dict[str | None, UserUsageStat] = {}

        system_defs = {s.system_code: s.name for s in self._registry.list_systems()}

        module_seconds: dict[str, dict[str, int]] = {}
        for system in self._registry.list_systems():
            module_seconds[system.system_code] = {
                m.module_id: m.estimated_manual_seconds for m in system.modules
            }

        if self._module_settings_repo is not None:
            overrides = await self._module_settings_repo.list()
            for override in overrides:
                parts = override.module_id.split(".", 1)
                if len(parts) == 2:
                    sys_code = parts[0]
                    if sys_code in module_seconds:
                        module_seconds[sys_code][override.module_id] = (
                            override.estimated_manual_seconds
                        )

        actor_context = None
        if self._user_service is not None and self._schedule_repo is not None:
            actor_context = await load_actor_context(
                self._user_service,
                self._suite_summary_query,
                self._schedule_repo,
            )

        for run in all_runs:
            run_modules = modules_by_run.get(run.run_id, [])
            passed = sum(1 for m in run_modules if m.status == ModuleStatus.PASSED)
            failed = sum(1 for m in run_modules if m.status in MODULE_ANOMALY_STATUSES)
            duration = sum(m.duration_ms or 0 for m in run_modules)
            sys_seconds = module_seconds.get(run.system_code, {})
            saved_seconds = sum(
                sys_seconds.get(m.module_id, 0)
                for m in run_modules
                if m.status == ModuleStatus.PASSED
            )
            code = run.system_code
            if code not in system_map:
                system_map[code] = SystemUsageStat(
                    system_code=code,
                    system_name=system_defs.get(code, code),
                    runs=0,
                    modules_passed=0,
                    modules_failed=0,
                    total_duration_ms=0,
                    manual_seconds_saved=0,
                )
            s = system_map[code]
            system_map[code] = s.model_copy(
                update={
                    "runs": s.runs + 1,
                    "modules_passed": s.modules_passed + passed,
                    "modules_failed": s.modules_failed + failed,
                    "total_duration_ms": s.total_duration_ms + duration,
                    "manual_seconds_saved": s.manual_seconds_saved + saved_seconds,
                }
            )

            uid = run.created_by_user_id
            user_name = run.created_by_user_name
            email = None
            if actor_context is not None:
                uid, user_name = actor_context.resolve(run)
                if uid and uid in actor_context.users_by_id:
                    _name, email = actor_context.users_by_id[uid]

            if uid not in user_map:
                user_map[uid] = UserUsageStat(
                    user_id=uid,
                    user_name=user_name,
                    email=email,
                    total_runs=0,
                    total_modules_passed=0,
                    total_modules_failed=0,
                    total_duration_ms=0,
                    manual_seconds_saved=0,
                    by_system=[],
                )
            u = user_map[uid]

            u_sys_map = {s2.system_code: s2 for s2 in u.by_system}
            if code not in u_sys_map:
                u_sys_map[code] = SystemUsageStat(
                    system_code=code,
                    system_name=system_defs.get(code, code),
                    runs=0,
                    modules_passed=0,
                    modules_failed=0,
                    total_duration_ms=0,
                    manual_seconds_saved=0,
                )
            us = u_sys_map[code]
            u_sys_map[code] = us.model_copy(
                update={
                    "runs": us.runs + 1,
                    "modules_passed": us.modules_passed + passed,
                    "modules_failed": us.modules_failed + failed,
                    "total_duration_ms": us.total_duration_ms + duration,
                    "manual_seconds_saved": us.manual_seconds_saved + saved_seconds,
                }
            )

            user_map[uid] = u.model_copy(
                update={
                    "total_runs": u.total_runs + 1,
                    "total_modules_passed": u.total_modules_passed + passed,
                    "total_modules_failed": u.total_modules_failed + failed,
                    "total_duration_ms": u.total_duration_ms + duration,
                    "manual_seconds_saved": u.manual_seconds_saved + saved_seconds,
                    "by_system": list(u_sys_map.values()),
                }
            )

        by_user = sorted(user_map.values(), key=lambda u: u.total_runs, reverse=True)
        by_system = sorted(system_map.values(), key=lambda s: s.runs, reverse=True)

        stats = UsageStats(
            period_from=from_dt,
            period_to=to_dt,
            generated_at=datetime.now(UTC),
            total_runs=len(all_runs),
            total_users=sum(1 for uid in user_map if uid is not None),
            by_user=by_user,
            by_system=by_system,
        )
        return stats.model_copy(update={"charts": build_usage_charts(stats)})
