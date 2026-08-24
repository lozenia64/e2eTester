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
            "first_at": "2026-08-20T07:00:00+09:00",
            "last_at": "2026-08-20T07:30:00+09:00",
        },
        {
            "system_code": "FP",
            "system_name": "위촉서류",
            "module_total": 6,
            "pass_rate": 67,
            "counts": {
                "passed": 4,
                "anomaly": 2,
                "error": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
            "first_at": "2026-08-20T08:00:00+09:00",
            "last_at": "2026-08-20T08:15:00+09:00",
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
    "generated_at": "2026-08-20T09:00:00+09:00",
}


class _FakeSummaryQueries:
    def __init__(self, summary: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.summary = summary if summary is not None else SUMMARY

    async def get_daily_summary(self, *, user_id, allowed_system_codes, is_admin=False):
        self.calls.append(
            {"user_id": user_id, "allowed": allowed_system_codes, "is_admin": is_admin}
        )
        return self.summary


def _client(
    *, enabled: bool = True, summary: dict[str, Any] | None = None
) -> tuple[TestClient, _FakeSummaryQueries]:
    app = FastAPI()
    app.include_router(routes_wall.router)
    fake = _FakeSummaryQueries(summary)
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


def test_strip_renders_three_large_cards():
    """통과율은 히어로가 흡수 — 스트립은 3장(설계 §3.5)."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert body.count('class="kpi-card"') == 3
    assert body.count('data-size="lg"') == 3


def test_strip_has_no_pass_rate_card():
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert 'data-key="pass_rate"' not in body


def test_strip_cards_are_not_links():
    """조작하지 않는 화면 — href 가 있어도 링크로 렌더하지 않는다."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert "<a " not in body


def test_body_declares_htmx_polling_target():
    """갱신은 htmx 가 /wall/fragment 를 다시 받아 처리한다(설계 §3.9)."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert 'hx-get="/wall/fragment"' in body
    assert 'hx-swap="morph:outerHTML"' in body


def test_fragment_is_self_replacing():
    """프래그먼트 루트가 교체 대상과 같은 요소여야 outerHTML 스왑이 성립한다."""
    client, _ = _client()
    with client:
        body = client.get("/wall/fragment").text
    assert 'id="wall-body"' in body


def test_timeline_renders_a_lane_per_inspected_system():
    client, _ = _client()
    html = client.get("/wall").text
    assert 'class="wall-timeline"' in html
    assert html.count('class="wall-lane"') == 2  # SUMMARY 의 시스템 2개


def test_timeline_lanes_have_unique_stable_system_ids():
    """시스템 삽입·재정렬에도 morph가 같은 레인을 보존할 식별자가 필요하다."""
    client, _ = _client()
    html = client.get("/wall").text

    assert 'id="wall-lane-HOM"' in html
    assert 'id="wall-lane-FP"' in html
    assert html.count('id="wall-lane-') == 2


def test_timeline_lane_carries_geometry_from_server():
    """좌표 계산은 서버가 한다 — 클라이언트 JS 가 없어도 그려진다(D2)."""
    client, _ = _client()
    html = client.get("/wall").text
    assert "--lane-left:" in html
    assert "--lane-width:" in html
    assert 'class="wall-lane__span"\n                data-tone="passed"' in html
    assert 'class="wall-lane__span"\n                data-tone="anomaly"' in html


def test_timeline_marks_now():
    client, _ = _client()
    html = client.get("/wall").text
    assert 'class="wall-timeline__now"' in html


def test_timeline_shows_waiting_message_when_nothing_inspected():
    empty = {**SUMMARY, "systems": []}
    client, _ = _client(summary=empty)
    html = client.get("/wall").text
    assert "오늘 점검 대기 중" in html
    assert 'class="wall-lane"' not in html


def test_matrix_markup_is_gone():
    """매트릭스는 타임라인의 y축으로 흡수됐다(D1)."""
    client, _ = _client()
    html = client.get("/wall").text
    assert 'class="wall-matrix"' not in html
    assert 'class="wall-sys"' not in html


def test_body_declares_morph_extension_outside_the_swap_target():
    """확장 선언이 교체 대상 안에 있으면 첫 교체 후 사라진다(설계 §4.4)."""
    client, _ = _client()
    html = client.get("/wall").text
    body_open = html.index("<body")
    wall_body = html.index('id="wall-body"')
    assert 'hx-ext="morph"' in html
    assert html.index('hx-ext="morph"') < wall_body
    assert html.index('hx-ext="morph"') > body_open


def test_fragment_uses_morph_swap():
    client, _ = _client()
    html = client.get("/wall/fragment").text
    assert 'hx-swap="morph:outerHTML"' in html
    assert 'hx-swap="outerHTML"' not in html
