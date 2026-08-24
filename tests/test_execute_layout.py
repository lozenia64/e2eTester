"""점검 실행 레이아웃 계약 — 아코디언이 아니라 마스터-디테일인지.

`app.js` 는 폼을 `data-role` 로 찾는다. 레이아웃을 바꾸면서 그 속성을 잃으면
화면은 멀쩡해 보이는데 실행 버튼이 아무 일도 하지 않는다 — 그것을 막는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

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


class _AncestorCapture(HTMLParser):
    """렌더된 HTML의 특정 id가 어느 레이아웃 컨테이너에 속하는지 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[dict[str, str]] = []
        self.ancestors: dict[str, list[dict[str, str]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {key: value or "" for key, value in attrs}
        element = {"tag": tag, **node}
        if node.get("id") in {"runs-section", "schedules-section"}:
            self.ancestors[node["id"]] = [*self._stack, element]
        self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return None

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                del self._stack[index:]
                return


def test_root_carries_the_exec_shell_class(client) -> None:
    """넌스크롤 셸은 body:has(.exec) 로 걸린다 — 클래스가 없으면 셸이 통째로 안 붙는다."""
    assert 'class="exec' in _html(client)


def test_system_accordions_are_gone(client) -> None:
    """시스템 카드 아코디언만 제거하고, 예약 폼의 접이식은 유지한다."""
    html = _html(client)
    assert 'class="system-card' not in html
    assert "system-card--suite" not in html


def test_orphaned_system_card_css_is_gone() -> None:
    """Task 1 이 마지막 소비자를 없앴다 — 죽은 규칙을 남기면 app.css 가 계속 부풀어 있다.

    app.css 는 FG-004 의 400줄 상한을 넘겨 allowlist 에 올라 있다. 그 목록을
    비우는 것이 프로그램의 목표 중 하나이므로, 소비자가 사라진 규칙은 바로 지운다.
    """
    css = Path("app/web/frontend/styles/app.css").read_text(encoding="utf-8")
    assert "system-card" not in css


def test_schedule_form_stays_collapsible(client) -> None:
    """D7: 긴 cron 빌더는 실행 버튼의 초기 가시성을 위해 접이식으로 유지한다."""
    assert '<details class="sched' in _html(client)


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
        'name="browser_mode"',
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


def test_x_cloak_is_global_for_execute_and_dashboard_consumers(client) -> None:
    """Alpine 초기화 전 execute 패널과 dashboard 드로어가 같은 전역 리셋을 쓴다."""
    base_css = Path("app/web/frontend/styles/base.css").read_text(encoding="utf-8")
    dashboard_template = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")

    assert base_css.count("[x-cloak]") == 1
    assert "x-cloak" in _html(client)
    assert "x-cloak" in dashboard_template


def test_exec_shell_assigns_overflow_to_the_detail_owner() -> None:
    """뷰포트 셸은 잠그고, 실제 콘텐츠 오버플로는 우측 detail만 소유한다."""
    execute_css = Path("app/web/frontend/styles/execute.css").read_text(encoding="utf-8")

    shell_rule = execute_css.split("body:has(.exec) {", 1)[1].split("}", 1)[0]
    detail_rule = execute_css.split(".exec-detail {", 1)[1].split("}", 1)[0]
    assert "overflow: hidden;" in shell_rule
    assert "overflow-y: auto;" in detail_rule


def test_single_system_user_still_gets_a_layout(client) -> None:
    """allowed_system_codes 가 1개인 사용자에게도 좌우 2열이 성립해야 한다."""
    client.app.dependency_overrides[get_current_user] = lambda: _user(["hom"])
    html = client.get("/runs/execute").text
    assert 'data-exec-target="suite"' in html
    assert 'data-exec-target="hom"' in html
    assert 'data-exec-target="mhm"' not in html


def test_results_and_saved_schedules_remain_in_the_detail_scroller(client) -> None:
    """실행 뒤 표시되는 결과·저장 예약은 넌스크롤 셸 밖으로 밀려나면 안 된다."""
    parser = _AncestorCapture()
    parser.feed(_html(client))

    for section_id in ("runs-section", "schedules-section"):
        ancestors = parser.ancestors[section_id]
        assert any("exec-detail" in node.get("class", "").split() for node in ancestors)


def test_removed_system_accordions_leave_no_stale_copy(client) -> None:
    """시스템 패널은 좌측 선택으로 바뀌었으므로 카드 펼치기 안내가 남으면 안 된다."""
    html = _html(client)
    assert "카드를 펼쳐" not in html


def test_module_graph_is_the_first_thing_in_the_panel(client) -> None:
    """그래프가 인증 폼 아래 묻히면 '지배 요소' 가 아니다."""
    html = _html(client)
    panel_start = html.index('data-exec-panel="hom"')
    graph_at = html.index('data-role="module-graph-canvas"', panel_start)
    auth_at = html.index('name="auth_method"', panel_start)
    assert graph_at < auth_at, "모듈 그래프가 인증 필드보다 뒤에 있다"


def test_graph_has_its_own_wrapper(client) -> None:
    assert "exec-graph" in _html(client)
