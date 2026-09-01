"""런 상세 2열 레이아웃과 프런트엔드 훅 계약."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_dashboard
from app.api.dependencies import get_healing_service, get_run_queries
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.views.view import RunView
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import RunModule

GEN_AT = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


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


def _run() -> RunView:
    return RunView(
        run_id="run_demo",
        system_code="hom",
        system_name="대표홈",
        status=RunStatus.RUNNING,
        status_label="점검 중",
        requested_at=GEN_AT,
        modules=[
            RunModule(
                module_id="login",
                name="로그인",
                group="인증",
                order=1,
                status=ModuleStatus.RUNNING,
            )
        ],
    )


class _FakeRunQueries:
    async def get_run_detail(self, run_id: str) -> RunView:
        if run_id != "run_demo":
            raise KeyError(run_id)
        return _run()


class _NoHealing:
    async def list_events(self, **kwargs):
        return {"items": [], "systems": []}


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_dashboard.router)
    app.dependency_overrides[get_run_queries] = _FakeRunQueries
    app.dependency_overrides[get_healing_service] = _NoHealing
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


def _html(client: TestClient) -> str:
    response = client.get("/runs/run_demo")
    assert response.status_code == 200
    return response.text


def _content(client: TestClient) -> str:
    """run.html이 렌더한 영역만 반환해 공용 셸의 레거시 색 유틸리티를 제외한다."""
    html = _html(client)
    return html.split('id="run-root"', 1)[1].split('id="toast-container"', 1)[0]


def test_root_carries_the_run_shell_class(client) -> None:
    assert 'class="run' in _html(client)


def test_two_column_layout(client) -> None:
    html = _html(client)
    assert 'id="run-module-list"' in html
    assert 'id="log-console"' in html
    assert "md:grid-cols-2 xl:grid-cols-3" not in html


def test_comparison_is_a_header_chip_not_a_section(client) -> None:
    """설계 D6 — 전용 섹션을 쌓으면 넌스크롤 예산이 깨진다."""
    html = _html(client)
    assert 'id="comparison-panel"' not in html
    assert 'data-role="comparison-chip"' in html


def test_module_rows_carry_focus_inputs(client) -> None:
    """applyFocus 가 DOM 에서 읽는 값들."""
    html = _html(client)
    assert "data-module-id=" in html
    assert "data-order=" in html
    assert "data-status=" in html


def test_js_hooks_survive(client) -> None:
    html = _html(client)
    for hook in (
        'id="run-status"',
        'id="run-cancel"',
        'id="run-rerun"',
        'id="run-progress-bar"',
        'id="otp-panel"',
        'id="otp-form"',
        'id="otp-countdown"',
        'id="log-console"',
        'id="log-filter"',
        'id="log-search"',
        'id="log-copy"',
        'id="log-download"',
        'data-role="failure-analysis"',
        'data-role="module-artifacts-list"',
    ):
        assert hook in html, hook


def test_no_tailwind_color_utilities(client) -> None:
    import re

    html = _content(client)
    assert not re.findall(
        r'class="[^"]*\b(?:bg|text|border)-(?:gray|amber|red|emerald|indigo|blue|violet)-\d{2,3}',
        html,
    )
