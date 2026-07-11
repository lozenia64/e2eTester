"""운영 인텔리전스(이상징후 인박스 + 시스템 인사이트) 애플리케이션 서비스.

집계 규칙은 순수 빌더(``insights_*`` 모듈)가 담당하고, 이 서비스는 I/O 만 한다: Run/처리레코드
조회 → 순수 빌더 호출 → Plotly figure 첨부. ``StatsService`` 와 같은 얇은 인터프리터 패턴.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.enums import AnomalyState
from app.core.models import AnomalyHandling
from app.orchestrator.insights_anomalies import build_anomaly_items
from app.orchestrator.insights_breakdown import build_module_breakdown
from app.orchestrator.insights_charts import (
    calendar_heatmap_chart,
    cumulative_step_duration_bar,
    failure_category_donut,
    health_trend_chart,
    module_duration_sparkline,
)
from app.orchestrator.insights_common import (
    ANOMALY_OR_ERROR_STATUSES,
    split_module_run_id,
)
from app.orchestrator.insights_health import build_system_health
from app.orchestrator.insights_timeline import build_system_timeline
from app.orchestrator.run_actor import load_actor_context

if TYPE_CHECKING:
    from app.auth.service import UserService
    from app.registry.loader import ModuleRegistry
    from app.storage.ports import (
        AnomalyHandlingStorePort,
        RunHistoryQueryPort,
        ScheduleRepositoryPort,
        SuiteRepositoryPort,
    )


class InsightsService:
    def __init__(
        self,
        run_repo: RunHistoryQueryPort,
        registry: ModuleRegistry,
        anomaly_store: AnomalyHandlingStorePort,
        *,
        user_service: UserService | None = None,
        suite_repo: SuiteRepositoryPort | None = None,
        schedule_repo: ScheduleRepositoryPort | None = None,
    ) -> None:
        self._run_repo = run_repo
        self._registry = registry
        self._anomaly_store = anomaly_store
        self._user_service = user_service
        self._suite_repo = suite_repo
        self._schedule_repo = schedule_repo

    # ── 시스템/타임존 헬퍼 ───────────────────────────────────────────────────
    def _system(self, system_code: str):
        return self._registry.get_system(system_code)  # KeyError -> 404

    async def _runs_for_system(self, system_code: str):
        return await self._run_repo.list_runs_by_system(system_code)

    @staticmethod
    def _tz():
        from app.scheduling.scheduler import _resolve_timezone

        tz, _name = _resolve_timezone()
        return tz

    # ── 이상징후 인박스 ─────────────────────────────────────────────────────
    async def list_anomalies(self, allowed_system_codes: list[str] | None = None) -> dict[str, Any]:
        runs = await self._run_repo.list_all_runs()
        handlings = {h.module_run_id: h for h in await self._anomaly_store.list()}
        systems = self._registry.list_systems()
        return build_anomaly_items(
            systems, runs, handlings, allowed_system_codes=allowed_system_codes
        )

    async def list_assignees(self, allowed_system_codes: list[str] | None = None) -> list[dict]:
        if self._user_service is None:
            return []
        users = await self._user_service.list_users()
        return [
            {"user_id": u.user_id, "name": u.name, "email": u.email}
            for u in users
            if getattr(u, "is_active", True)
        ]

    async def update_anomaly(
        self,
        module_run_id_value: str,
        *,
        state: str | None = None,
        assignee_user_id: str | None = None,
        memo: str | None = None,
        actor_user_id: str | None = None,
        allowed_system_codes: list[str] | None = None,
    ) -> AnomalyHandling:
        """이상건의 처리 레코드를 갱신(부분 병합)한다. 대상이 실제 이상건인지 검증한다."""
        run_id, mod_id = split_module_run_id(module_run_id_value)
        run = await self._run_repo.get_run(run_id)  # KeyError -> 404
        if allowed_system_codes is not None and run.system_code not in allowed_system_codes:
            raise KeyError(module_run_id_value)  # 권한 밖은 존재를 노출하지 않고 404
        module = next((m for m in run.modules if m.module_id == mod_id), None)
        if module is None or module.status not in ANOMALY_OR_ERROR_STATUSES:
            raise KeyError(module_run_id_value)

        current = await self._anomaly_store.get(module_run_id_value) or AnomalyHandling(
            module_run_id=module_run_id_value
        )

        new_state = current.state
        if state is not None:
            new_state = AnomalyState(state)  # ValueError -> 400

        new_assignee_id = current.assignee_user_id
        new_assignee_name = current.assignee_name
        if assignee_user_id is not None:
            if assignee_user_id == "":
                new_assignee_id = None
                new_assignee_name = None
            else:
                new_assignee_id = assignee_user_id
                new_assignee_name = await self._resolve_user_name(assignee_user_id)

        updated = AnomalyHandling(
            module_run_id=module_run_id_value,
            state=new_state,
            assignee_user_id=new_assignee_id,
            assignee_name=new_assignee_name,
            memo=current.memo if memo is None else memo,
            updated_at=datetime.now(UTC),
            updated_by_user_id=actor_user_id,
        )
        return await self._anomaly_store.upsert(updated)

    async def _resolve_user_name(self, user_id: str) -> str | None:
        if self._user_service is None:
            return None
        for user in await self._user_service.list_users():
            if user.user_id == user_id:
                return user.name
        return None

    # ── 시스템 헬스 ─────────────────────────────────────────────────────────
    async def get_system_health(self, system_code: str, *, days: int = 30) -> dict[str, Any]:
        system = self._system(system_code)
        runs = await self._runs_for_system(system_code)
        health = build_system_health(system, runs, days=days, now=datetime.now(UTC), tz=self._tz())
        health["charts"] = {
            "insight-health-trend": health_trend_chart(health["daily"]),
            "insight-health-calendar": calendar_heatmap_chart(health["daily"]),
        }
        return health

    # ── 시스템 타임라인 ─────────────────────────────────────────────────────
    async def get_system_timeline(self, system_code: str, *, limit: int = 50) -> dict[str, Any]:
        system = self._system(system_code)
        runs = await self._runs_for_system(system_code)
        actor_context = None
        if self._user_service and self._suite_repo and self._schedule_repo:
            actor_context = await load_actor_context(
                self._user_service, self._suite_repo, self._schedule_repo
            )
        return build_system_timeline(system, runs, limit=limit, actor_context=actor_context)

    # ── 모듈 딥다이브 ───────────────────────────────────────────────────────
    async def get_module_breakdown(self, system_code: str) -> dict[str, Any]:
        system = self._system(system_code)
        runs = await self._runs_for_system(system_code)
        breakdown = build_module_breakdown(system, runs)
        for module in breakdown["modules"]:
            module["charts"] = {
                "sparkline": module_duration_sparkline(module["duration_series"]),
                "donut": failure_category_donut(module["failure_categories"]),
            }
        breakdown["charts"] = {
            "insight-cumulative": cumulative_step_duration_bar(breakdown["cumulative"]),
        }
        return breakdown
