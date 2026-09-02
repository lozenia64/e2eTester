"""사용자용 커버리지·드릴다운 라우트 — 권한 축과 노출 필드 계약(설계 D2·D8·D9)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_admin_dashboard_queries, get_run_queries
from app.api.routes_runs import router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User


class _StubAdminQueries:
    def __init__(self) -> None:
        self.seen: frozenset[str] | None = None

    async def get_coverage_dashboard(self, *, system_codes=None):
        self.seen = system_codes
        return {"systems": [], "columns": [], "totals": {}, "window": {}}


class _StubRunQueries:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def list_run_summaries_page(self, **kwargs):
        self.kwargs = kwargs
        return {
            "items": [
                {
                    "run_id": "run_1",
                    "system_code": "hom",
                    "status": "passed",
                    "status_label": "정상",
                    "requested_at": datetime(2026, 9, 1, 13, 0, tzinfo=UTC).isoformat(),
                    "module_total": 3,
                    "module_passed": 3,
                    "suite_id": None,
                    "created_by_user_id": "u_other",
                    "created_by_user_name": "다른 사용자",
                }
            ],
            "total": 1,
        }


def _user() -> User:
    return User(
        user_id="u_1",
        name="사용자",
        email="user@example.com",
        role="user",
        hashed_password="x",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        allowed_system_codes=["hom"],
    )


def _client(admin_queries, run_queries) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_admin_dashboard_queries] = lambda: admin_queries
    app.dependency_overrides[get_run_queries] = lambda: run_queries
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_coverage_scopes_to_allowed_systems():
    admin_queries = _StubAdminQueries()
    async with _client(admin_queries, _StubRunQueries()) as client:
        response = await client.get("/api/runs/coverage")

    assert response.status_code == 200
    assert admin_queries.seen == frozenset({"hom"})


@pytest.mark.asyncio
async def test_day_rejects_system_outside_permission():
    async with _client(_StubAdminQueries(), _StubRunQueries()) as client:
        response = await client.get(
            "/api/runs/day", params={"system_code": "mhm", "day": "2026-09-01"}
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_day_hides_actor_fields():
    async with _client(_StubAdminQueries(), _StubRunQueries()) as client:
        response = await client.get(
            "/api/runs/day", params={"system_code": "hom", "day": "2026-09-01"}
        )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["run_id"] == "run_1"
    assert "created_by_user_name" not in item
    assert "created_by_user_id" not in item


@pytest.mark.asyncio
async def test_day_filters_by_system_not_requester():
    run_queries = _StubRunQueries()
    async with _client(_StubAdminQueries(), run_queries) as client:
        await client.get("/api/runs/day", params={"system_code": "hom", "day": "2026-09-01"})

    assert run_queries.kwargs["system_code"] == "hom"
    assert run_queries.kwargs.get("user_id") is None
