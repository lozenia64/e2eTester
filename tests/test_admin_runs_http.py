"""관리자 Run 이력 HTTP API — FastAPI 라우트 계약."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_registry,
    get_run_queries,
    get_run_service,
    get_schedule_repository,
    get_suite_summary_query,
)
from app.api.routes_admin import router as admin_router
from app.contexts.identity.dependencies import get_user_service, require_admin
from app.contexts.identity.models import User
from app.contexts.run.views.actor import ActorContext

ADMIN = User(
    user_id="admin_1",
    email="admin@test.local",
    name="Admin",
    role="admin",
    hashed_password="x",
    is_active=True,
    created_at=datetime.now(UTC),
)


class FakeRunQueries:
    def __init__(self) -> None:
        self.last_page_kwargs: dict[str, Any] | None = None

    async def list_run_summaries_page(self, **kwargs: Any) -> dict[str, Any]:
        self.last_page_kwargs = kwargs
        return {
            "items": [
                {
                    "run_id": "run_1",
                    "status": "PASSED",
                    "status_label": "정상",
                    "system_code": "hom",
                    "system_name": "HOM",
                }
            ],
            "total": 1,
            "offset": kwargs.get("offset", 0),
            "limit": kwargs.get("limit", 50),
        }

    async def get_admin_run_history_board(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "timezone": "Asia/Seoul",
            "today_start": datetime.now(UTC).isoformat(),
            "system_map": {
                "period": {"from": "2026-09-30T15:00:00+00:00", "to": "2026-10-14T12:00:00+00:00"},
                "systems": [
                    {"system_code": "hom", "system_name": "대표홈페이지", "runs": 3, "anomaly": 1}
                ],
                "top_runs": "hom",
                "top_anomaly": "hom",
            },
        }

    async def get_admin_run_history_heatmap(
        self, *, systems: list[tuple[str, str]]
    ) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "users": ["Alice"],
            "systems": [name for _code, name in systems],
            "system_codes": [code for code, _name in systems],
            "matrix": [[0] for _ in systems],
            "legend": [],
        }


class FakeRegistry:
    def list_systems(self) -> list[object]:
        return [type("System", (), {"system_code": "hom", "name": "HOM"})()]


class FakeRunService:
    async def delete_run(self, run_id: str) -> None:
        if run_id != "run_1":
            raise KeyError(run_id)


@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeRunQueries]:
    async def fake_actor_context(*_args: object, **_kwargs: object) -> ActorContext:
        return ActorContext(users_by_id={}, suites_by_id={}, schedules_by_id={})

    monkeypatch.setattr("app.api.routes_admin.load_actor_context", fake_actor_context)

    app = FastAPI()
    app.include_router(admin_router)
    fake_queries = FakeRunQueries()

    app.dependency_overrides[require_admin] = lambda: ADMIN
    app.dependency_overrides[get_run_queries] = lambda: fake_queries
    app.dependency_overrides[get_run_service] = lambda: FakeRunService()
    app.dependency_overrides[get_user_service] = lambda: object()
    app.dependency_overrides[get_suite_summary_query] = lambda: object()
    app.dependency_overrides[get_schedule_repository] = lambda: object()
    app.dependency_overrides[get_registry] = lambda: FakeRegistry()

    with TestClient(app) as client:
        yield client, fake_queries

    app.dependency_overrides.clear()


def test_admin_runs_board_returns_system_map(
    admin_client: tuple[TestClient, FakeRunQueries],
) -> None:
    client, _ = admin_client
    response = client.get("/api/admin/runs/board")
    assert response.status_code == 200
    body = response.json()
    assert body["system_map"]["systems"] == [
        {"system_code": "hom", "system_name": "대표홈페이지", "runs": 3, "anomaly": 1}
    ]
    assert "today_start" in body
    assert "trend_7d" not in body


def test_admin_list_runs_include_total_wraps_page(
    admin_client: tuple[TestClient, FakeRunQueries],
) -> None:
    client, fake = admin_client
    response = client.get("/api/admin/runs", params={"include_total": "true", "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["run_id"] == "run_1"
    assert fake.last_page_kwargs is not None
    assert fake.last_page_kwargs["limit"] == 10


def test_admin_list_runs_passes_run_id_prefix(
    admin_client: tuple[TestClient, FakeRunQueries],
) -> None:
    client, fake = admin_client
    response = client.get(
        "/api/admin/runs",
        params={"include_total": "true", "run_id": "hom_2026"},
    )
    assert response.status_code == 200
    assert fake.last_page_kwargs is not None
    assert fake.last_page_kwargs["run_id_query"] == "hom_2026"


def test_admin_list_runs_passes_multi_system_and_user_name(
    admin_client: tuple[TestClient, FakeRunQueries],
) -> None:
    client, fake = admin_client
    response = client.get(
        "/api/admin/runs",
        params=[
            ("include_total", "true"),
            ("system_code", "hom"),
            ("system_code", "mhm"),
            ("user_name", "테스터"),
            ("to", "2026-07-14T00:00:00Z"),
        ],
    )
    assert response.status_code == 200
    assert fake.last_page_kwargs is not None
    assert fake.last_page_kwargs["system_codes"] == frozenset({"hom", "mhm"})
    assert fake.last_page_kwargs["user_name_query"] == "테스터"
    assert fake.last_page_kwargs["requested_before"] is not None


def test_admin_list_runs_rejects_invalid_triggered_by(
    admin_client: tuple[TestClient, FakeRunQueries],
) -> None:
    client, _ = admin_client
    response = client.get("/api/admin/runs", params={"triggered_by": "invalid"})
    assert response.status_code == 400


def test_admin_delete_run_ok(admin_client: tuple[TestClient, FakeRunQueries]) -> None:
    client, _ = admin_client
    response = client.delete("/api/admin/runs/run_1")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_admin_delete_run_not_found(admin_client: tuple[TestClient, FakeRunQueries]) -> None:
    client, _ = admin_client
    response = client.delete("/api/admin/runs/missing")
    assert response.status_code == 404


def test_admin_export_runs_csv(admin_client: tuple[TestClient, FakeRunQueries]) -> None:
    client, _ = admin_client
    response = client.get("/api/admin/runs/export.csv", params={"status": "PASSED"})
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "admin_runs_" in disposition
    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf")
    body = raw.decode("utf-8-sig")
    assert "run_id" in body.splitlines()[0]
    assert "schedule_id" in body.splitlines()[0]
    assert "suite_id" in body.splitlines()[0]
    assert "run_1" in body


def test_admin_export_runs_csv_rejects_invalid_triggered_by(
    admin_client: tuple[TestClient, FakeRunQueries],
) -> None:
    client, _ = admin_client
    response = client.get("/api/admin/runs/export.csv", params={"triggered_by": "invalid"})
    assert response.status_code == 400


def test_admin_runs_heatmap_ok(admin_client: tuple[TestClient, FakeRunQueries]) -> None:
    client, _ = admin_client
    response = client.get("/api/admin/runs/heatmap")
    assert response.status_code == 200
    body = response.json()
    assert body["users"] == ["Alice"]


def test_admin_routes_require_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    async def deny_admin() -> User:
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    async def fake_actor_context(*_args: object, **_kwargs: object) -> ActorContext:
        return ActorContext(users_by_id={}, suites_by_id={}, schedules_by_id={})

    monkeypatch.setattr("app.api.routes_admin.load_actor_context", fake_actor_context)

    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = deny_admin
    app.dependency_overrides[get_run_queries] = lambda: FakeRunQueries()
    app.dependency_overrides[get_user_service] = lambda: object()
    app.dependency_overrides[get_suite_summary_query] = lambda: object()
    app.dependency_overrides[get_schedule_repository] = lambda: object()
    app.dependency_overrides[get_registry] = lambda: FakeRegistry()

    with TestClient(app) as client:
        response = client.get("/api/admin/runs/board")
        assert response.status_code == 403

    app.dependency_overrides.clear()
