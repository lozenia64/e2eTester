from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.enums import ModuleStatus
from app.core.models import UsageStats, UserUsageStat, SystemUsageStat
from app.storage.ports import RunRepositoryPort, SuiteRepositoryPort
from app.storage.module_settings_repository import ModuleSettingsRepositoryPort

if TYPE_CHECKING:
    from app.registry.loader import ModuleRegistry


class StatsService:
    def __init__(
        self,
        run_repo: RunRepositoryPort,
        suite_repo: SuiteRepositoryPort,
        registry: "ModuleRegistry",
        module_settings_repo: ModuleSettingsRepositoryPort | None = None,
    ) -> None:
        self._run_repo = run_repo
        self._suite_repo = suite_repo
        self._registry = registry
        self._module_settings_repo = module_settings_repo

    async def get_usage_stats(
        self,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> UsageStats:
        all_runs = await self._run_repo.list_runs()

        if from_dt is not None:
            all_runs = [r for r in all_runs if r.requested_at >= from_dt]
        if to_dt is not None:
            all_runs = [r for r in all_runs if r.requested_at <= to_dt]

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
                        module_seconds[sys_code][override.module_id] = override.estimated_manual_seconds

        for run in all_runs:
            passed = sum(1 for m in run.modules if m.status == ModuleStatus.PASSED)
            failed = sum(1 for m in run.modules if m.status == ModuleStatus.FAILED)
            duration = sum(m.duration_ms or 0 for m in run.modules)
            sys_seconds = module_seconds.get(run.system_code, {})
            saved_seconds = sum(
                sys_seconds.get(m.module_id, 0)
                for m in run.modules
                if m.status == ModuleStatus.PASSED
            )
            saved = saved_seconds // 60

            code = run.system_code
            if code not in system_map:
                system_map[code] = SystemUsageStat(
                    system_code=code,
                    system_name=system_defs.get(code, code),
                    runs=0,
                    modules_passed=0,
                    modules_failed=0,
                    total_duration_ms=0,
                    manual_minutes_saved=0,
                )
            s = system_map[code]
            system_map[code] = s.model_copy(update={
                "runs": s.runs + 1,
                "modules_passed": s.modules_passed + passed,
                "modules_failed": s.modules_failed + failed,
                "total_duration_ms": s.total_duration_ms + duration,
                "manual_minutes_saved": s.manual_minutes_saved + saved,
            })

            uid = run.created_by_user_id
            if uid not in user_map:
                user_map[uid] = UserUsageStat(
                    user_id=uid,
                    user_name=run.created_by_user_name,
                    email=None,
                    total_runs=0,
                    total_modules_passed=0,
                    total_modules_failed=0,
                    total_duration_ms=0,
                    manual_minutes_saved=0,
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
                    manual_minutes_saved=0,
                )
            us = u_sys_map[code]
            u_sys_map[code] = us.model_copy(update={
                "runs": us.runs + 1,
                "modules_passed": us.modules_passed + passed,
                "modules_failed": us.modules_failed + failed,
                "total_duration_ms": us.total_duration_ms + duration,
                "manual_minutes_saved": us.manual_minutes_saved + saved,
            })

            user_map[uid] = u.model_copy(update={
                "total_runs": u.total_runs + 1,
                "total_modules_passed": u.total_modules_passed + passed,
                "total_modules_failed": u.total_modules_failed + failed,
                "total_duration_ms": u.total_duration_ms + duration,
                "manual_minutes_saved": u.manual_minutes_saved + saved,
                "by_system": list(u_sys_map.values()),
            })

        by_user = sorted(user_map.values(), key=lambda u: u.total_runs, reverse=True)
        by_system = sorted(system_map.values(), key=lambda s: s.runs, reverse=True)

        return UsageStats(
            period_from=from_dt,
            period_to=to_dt,
            generated_at=datetime.now(timezone.utc),
            total_runs=len(all_runs),
            total_users=sum(1 for uid in user_map if uid is not None),
            by_user=by_user,
            by_system=by_system,
        )
