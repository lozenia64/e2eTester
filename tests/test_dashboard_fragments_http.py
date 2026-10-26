"""일간 대시보드 HTMX fragment HTML 계약 테스트.

Premium Light 리디자인 후 fragment 응답이 카드 리스트·히어로 마크업을 반환하는지 검증한다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_daily_queries, get_daily_summary_queries, get_run_service
from app.api.routes_daily import router as daily_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.insights.application.daily_dashboard import build_daily_dashboard_from_projection
from app.core.enums import ModuleStatus
from app.registry.loader import ModuleRegistry
from tests.conftest import make_run_summary_row, make_status_row

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


class FakeDailySummaryQueries:
    """DailySummaryQueries 대체 — kpi 프래그먼트는 totals/date_label/generated_at/attention/
    cards 를 쓴다(zone_a_kpi.html 참고). totals 는 넘겨받은 dashboard_data 를 그대로 쓰고,
    healing/stats 컨텍스트가 없는 이 fake 에서는 나머지 카드 3장을 카드 계약(key·label·
    value·unit·period·note·tone·href·estimated)에 맞는 고정값으로 채운다."""

    def __init__(self, data: dict) -> None:
        self._data = data

    async def get_daily_summary(
        self,
        *,
        user_id: str | None = None,
        allowed_system_codes: list[str] | None = None,
        is_admin: bool = False,
    ) -> dict:
        totals = self._data["totals"]
        cards = [
            {
                "key": "pass_rate",
                "label": "통과율",
                "value": totals["pass_rate"],
                "unit": "%",
                "period": "오늘",
                "note": f"{totals['passed']}/{totals['modules']} 모듈 정상",
                "tone": "passed",
                "href": "",
                "estimated": False,
            },
            {
                "key": "self_healed",
                "label": "스스로 복구",
                "value": 3,
                "unit": "건",
                "period": "오늘",
                "note": "이번 달 누적 12건",
                "tone": "running",
                "href": "/self-healing",
                "estimated": False,
            },
            {
                "key": "pending_patches",
                "label": "내 승인 대기",
                "value": 2,
                "unit": "건",
                "period": "패치",
                "note": "자동 생성된 수정 diff 검토",
                "tone": "anomaly",
                "href": "/self-healing#patches",
                "estimated": False,
            },
            {
                "key": "savings",
                "label": "이번 달 절감",
                "value": 120,
                "unit": "h",
                "period": "이번 달",
                "note": "480회 · 12개 모듈 × 수동 추정치 (기준 8/1)",
                "tone": "passed",
                "href": "/admin/modules",
                "estimated": True,
            },
        ]
        return {**self._data, "cards": cards}


class FakeRunService:
    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry

    def list_systems(self):
        return self._registry.list_systems()


def _build_all_not_inspected_dashboard(registry: ModuleRegistry) -> dict:
    systems = registry.list_systems()
    return build_daily_dashboard_from_projection(
        systems,
        [],
        [],
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
    )


def _build_realistic_six_system_dashboard() -> dict:
    """레지스트리 6시스템·혼합 모듈 상태로 현실적인 일간 대시보드 payload."""
    registry = ModuleRegistry()
    systems = registry.list_systems()
    assert len(systems) >= 6

    status_rows = []
    run_summaries = []
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
        run_id = f"run_{code}"
        status_rows.extend(
            make_status_row(system_code=code, module_id=mid, last_status=st, last_run_id=run_id)
            for mid, st in statuses.items()
        )
        run_summaries.append(
            make_run_summary_row(system_code=code, run_id=run_id, requested_at=GEN_AT)
        )

    return build_daily_dashboard_from_projection(
        systems,
        status_rows,
        run_summaries,
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
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
    app.dependency_overrides[get_daily_summary_queries] = lambda: FakeDailySummaryQueries(
        dashboard_data
    )
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


def test_matrix_fragment_uses_unique_stable_system_row_ids(
    client: TestClient, dashboard_data: dict
) -> None:
    """주의도 정렬이 바뀌어도 morph가 같은 시스템 행을 보존할 식별자가 필요하다."""
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    row_ids = re.findall(r'<div class="dash-sys-row"\s+id="([^"]+)"', html)
    expected_ids = [f"dash-system-{system['system_code']}" for system in dashboard_data["systems"]]

    assert sorted(row_ids) == sorted(expected_ids)
    assert len(row_ids) == len(set(row_ids))


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_kpi_fragment_renders_hero(client: TestClient) -> None:
    response = client.get("/api/dashboard/daily/fragments/kpi")
    assert response.status_code == 200
    html = response.text
    # _build_realistic_six_system_dashboard 는 hom 시스템에 ERROR 를 심어 두므로
    # 히어로 문장은 점검실패 분기를 탄다(zone_a_kpi.html 의 상태 분기 참고).
    assert "점검실패" in html
    assert "우선 확인이 필요합니다" in html
    assert 'class="status-hero"' in html
    assert 'class="status-hero__ring"' in html
    assert 'data-passed="' in html
    assert 'data-total="' in html
    assert 'class="status-hero__headline"' in html
    assert 'class="status-hero__cards"' in html


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
    assert 'class="status-hero__ring"' in html
    assert 'data-passed="0"' in html
    assert 'data-total="' in html
    assert "아직 점검이 시작되지 않았습니다" in html


@pytest.mark.spec("SPEC-UI-005", "AC-004")
def test_kpi_fragment_always_four_stat_tiles(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/kpi").text
    assert 'class="status-hero__cards"' in html
    assert html.count('class="kpi-card"') == 4


@pytest.mark.spec("SPEC-UI-005", "AC-007")
def test_matrix_fragment_renders_module_cells(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    assert "dash-sys-row__cells" in html
    assert "dash-cell__glyph" in html
    assert "dash-sys-row__count" in html
    assert "dash-sys-row__segment" not in html
    assert "dash-sys-row__chevron" not in html
    assert "dash-mod" not in html


@pytest.mark.spec("SPEC-UI-007", "AC-009")
def test_matrix_fragment_uses_native_name_button_without_row_button_semantics(
    client: TestClient,
) -> None:
    """모듈 링크와 상세 제어는 중첩되지 않는 별도 네이티브 요소여야 한다."""
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    row_start = html.index('<div class="dash-sys-row"')
    row_tag = html[row_start : html.index(">", row_start) + 1]
    assert "tabindex=" not in row_tag
    assert 'role="button"' not in row_tag
    assert "aria-label=" not in row_tag
    name_button = re.search(
        r'<button type="button" class="dash-sys-row__name" data-action="detail" '
        r'aria-label="(?P<label>[^\"]+) 상세 보기">(?P<name>[^<]+)</button>',
        html,
    )
    assert name_button is not None
    assert name_button.group("label") == name_button.group("name")


@pytest.mark.spec("SPEC-UI-007", "AC-008")
def test_matrix_fragment_error_system_has_attention_priority(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    # hom has ERROR in _build_realistic_six_system_dashboard
    assert 'data-system-code="hom"' in html
    idx = html.index('data-system-code="hom"')
    row_chunk = html[idx : idx + 800]
    assert 'data-priority="attention"' in row_chunk


@pytest.mark.spec("SPEC-UI-006", "AC-005")
def test_fragments_include_status_hero_contract(client: TestClient) -> None:
    kpi = client.get("/api/dashboard/daily/fragments/kpi").text
    matrix = client.get("/api/dashboard/daily/fragments/matrix").text
    assert 'class="status-hero"' in kpi
    assert 'class="status-hero__ring"' in kpi
    assert 'class="status-hero__headline"' in kpi
    assert 'class="status-hero__cards"' in kpi
    assert "dash-sys-row__cells" in matrix


def test_matrix_fragment_shows_recovered_cell_flag(registry: ModuleRegistry) -> None:
    """자동 복구된 모듈은 일간 현황 매트릭스 셀에 ⟳ 불안정 표식을 노출해야 한다."""
    system = registry.list_systems()[0]
    module_id = system.modules[0].module_id
    data = build_daily_dashboard_from_projection(
        [system],
        [
            make_status_row(
                system_code=system.system_code,
                module_id=module_id,
                last_status=ModuleStatus.PASSED,
                recovered=True,
            )
        ],
        [make_run_summary_row(system_code=system.system_code)],
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
    )
    user = User(
        user_id="u_recovered",
        email="recovered@test.local",
        name="Recovered Tester",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=[system.system_code],
        created_at=GEN_AT,
    )
    app = _build_app(user=user, dashboard_data=data, registry=registry)
    with TestClient(app) as c:
        html = c.get("/api/dashboard/daily/fragments/matrix").text
    assert "dash-cell__flag" in html


def test_matrix_fragment_omits_cell_flag_for_clean_module(registry: ModuleRegistry) -> None:
    system = registry.list_systems()[0]
    module_id = system.modules[0].module_id
    data = build_daily_dashboard_from_projection(
        [system],
        [
            make_status_row(
                system_code=system.system_code,
                module_id=module_id,
                last_status=ModuleStatus.PASSED,
            )
        ],
        [make_run_summary_row(system_code=system.system_code)],
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
    )
    user = User(
        user_id="u_clean",
        email="clean@test.local",
        name="Clean Tester",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=[system.system_code],
        created_at=GEN_AT,
    )
    app = _build_app(user=user, dashboard_data=data, registry=registry)
    with TestClient(app) as c:
        html = c.get("/api/dashboard/daily/fragments/matrix").text
    assert "dash-cell__flag" not in html


def test_activity_fragment_renders_items(client):
    res = client.get("/api/dashboard/daily/fragments/activity")
    assert res.status_code == 200
    html = res.text
    assert 'id="dash-zone-activity"' in html
    assert 'class="dash-activity"' in html
    # 항목 하나 이상이 시각·시스템·모듈을 담는다
    assert "dash-activity__item" in html


def test_activity_fragment_uses_unique_stable_item_ids(client, dashboard_data: dict) -> None:
    """시간 역순 재정렬에도 morph가 같은 시스템·모듈 활동을 보존해야 한다."""
    html = client.get("/api/dashboard/daily/fragments/activity").text
    item_ids = re.findall(r'<li class="dash-activity__item"\s+id="([^"]+)"', html)
    expected_ids = [
        f"dash-activity-{item['system_code']}-{item['module_id']}"
        for item in dashboard_data["activity"]
    ]

    assert item_ids == expected_ids
    assert len(item_ids) == len(set(item_ids))


def test_activity_fragment_unknown_zone_still_404(client):
    assert client.get("/api/dashboard/daily/fragments/nope").status_code == 404


@pytest.mark.spec("SPEC-UI-005", "AC-007")
def test_matrix_fragment_orders_passed_anomaly_error_then_not_inspected(
    client: TestClient, dashboard_data: dict
) -> None:
    """대시보드 화면 순서: 전체 정상 > 이상징후 > 오류 > (진행 중 등) > 미점검."""
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    codes = re.findall(r'<div class="dash-sys-row"\s+id="dash-system-([^"]+)"', html)
    passed = [
        s["system_code"]
        for s in dashboard_data["systems"]
        if s["summary_badge"]["tone"] == "passed"
    ]
    assert passed
    assert codes[: len(passed)] == passed
    assert codes[len(passed) :] == ["mhm", "hom", "hrp", "hwtc"]
