"""일간 대시보드 HTMX fragment HTML 계약 테스트.

Premium Light 리디자인 후 fragment 응답이 카드 리스트·히어로 마크업을 반환하는지 검증한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_daily_queries, get_run_service
from app.api.routes_daily import router as daily_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.insights.application.daily_dashboard import build_daily_dashboard
from app.core.enums import ModuleStatus
from app.registry.loader import ModuleRegistry
from tests.test_daily_dashboard import _run

GEN_AT = datetime(2026, 8, 15, 5, 0, tzinfo=UTC)


class FakeDailyDashboardQueries:
    """DailyDashboardQueries 대체 — 고정 집계 데이터 반환."""

    def __init__(self, data: dict) -> None:
        self._data = data

    async def get_daily_dashboard(
        self,
        *,
        allowed_system_codes: list[str] | None = None,
    ) -> dict:
        if allowed_system_codes is None:
            return self._data
        allowed = set(allowed_system_codes)
        systems = [s for s in self._data["systems"] if s["system_code"] in allowed]
        return {**self._data, "systems": systems}


class FakeRunService:
    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry

    def list_systems(self):
        return self._registry.list_systems()


def _build_all_not_inspected_dashboard(registry: ModuleRegistry) -> dict:
    systems = registry.list_systems()
    return build_daily_dashboard(
        systems,
        [],
        generated_at=GEN_AT,
        date_label="2026-08-15",
    )


def _build_realistic_six_system_dashboard() -> dict:
    """레지스트리 6시스템·혼합 모듈 상태로 현실적인 일간 대시보드 payload."""
    registry = ModuleRegistry()
    systems = registry.list_systems()
    assert len(systems) >= 6

    runs = []
    for sys in systems:
        code = sys.system_code
        if code == "hwtc":
            continue
        if code == "hom":
            statuses = {
                m.module_id: (ModuleStatus.ERROR if i == 0 else ModuleStatus.PASSED)
                for i, m in enumerate(sys.modules)
            }
        elif code == "mhm":
            statuses = {m.module_id: ModuleStatus.ANOMALY for m in sys.modules[:1]}
            for m in sys.modules[1:]:
                statuses[m.module_id] = ModuleStatus.PASSED
        elif code == "hrp":
            statuses = {m.module_id: ModuleStatus.RUNNING for m in sys.modules[:1]}
            for m in sys.modules[1:]:
                statuses[m.module_id] = ModuleStatus.PASSED
        else:
            statuses = {m.module_id: ModuleStatus.PASSED for m in sys.modules}
        runs.append(_run(code, statuses, at=GEN_AT))

    return build_daily_dashboard(
        systems,
        runs,
        generated_at=GEN_AT,
        date_label="2026-08-15",
    )


def _build_app(
    *,
    user: User,
    dashboard_data: dict,
    registry: ModuleRegistry,
) -> FastAPI:
    app = FastAPI()
    app.include_router(daily_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_daily_queries] = lambda: FakeDailyDashboardQueries(dashboard_data)
    app.dependency_overrides[get_run_service] = lambda: FakeRunService(registry)
    return app


@pytest.fixture
def registry() -> ModuleRegistry:
    return ModuleRegistry()


@pytest.fixture
def dashboard_data(registry: ModuleRegistry) -> dict:
    data = _build_realistic_six_system_dashboard()
    assert len(data["systems"]) >= 6
    return data


@pytest.fixture
def client(registry: ModuleRegistry, dashboard_data: dict) -> TestClient:
    codes = [s.system_code for s in registry.list_systems()]
    user = User(
        user_id="dash_user",
        email="dash@test.local",
        name="Dash User",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=codes,
        created_at=GEN_AT,
    )
    app = _build_app(user=user, dashboard_data=dashboard_data, registry=registry)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.spec("SPEC-UI-004", "AC-005")
def test_matrix_fragment_renders_card_rows(client: TestClient) -> None:
    response = client.get("/api/dashboard/daily/fragments/matrix")
    assert response.status_code == 200
    html = response.text
    assert "dash-sys-row" in html
    assert "cytoscape" not in html.lower()
    assert "dash-matrix-chart" not in html


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_kpi_fragment_renders_hero(client: TestClient) -> None:
    response = client.get("/api/dashboard/daily/fragments/kpi")
    assert response.status_code == 200
    html = response.text
    assert "오늘의 점검 현황" in html
    assert "dash-hero__rate" in html


@pytest.mark.spec("SPEC-UI-005", "AC-002")
def test_kpi_fragment_renders_empty_day_summary(
    client: TestClient, registry: ModuleRegistry
) -> None:
    data = _build_all_not_inspected_dashboard(registry)
    user = User(
        user_id="u",
        email="u@t.local",
        name="U",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=[s.system_code for s in registry.list_systems()],
        created_at=GEN_AT,
    )
    app = _build_app(user=user, dashboard_data=data, registry=registry)
    with TestClient(app) as c:
        html = c.get("/api/dashboard/daily/fragments/kpi").text
    assert "dash-hero__rate-label" in html
    assert "통과율" in html
    assert "dash-hero__summary" in html
    assert "아직 점검이 시작되지 않았습니다" in html


@pytest.mark.spec("SPEC-UI-005", "AC-004")
def test_kpi_fragment_always_four_stat_tiles(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/kpi").text
    assert html.count('class="dash-stats__tile"') == 4
    assert "이상징후" in html


@pytest.mark.spec("SPEC-UI-005", "AC-007")
def test_matrix_fragment_renders_segment_and_chevron(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    assert "dash-sys-row__segment" in html
    assert "dash-sys-row__chevron" in html
    assert "dash-mod__glyph" in html


@pytest.mark.spec("SPEC-UI-005", "AC-009")
def test_matrix_fragment_error_system_has_attention_priority(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    # hom has ERROR in _build_realistic_six_system_dashboard
    assert 'data-system-code="hom"' in html
    idx = html.index('data-system-code="hom"')
    row_chunk = html[idx : idx + 800]
    assert 'data-priority="attention"' in row_chunk
