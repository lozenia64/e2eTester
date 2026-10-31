"""사용자별 텔레그램 연결 저장과 계정 화면 HTTP 흐름 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_telegram_bot
from app.api.routes_identity import router
from app.contexts.identity.dependencies import get_current_user, get_user_service
from app.contexts.identity.models import User, UserPublic
from app.contexts.identity.service import UserService
from app.contexts.scheduling.telegram_bot import _LINK_TTL_S as LINK_TTL_S
from app.contexts.scheduling.telegram_bot import TelegramApiError, TelegramLink


class _Repo:
    def __init__(self, users: list[User]) -> None:
        self.items = {user.user_id: user for user in users}

    async def get(self, user_id: str) -> User:
        return self.items[user_id]

    async def save(self, user: User) -> User:
        self.items[user.user_id] = user
        return user

    async def list(self) -> list[User]:
        return list(self.items.values())

    async def delete(self, user_id: str) -> None:
        del self.items[user_id]


def _user(user_id: str, *, telegram_user_id: int | None = None) -> User:
    return User(
        user_id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        role="user",
        hashed_password="hash",
        created_at=datetime.now(UTC),
        telegram_user_id=telegram_user_id,
    )


async def test_link_saves_telegram_id_per_user():
    repo = _Repo([_user("a"), _user("b")])
    service = UserService(repo)
    await service.link_telegram("a", 111)
    await service.link_telegram("b", 222)
    assert (await service.get_user_by_telegram_id(111)).user_id == "a"
    assert (await service.get_user_by_telegram_id(222)).user_id == "b"


async def test_linking_moves_telegram_account_from_previous_user():
    repo = _Repo([_user("a", telegram_user_id=111), _user("b")])
    service = UserService(repo)
    await service.link_telegram("b", 111)
    assert repo.items["a"].telegram_user_id is None
    assert (await service.get_user_by_telegram_id(111)).user_id == "b"


async def test_unlink_clears_telegram_id():
    repo = _Repo([_user("a", telegram_user_id=111)])
    service = UserService(repo)
    await service.unlink_telegram("a")
    assert await service.get_user_by_telegram_id(111) is None


@pytest.mark.parametrize("operation", ["deactivate", "delete"])
async def test_link_cannot_overwrite_concurrent_admin_change(operation):
    entered, release = asyncio.Event(), asyncio.Event()

    class PausedRepo(_Repo):
        async def list(self):
            entered.set()
            await release.wait()
            return await super().list()

    repo = PausedRepo([_user("a")])
    service = UserService(repo)
    linking = asyncio.create_task(service.link_telegram("a", 111))
    await entered.wait()
    change = asyncio.create_task(
        service.update_user_active("a", False)
        if operation == "deactivate"
        else service.delete_user("a")
    )
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(linking, change)
    if operation == "deactivate":
        assert repo.items["a"].is_active is False
    else:
        assert "a" not in repo.items


async def test_unknown_telegram_id_finds_nobody():
    assert await UserService(_Repo([_user("a")])).get_user_by_telegram_id(111) is None


def test_public_user_does_not_expose_telegram_id():
    public = UserPublic(**_user("a", telegram_user_id=111).model_dump())
    assert "111" not in public.model_dump_json()


class _Bot:
    def __init__(self, *, error: bool = False) -> None:
        self.error = error
        self.issued: list[str] = []

    async def issue_link(self, user_id: str) -> TelegramLink:
        if self.error:
            raise TelegramApiError("getMe: ConnectError")
        self.issued.append(user_id)
        return TelegramLink(
            "AB12CD34", "e2e_check_bot", "https://t.me/e2e_check_bot?start=AB12CD34"
        )

    async def unlink_user(self, user_id: str) -> None:
        await self.users.unlink_telegram(user_id)


@pytest.fixture
def web():
    def build(user: User, bot):
        repo = _Repo([user])
        if bot is not None:
            bot.users = UserService(repo)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: repo.items[user.user_id]
        app.dependency_overrides[get_user_service] = lambda: UserService(repo)
        app.dependency_overrides[get_telegram_bot] = lambda: bot
        return SimpleNamespace(client=TestClient(app), repo=repo)

    return build


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/account/telegram"),
        ("post", "/account/telegram/link"),
        ("post", "/account/telegram/unlink"),
    ],
)
def test_anonymous_request_goes_to_login(web, method, path):
    site = web(_user("a", telegram_user_id=111), _Bot())
    del site.client.app.dependency_overrides[get_current_user]
    response = getattr(site.client, method)(path, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"
    assert site.repo.items["a"].telegram_user_id == 111


def test_page_explains_when_bot_is_off(web):
    page = web(_user("a"), None).client.get("/account/telegram")
    assert page.status_code == 200
    assert "설정되지 않았습니다" in page.text


def test_page_offers_link_when_unlinked(web):
    page = web(_user("a"), _Bot()).client.get("/account/telegram")
    assert 'action="/account/telegram/link"' in page.text


def test_page_shows_linked_state_without_id(web):
    page = web(_user("a", telegram_user_id=98765), _Bot()).client.get("/account/telegram")
    assert 'action="/account/telegram/unlink"' in page.text
    assert "98765" not in page.text


def test_issuing_link_shows_code_for_logged_in_user(web):
    bot = _Bot()
    page = web(_user("a"), bot).client.post("/account/telegram/link")
    assert page.status_code == 200
    assert "AB12CD34" in page.text
    assert "https://t.me/e2e_check_bot?start=AB12CD34" in page.text
    assert f"{LINK_TTL_S // 60}분" in page.text
    assert bot.issued == ["a"]


def test_issue_failure_shows_notice(web):
    page = web(_user("a"), _Bot(error=True)).client.post("/account/telegram/link")
    assert page.status_code == 200
    assert "코드를 만들지 못했습니다" in page.text


def test_issue_with_bot_off_shows_page(web):
    page = web(_user("a"), None).client.post("/account/telegram/link")
    assert page.status_code == 200
    assert "설정되지 않았습니다" in page.text


def test_unlink_clears_only_current_user(web):
    site = web(_user("a", telegram_user_id=111), _Bot())
    response = site.client.post("/account/telegram/unlink", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/account/telegram"
    assert site.repo.items["a"].telegram_user_id is None
