"""점검 실행 레이아웃 계약 — 아코디언이 아니라 마스터-디테일인지.

`app.js` 는 폼을 `data-role` 로 찾는다. 레이아웃을 바꾸면서 그 속성을 잃으면
화면은 멀쩡해 보이는데 실행 버튼이 아무 일도 하지 않는다 — 그것을 막는다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.api.dependencies import get_run_service
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.registry.loader import ModuleRegistry
from tests.test_dashboard_fragments_http import FakeRunService


GEN_AT = datetime(2026, 8, 25, 5, 0, tzinfo=UTC)


def _user(codes: list[str]) -> User:
    """User 는 hashed_password·created_at 이 필수다(기본값 없음) — 빠뜨리면 ValidationError."""
    return User(
        user_id="exec_user",
        email="operator@test.local",
        name="점검자",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=codes,
        created_at=GEN_AT,
    )


@pytest.fixture()
def registry() -> ModuleRegistry:
    return ModuleRegistry()


@pytest.fixture()
def client(registry: ModuleRegistry) -> TestClient:
    codes = [s.system_code for s in registry.list_systems()]
    app = FastAPI()
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    app.dependency_overrides[get_current_user] = lambda: _user(codes)
    app.dependency_overrides[get_run_service] = lambda: FakeRunService(registry)
    return TestClient(app)


def _html(client: TestClient) -> str:
    response = client.get("/runs/execute")
    assert response.status_code == 200
    return response.text


def test_root_carries_the_exec_shell_class(client) -> None:
    """넌스크롤 셸은 body:has(.exec) 로 걸린다 — 클래스가 없으면 셸이 통째로 안 붙는다."""
    assert 'class="exec' in _html(client)


def test_accordion_is_gone(client) -> None:
    """<details> 가 남아 있으면 '펼치기 전에는 안 보이는' 문제가 그대로다."""
    html = _html(client)
    assert "<details" not in html
    assert "system-card--suite" not in html


def test_every_system_has_a_left_target_and_a_right_panel(client) -> None:
    html = _html(client)
    for key in ("suite", "hom", "mhm", "fp", "hrp", "hwtc", "chbot"):
        assert f'data-exec-target="{key}"' in html, key
        assert f'data-exec-panel="{key}"' in html, key


def test_suite_is_selected_first(client) -> None:
    """전체 순차 점검이 기본 선택 — 데모에서 가장 먼저 보여줄 화면이다."""
    assert "selected: 'suite'" in _html(client)


def test_form_contract_survives(client) -> None:
    """app.js 가 찾는 훅이 그대로여야 한다(Cycle 1b 이전까지 레거시가 계속 붙는다)."""
    html = _html(client)
    for hook in (
        'id="suite-form"',
        'id="suite-start-button"',
        'id="suite-section"',
        'class="system-form',
        'data-role="system-definition"',
        'data-role="preset-panel"',
        'data-role="module-selector"',
        'data-role="module-graph-canvas"',
        'data-role="module-graph-edges"',
        'data-role="module-graph-grid"',
        'data-role="suite-system-checkbox"',
        'data-role="suite-preset-list"',
    ):
        assert hook in html, hook


def test_single_system_user_still_gets_a_layout(client) -> None:
    """allowed_system_codes 가 1개인 사용자에게도 좌우 2열이 성립해야 한다."""
    client.app.dependency_overrides[get_current_user] = lambda: _user(["hom"])
    html = client.get("/runs/execute").text
    assert 'data-exec-target="suite"' in html
    assert 'data-exec-target="hom"' in html
    assert 'data-exec-target="mhm"' not in html
