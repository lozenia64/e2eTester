"""프리셋 관리 HTML 라우트 — 접근 제어 및 시스템 필터링."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from app.api.dependencies import get_run_service
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.registry.loader import ModuleRegistry

REGULAR_USER = User(
    user_id="user_1",
    email="user@test.local",
    name="User",
    role="user",
    hashed_password="x",
    is_active=True,
    allowed_system_codes=["hom"],
    created_at=datetime.now(UTC),
)

ADMIN = User(
    user_id="admin_1",
    email="admin@test.local",
    name="Admin",
    role="admin",
    hashed_password="x",
    is_active=True,
    created_at=datetime.now(UTC),
)


class FakeRunService:
    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry

    def list_systems(self):
        return self._registry.list_systems()


def _build_app(
    *,
    user: User | None,
    registry: ModuleRegistry,
) -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router)

    if user is None:

        async def redirect_login() -> RedirectResponse:
            return RedirectResponse(url="/login")

        app.dependency_overrides[get_current_user] = redirect_login
    else:
        app.dependency_overrides[get_current_user] = lambda: user

    app.dependency_overrides[get_run_service] = lambda: FakeRunService(registry)
    return app


def _parse_systems_payload(html: str) -> dict[str, object]:
    match = re.search(
        r'id="presets-systems-data">(\{.*?\})</script>',
        html,
        re.DOTALL,
    )
    assert match is not None, "systems_payload script tag not found"
    return json.loads(match.group(1))


@pytest.fixture
def registry() -> ModuleRegistry:
    return ModuleRegistry()


def test_presets_requires_login(registry: ModuleRegistry) -> None:
    app = _build_app(user=None, registry=registry)
    with TestClient(app) as client:
        response = client.get("/presets", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers.get("location", "").endswith("/login")


def test_presets_page_renders_for_authenticated_user(registry: ModuleRegistry) -> None:
    app = _build_app(user=REGULAR_USER, registry=registry)
    with TestClient(app) as client:
        response = client.get("/presets")
    assert response.status_code == 200
    assert "프리셋 관리" in response.text
    assert "presets-systems-data" in response.text
    assert "/static/presets.js" in response.text


def test_presets_filters_systems_by_allowed_codes(registry: ModuleRegistry) -> None:
    app = _build_app(user=REGULAR_USER, registry=registry)
    with TestClient(app) as client:
        response = client.get("/presets")
    systems = _parse_systems_payload(response.text)
    assert set(systems.keys()) == {"hom"}


def test_presets_admin_sees_all_systems(registry: ModuleRegistry) -> None:
    app = _build_app(user=ADMIN, registry=registry)
    with TestClient(app) as client:
        response = client.get("/presets")
    systems = _parse_systems_payload(response.text)
    assert len(systems) == len(registry.list_systems())
    assert "hom" in systems
    assert "mhm" in systems
