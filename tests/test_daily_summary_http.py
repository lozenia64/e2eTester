"""KPI 요약 라우트 계약 테스트 — 권한·프라이버시.

로그인 플로우 대신 dependency_overrides 로 사용자를 주입한다
(tests/test_dashboard_fragments_http.py 와 같은 방식).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_daily_queries, get_daily_summary_queries
from app.api.routes_daily import router as daily_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User

GEN_AT = datetime(2026, 8, 15, 5, 0, tzinfo=UTC)

SUMMARY = {
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
            "value": 310,
            "unit": "h",
            "period": "이번 달",
            "note": "1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)",
            "tone": "passed",
            "href": "/admin/modules",
            "estimated": True,
        },
    ],
    "totals": {
        "modules": 36,
        "passed": 34,
        "pass_rate": 94,
        "anomaly": 2,
        "error": 0,
        "running": 0,
        "not_inspected": 0,
    },
    "date_label": "2026-08-19",
    "generated_at": "2026-08-19T00:14:00+00:00",
    "attention": [],
}


class FakeDailySummaryQueries:
    def __init__(self) -> None:
        self.seen: list[tuple[str | None, list[str] | None]] = []

    async def get_daily_summary(self, *, user_id, allowed_system_codes, is_admin: bool = False):
        self.seen.append((user_id, allowed_system_codes))
        return SUMMARY


def _member() -> User:
    """비관리자(일반 담당자) 사용자."""
    return User(
        user_id="user-a",
        email="a@example.com",
        name="가",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=["HOM"],
        created_at=GEN_AT,
    )


@pytest.fixture()
def client_and_fake():
    app = FastAPI()
    app.include_router(daily_router)
    fake = FakeDailySummaryQueries()
    app.dependency_overrides[get_daily_summary_queries] = lambda: fake
    app.dependency_overrides[get_daily_queries] = lambda: None
    app.dependency_overrides[get_current_user] = _member
    with TestClient(app) as client:
        yield client, fake


def test_summary_returns_four_cards(client_and_fake):
    client, _ = client_and_fake
    response = client.get("/api/dashboard/daily/summary")
    assert response.status_code == 200
    assert [c["key"] for c in response.json()["cards"]] == [
        "pass_rate",
        "self_healed",
        "pending_patches",
        "savings",
    ]


def test_non_admin_can_read_savings(client_and_fake):
    """경영진·담당자가 관리자 권한 없이 절감 지표를 볼 수 있어야 한다."""
    client, _ = client_and_fake
    response = client.get("/api/dashboard/daily/summary")
    savings = next(c for c in response.json()["cards"] if c["key"] == "savings")
    assert savings["value"] == 310
    assert savings["estimated"] is True
    assert savings["note"]


def test_summary_response_has_no_user_identifiers(client_and_fake):
    """프라이버시 계약 — 사용자별 분해는 관리자 전용에만."""
    client, _ = client_and_fake
    body = client.get("/api/dashboard/daily/summary").text
    for forbidden in ("email", "user_id", "user_name", "by_user"):
        assert forbidden not in body, forbidden


def test_non_admin_is_scoped_to_allowed_systems(client_and_fake):
    """관리자가 아니면 allowed_system_codes 로 스코프가 걸려야 한다."""
    client, fake = client_and_fake
    client.get("/api/dashboard/daily/summary")
    user_id, allowed = fake.seen[-1]
    assert user_id == "user-a"
    assert allowed == ["HOM"]


def test_kpi_fragment_uses_summary(client_and_fake):
    """kpi 프래그먼트가 요약 핸들러를 쓴다(matrix 는 기존 핸들러 유지)."""
    client, fake = client_and_fake
    response = client.get("/api/dashboard/daily/fragments/kpi")
    assert response.status_code == 200
    assert fake.seen, "요약 핸들러가 호출되지 않았다"
