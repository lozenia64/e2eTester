"""관리자 본인 계정 비활성화·삭제 차단 — 스스로 잠기는 것을 막는다."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_admin import router as admin_router
from app.contexts.identity.dependencies import get_user_service, require_admin
from app.contexts.identity.models import User

ADMIN = User(
    user_id="admin_1",
    email="admin@test.local",
    name="Admin",
    role="admin",
    hashed_password="x",
    is_active=True,
    created_at=datetime.now(UTC),
)


class FakeUserService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def update_user_active(self, user_id: str, is_active: bool) -> User:
        self.calls.append(("active", user_id, is_active))
        return ADMIN.model_copy(update={"user_id": user_id, "is_active": is_active})

    async def delete_user(self, user_id: str) -> None:
        self.calls.append(("delete", user_id))


@pytest.fixture
def ctx():
    service = FakeUserService()
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = lambda: ADMIN
    app.dependency_overrides[get_user_service] = lambda: service
    return TestClient(app), service


def test_본인_계정_비활성화는_거부한다(ctx):
    client, service = ctx
    res = client.patch("/api/admin/users/admin_1/active", json={"is_active": False})
    assert res.status_code == 400
    assert "본인" in res.json()["detail"]
    assert service.calls == []


def test_본인_계정_삭제는_거부한다(ctx):
    client, service = ctx
    res = client.delete("/api/admin/users/admin_1")
    assert res.status_code == 400
    assert "본인" in res.json()["detail"]
    assert service.calls == []


def test_다른_사용자_비활성화와_삭제는_허용한다(ctx):
    client, service = ctx
    assert (
        client.patch("/api/admin/users/user_2/active", json={"is_active": False}).status_code == 200
    )
    assert client.delete("/api/admin/users/user_2").status_code == 200
    assert service.calls == [("active", "user_2", False), ("delete", "user_2")]
