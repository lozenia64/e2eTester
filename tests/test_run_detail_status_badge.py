"""Run 상세 상태 배지의 서버 렌더 계약 — 버그 3건 회귀 가드.

이전에는 run.html 이 자체 status_pill 맵을 들고 있어
(1) 배지 텍스트가 영문 enum 값, (2) ANOMALY/ERROR 가 회색,
(3) 레거시 FAILED 가 빨강이었다. 완료된 Run 은 WS 갱신이 오지 않아 끝까지 깨졌다.
"""

from __future__ import annotations

import re
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
from app.core.status_labels import module_status_badge_tone, module_status_label

BADGE_RE = re.compile(
    r'<span class="status-badge"[^>]*data-tone="(?P<tone>[a-z_]+)"[^>]*>(?P<text>[^<]*)</span>'
)


def _run_view(module_status: ModuleStatus, run_status: RunStatus = RunStatus.PASSED) -> RunView:
    return RunView(
        run_id="run1",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=run_status,
        status_label="정상",
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="m1",
                name="로그인",
                group="인증",
                order=1,
                status=module_status,
            )
        ],
    )


class _StubRunQueries:
    def __init__(self, run: RunView) -> None:
        self._run = run

    async def get_run_detail(self, run_id: str) -> RunView:
        if run_id != self._run.run_id:
            raise KeyError(run_id)
        return self._run


def _html(run: RunView) -> str:
    app = FastAPI()
    app.include_router(routes_dashboard.router)

    class _NoHealing:
        async def list_events(self, **kwargs):
            return {"items": [], "systems": []}

    app.dependency_overrides[get_run_queries] = lambda: _StubRunQueries(run)
    app.dependency_overrides[get_healing_service] = lambda: _NoHealing()
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="u1",
        email="tester@test.local",
        name="tester",
        role="admin",
        hashed_password="x",
        created_at=datetime.now(UTC),
    )
    with TestClient(app) as client:
        response = client.get("/runs/run1")
        assert response.status_code == 200, response.text
        return response.text


def test_status_pill_map_is_gone() -> None:
    """템플릿이 자체 색 맵을 다시 들면 이 테스트가 막는다."""
    source = __import__("pathlib").Path("app/web/templates/run.html").read_text(encoding="utf-8")
    assert "status_pill" not in source


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_module_badge_tone_and_label_match_ssot(status: ModuleStatus) -> None:
    html = _html(_run_view(status))
    badges = BADGE_RE.findall(html)
    tones = {tone for tone, _ in badges}
    texts = {text.strip() for _, text in badges}
    assert module_status_badge_tone(status) in tones, (status, tones)
    assert module_status_label(status) in texts, (status, texts)


def test_anomaly_module_is_not_rendered_neutral() -> None:
    """버그 2 회귀 가드."""
    html = _html(_run_view(ModuleStatus.ANOMALY))
    assert 'data-tone="anomaly"' in html


def test_error_module_is_not_rendered_neutral() -> None:
    """버그 2 회귀 가드."""
    html = _html(_run_view(ModuleStatus.ERROR))
    assert 'data-tone="error"' in html


def test_legacy_failed_module_renders_as_anomaly() -> None:
    """버그 3 회귀 가드."""
    html = _html(_run_view(ModuleStatus.FAILED))
    assert 'data-tone="anomaly"' in html


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_no_english_enum_value_in_badge_text(status: ModuleStatus) -> None:
    """버그 1 회귀 가드 — 클래스 값은 정당하므로 배지 텍스트만 검사한다."""
    html = _html(_run_view(status))
    texts = {text.strip() for _, text in BADGE_RE.findall(html)}
    assert status.value not in texts, (status, texts)


def test_run_badge_carries_raw_status_for_action_buttons() -> None:
    """app.js 가 버튼 표시를 판정하는 근거. 없으면 실행 중 Run 의 취소 버튼이 사라진다."""
    html = _html(_run_view(ModuleStatus.PASSED, run_status=RunStatus.RUNNING))
    assert 'id="run-status"' in html
    assert 'data-status="RUNNING"' in html


def test_module_badge_keeps_the_js_hook() -> None:
    """app.js:1913 이 이 속성으로 모듈 배지를 찾는다."""
    html = _html(_run_view(ModuleStatus.PASSED))
    assert 'data-role="module-status"' in html
