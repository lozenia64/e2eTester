"""수트 상세 레이아웃 계약.

JS 는 data-* 로 노드를 찾는다. 마크업을 바꾸면서 훅을 잃으면 화면은 멀쩡해
보이는데 소켓이 아무것도 갱신하지 못한다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.api.dependencies import get_run_summary_query, get_suite_service
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteRun, SuiteStep

GEN_AT = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def _user() -> User:
    return User(
        user_id="op",
        email="op@test.local",
        name="점검자",
        role="admin",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=[],
        created_at=GEN_AT,
    )


def _suite() -> SuiteRun:
    return SuiteRun(
        suite_id="suite_demo",
        status=SuiteStatus.RUNNING,
        steps=[
            SuiteStep(
                system_code="hom",
                system_name="대표홈",
                order=0,
                run_id="r0",
                status=SuiteStatus.PASSED,
                module_total=10,
            ),
            SuiteStep(
                system_code="mhm",
                system_name="모바일대표홈",
                order=1,
                run_id="r1",
                status=SuiteStatus.RUNNING,
                module_total=8,
            ),
            SuiteStep(
                system_code="fp",
                system_name="위촉서류",
                order=2,
                run_id=None,
                status=SuiteStatus.PENDING,
                module_total=3,
            ),
        ],
        current_step_index=1,
        requested_at=GEN_AT,
        started_at=GEN_AT,
        selected_system_codes=["hom", "mhm", "fp"],
    )


class _FakeSuiteService:
    async def get_suite(self, suite_id: str) -> SuiteRun:
        return _suite()


class _FakeRunSummaryQuery:
    async def avg_duration_ms_by_system(self, *, days: int = 30) -> dict[str, int]:
        return {"hom": 192_000, "mhm": 108_000}


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_suite_service] = _FakeSuiteService
    app.dependency_overrides[get_run_summary_query] = _FakeRunSummaryQuery
    return TestClient(app)


def _html(client: TestClient) -> str:
    response = client.get("/suites/suite_demo")
    assert response.status_code == 200
    return response.text


def _content(client: TestClient) -> str:
    """suite.html 이 렌더한 몫만 — base.html 의 사이드바/네비 크롬은 제외한다.

    외형 계약(색 유틸리티 0 · 죽은 훅 클래스 0)은 이 화면의 마크업에 대한 것이다.
    공용 셸의 Tailwind 클래스까지 걸면 어떤 화면도 통과할 수 없다.
    """
    html = _html(client)
    return html.split('id="suite-root"', 1)[1].split('id="toast-container"', 1)[0]


def test_root_carries_the_suite_shell_class(client) -> None:
    assert 'class="suite' in _html(client)


def test_step_rows_are_a_vertical_list(client) -> None:
    """2열 그리드가 남아 있으면 파이프라인이 아니다."""
    html = _html(client)
    assert "md:grid-cols-2" not in html
    assert 'data-step-order="0"' in html


def test_expanded_step_comes_from_the_server(client) -> None:
    """클라이언트가 규칙을 재구현하지 않는다 — 서버 값이 마크업에 찍혀 있어야 한다."""
    assert 'data-expanded="true"' in _html(client)


def test_baselines_are_injected_once(client) -> None:
    html = _html(client)
    assert "data-step-baselines=" in html


def test_js_hooks_survive(client) -> None:
    html = _html(client)
    for hook in (
        'id="suite-cancel"',
        'id="suite-status"',
        'id="suite-otp-panel"',
        'id="suite-otp-form"',
        'id="suite-otp-countdown"',
        'id="suite-step-list"',
        'data-role="step-run-link"',
        'data-role="step-module-progress"',
        'id="suite-ring"',
        'id="suite-now"',
        'id="suite-counts"',
        'id="suite-progress-elapsed"',
        'id="suite-progress-eta"',
    ):
        assert hook in html, hook


def test_no_tailwind_color_utilities(client) -> None:
    """외형은 컴포넌트 CSS 가 갖는다(설계 §1.3) — 이 화면의 마크업에 색 유틸리티가 없다."""
    content = _content(client)
    assert not re.findall(
        r'class="[^"]*\b(?:bg|text|border)-(?:gray|amber|red|emerald|indigo)-\d{2,3}', content
    )


def test_dead_hook_classes_are_gone(client) -> None:
    """정의가 없는 채로 붙어 있던 클래스들(설계 §3.5). 컴포넌트 CSS 가 자리를 대신한다.

    `otp-panel` 은 부분 문자열(`suite-otp-panel`)로도 걸리므로 class 속성 안의
    단어 경계로 확인한다.
    """
    content = _content(client)
    assert 'class="suite-step-card' not in content
    assert not re.findall(r'class="[^"]*\botp-panel\b', content)
