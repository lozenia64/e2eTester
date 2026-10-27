"""성과 대시보드의 기간·절감 산식·관리자 계약."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_stats_service
from app.api.routes_admin import router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.insights.application.stats_service import StatsService
from app.contexts.insights.infrastructure.in_memory_stats_query import InMemoryStatsQuery
from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.stats_models import ModuleSettings
from app.core.system_models import ModuleDefinition, SystemDefinition
from tests.test_stats_service import _FakeRegistry, _FakeSuiteSummaryQuery

KST = ZoneInfo("Asia/Seoul")


def moment(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=KST)


def make_service(*, overrides=None):
    registry = _FakeRegistry(
        [
            SystemDefinition(
                system_code=code,
                name=f"시스템 {code}",
                description="",
                modules=[
                    ModuleDefinition(
                        module_id=f"{code}.login",
                        system_code=code,
                        name="로그인",
                        description="",
                        group="인증",
                        order=0,
                        estimated_manual_seconds=45,
                    )
                ],
            )
            for code in ["hom", "mhm"]
        ]
    )
    repo = InMemoryRunRepository()
    return StatsService(
        InMemoryStatsQuery(repo), _FakeSuiteSummaryQuery(), registry, module_settings_repo=overrides
    ), repo


async def seed(
    repo, id, at, *, code="hom", status=RunStatus.PASSED, module_status=ModuleStatus.PASSED
):
    await repo.create_run(
        Run(
            run_id=id,
            system_code=code,
            system_name=code,
            requested_at=at.astimezone(UTC),
            status=status,
            modules=[
                RunModule(
                    module_id=f"{code}.login",
                    name="로그인",
                    group="인증",
                    order=0,
                    status=module_status,
                )
            ],
            selected_module_ids=[f"{code}.login"],
        )
    )


@pytest.mark.spec("SPEC-INSIGHT-003", "AC-003")
async def test_performance_matches_usage_without_rounding_and_fills_days():
    service, repo = make_service()
    now = moment(2026, 10, 3, 9, 42)
    await seed(repo, "previous", moment(2026, 9, 1))
    await seed(repo, "first", moment(2026, 10, 1))
    await seed(repo, "third", moment(2026, 10, 3), code="mhm", status=RunStatus.ANOMALY)
    await seed(repo, "error", moment(2026, 10, 3), status=RunStatus.ERROR)
    await seed(repo, "failed_module", moment(2026, 10, 3), module_status=ModuleStatus.ANOMALY)
    await seed(repo, "future", moment(2026, 10, 3, 10))
    data = await service.get_performance_dashboard(now=now)
    stats = await service.get_usage_stats(moment(2026, 10, 1).astimezone(UTC), now.astimezone(UTC))
    assert data["total_seconds"] == sum(s.manual_seconds_saved for s in stats.by_system) == 90
    assert data["previous_seconds"] == 45
    assert data["change_percent"] == 100
    assert data["total_runs"] == stats.total_runs == 3
    assert [p["cumulative_seconds"] for p in data["daily"]] == [45, 45, 90]
    assert sum(s["saved_seconds"] for s in data["by_system"]) == 90
    assert "by_user" not in data and "charts" not in data


@pytest.mark.parametrize(
    ("now", "previous_end"),
    [
        (moment(2026, 3, 31, 9), "2026-02-28T23:59:59.999999+09:00"),
        (moment(2024, 3, 31, 9), "2024-02-29T23:59:59.999999+09:00"),
        (moment(2026, 1, 1), "2025-12-01T00:00:00+09:00"),
        (moment(2026, 10, 27, 9, 42), "2026-09-27T09:42:00+09:00"),
    ],
)
async def test_performance_periods_and_empty_results(now, previous_end):
    service, _ = make_service()
    data = await service.get_performance_dashboard(now=now.astimezone(UTC))
    assert data["period"]["previous_to"] == previous_end
    assert data["period"]["from"].startswith(f"{now.year}-{now.month:02d}-01T00:00")
    assert data["total_seconds"] == 0
    assert data["change_percent"] is None
    assert len(data["daily"]) == now.day
    assert len(data["by_system"]) == 2
    assert all(p["cumulative_seconds"] == 0 for p in data["daily"])


async def test_overrides_zero_basis_and_korean_midnight():
    class Settings:
        async def list(self):
            return [
                ModuleSettings(
                    module_id="hom.login", estimated_manual_seconds=0, updated_at=datetime.now(UTC)
                ),
                ModuleSettings(
                    module_id="mhm.login", estimated_manual_seconds=75, updated_at=datetime.now(UTC)
                ),
            ]

    service, repo = make_service(overrides=Settings())
    await seed(repo, "september", moment(2026, 9, 30, 23, 59), code="mhm")
    await seed(repo, "october", moment(2026, 10, 1), code="mhm")
    await seed(repo, "zero", moment(2026, 10, 1))
    data = await service.get_performance_dashboard(now=moment(2026, 10, 1, 0, 1))
    assert data["total_seconds"] == 75
    assert data["daily"][-1]["cumulative_seconds"] == 75
    assert data["by_system"][0]["system_code"] == "mhm"
    stats = await service.get_usage_stats(moment(2026, 10, 1), moment(2026, 10, 1, 0, 1))
    assert sum(s.manual_seconds_saved for s in stats.by_system) == 75


def test_performance_api_requires_admin_and_has_no_personal_breakdown():
    from types import SimpleNamespace

    app = FastAPI()
    app.include_router(router)
    service, _ = make_service()
    app.dependency_overrides[get_stats_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
    with TestClient(app) as client:
        assert client.get("/api/admin/dashboard/performance").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
        res = client.get("/api/admin/dashboard/performance")
        assert res.status_code == 200
        assert res.json()["timezone"] == "Asia/Seoul"
        assert "by_user" not in res.json()
