"""상황판 라우트 계약 — 비인증·차단 스위치·프라이버시.

/wall 은 로그인 없이 열린다(설계 D1). 7일 JWT 만료로 사무실 벽에 로그인 폼이
뜨는 것을 피하기 위한 결정이며, 대가로 E2E_WALL_ENABLED 차단 스위치를 둔다(D2).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_wall
from app.api.dependencies import get_daily_summary_queries

SUMMARY: dict[str, Any] = {
    "cards": [
        {
            "key": "pass_rate",
            "label": "통과율",
            "value": 94,
            "unit": "%",
            "period": "오늘",
            "note": "34/36 모듈 정상",
            "tone": "passed",
            "href": "",
            "estimated": False,
        },
        {
            "key": "self_healed",
            "label": "스스로 복구",
            "value": 7,
            "unit": "건",
            "period": "오늘",
            "note": "이번 달 누적 21건",
            "tone": "running",
            "href": "",
            "estimated": False,
        },
        {
            "key": "pending_patches",
            "label": "내 승인 대기",
            "value": 2,
            "unit": "건",
            "period": "패치",
            "note": "검토",
            "tone": "anomaly",
            "href": "",
            "estimated": False,
        },
        {
            "key": "savings",
            "label": "이번 달 절감",
            "value": 310,
            "unit": "h",
            "period": "이번 달",
            "note": "1,240회",
            "tone": "passed",
            "href": "",
            "estimated": True,
        },
    ],
    "systems": [
        {
            "system_code": "HOM",
            "system_name": "대표홈",
            "module_total": 6,
            "pass_rate": 100,
            "counts": {
                "passed": 6,
                "anomaly": 0,
                "error": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
        },
    ],
    "totals": {
        "modules": 36,
        "passed": 34,
        "pass_rate": 94,
        "error": 0,
        "anomaly": 0,
        "running": 0,
        "not_inspected": 0,
    },
    "attention": [],
    "date_label": "2026-08-20",
    "generated_at": "2026-08-20T09:14:00+00:00",
}


class _FakeSummaryQueries:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_daily_summary(self, *, user_id, allowed_system_codes, is_admin=False):
        self.calls.append(
            {"user_id": user_id, "allowed": allowed_system_codes, "is_admin": is_admin}
        )
        return SUMMARY


def _client(*, enabled: bool = True) -> tuple[TestClient, _FakeSummaryQueries]:
    app = FastAPI()
    app.include_router(routes_wall.router)
    fake = _FakeSummaryQueries()
    app.dependency_overrides[get_daily_summary_queries] = lambda: fake
    app.dependency_overrides[routes_wall.wall_enabled] = lambda: enabled
    return TestClient(app), fake


def test_wall_renders_without_authentication():
    """인증 쿠키 없이 200 이어야 한다 — 상황판의 존재 이유다."""
    client, _ = _client()
    with client:
        response = client.get("/wall")
    assert response.status_code == 200, response.text
    assert "정상" in response.text


def test_fragment_renders_without_authentication():
    client, _ = _client()
    with client:
        response = client.get("/wall/fragment")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", ["/wall", "/wall/fragment"])
def test_disabled_switch_returns_404(path: str):
    client, _ = _client(enabled=False)
    with client:
        assert client.get(path).status_code == 404


def test_queries_are_called_company_wide_and_anonymous():
    """user_id=None(내 기여분 무의미) · allowed=None(전사) · is_admin=False(링크 없음)."""
    client, fake = _client()
    with client:
        client.get("/wall")
    assert fake.calls == [{"user_id": None, "allowed": None, "is_admin": False}]


def test_response_has_no_user_identifiers():
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    for forbidden in ("my_seconds", "email", "user_id", "user_name"):
        assert forbidden not in body, forbidden


def test_page_has_no_interactive_controls():
    """조작하지 않는 화면 — 링크·버튼·폼을 두지 않는다(설계 §3.1)."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    for tag in ("<button", "<form", "<a "):
        assert tag not in body, tag


def test_page_does_not_import_dashboard_macros():
    """_macros.html 은 FG006 allowlist 파일이다 — 알려진 위반을 끌어오지 않는다."""
    from pathlib import Path

    source = Path("app/web/templates/wall.html").read_text(encoding="utf-8")
    fragment = Path("app/web/templates/wall_fragment.html").read_text(encoding="utf-8")
    for text in (source, fragment):
        assert "_macros.html" not in text
        assert "zone_b_matrix" not in text


def test_page_does_not_extend_base_layout():
    """사이드바·모바일 네비가 없는 독립 레이아웃이다(설계 §3.8)."""
    from pathlib import Path

    source = Path("app/web/templates/wall.html").read_text(encoding="utf-8")
    assert 'extends "base.html"' not in source
