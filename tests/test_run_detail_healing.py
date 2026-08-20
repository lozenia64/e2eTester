"""Run 상세의 치유 이력 인라인 표시.

recovered 배지는 "재시도 후 통과"만 알린다. 무엇이 깨져서 무엇으로 고쳐졌는지는
Run 상세에 전혀 없었고 /self-healing 으로 따로 가야 보였다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.contexts.healing.models import HealingAction, HealingEvent
from app.contexts.healing.service import HealingService


def _event(*, run_id: str, module_id: str, action: HealingAction, event_id: str) -> HealingEvent:
    return HealingEvent(
        event_id=event_id,
        run_id=run_id,
        module_id=module_id,
        system_code="HOM",
        module_name="로그인",
        broken_selector="#login-btn",
        healed_selector="[data-testid=login]",
        action=action,
        retry_succeeded=action is HealingAction.AUTO_HEALED,
        created_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )


class _StubEventStore:
    def __init__(self, events: list[HealingEvent]) -> None:
        self._events = events

    async def list(self, limit: int = 500) -> list[HealingEvent]:
        return self._events[:limit]


class _StubPatchStore:
    async def list(self) -> list:
        return []


class _StubPolicyStore:
    async def get(self, system_code: str):
        return None

    async def list(self):
        return []


class _StubRegistry:
    def list_systems(self):
        return [SimpleNamespace(system_code="HOM", name="대표홈", display_order=1)]

    def get_system(self, system_code: str):
        return SimpleNamespace(system_code=system_code, name="대표홈", display_order=1)


@pytest.fixture()
def healing_service_factory(tmp_path):
    def _make(events: list[HealingEvent]) -> HealingService:
        return HealingService(
            _StubEventStore(events),
            _StubPolicyStore(),
            _StubPatchStore(),
            _StubRegistry(),
            repo_root=tmp_path,
        )

    return _make


@pytest.mark.asyncio
async def test_list_events_filters_by_run_id(healing_service_factory) -> None:
    """다른 Run 의 이벤트가 섞이지 않는다."""
    service = healing_service_factory(
        [
            _event(run_id="run1", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e1"),
            _event(run_id="run2", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e2"),
        ]
    )
    result = await service.list_events(run_id="run1")
    assert [item["event_id"] for item in result["items"]] == ["e1"]


@pytest.mark.asyncio
async def test_list_events_without_run_id_returns_all(healing_service_factory) -> None:
    """기존 호출자는 동작이 바뀌지 않는다."""
    service = healing_service_factory(
        [
            _event(run_id="run1", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e1"),
            _event(run_id="run2", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e2"),
        ]
    )
    result = await service.list_events()
    assert {item["event_id"] for item in result["items"]} == {"e1", "e2"}


def _html_with_heals(items: list[dict]) -> str:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import routes_dashboard
    from app.api.dependencies import get_healing_service, get_run_queries
    from app.contexts.identity.dependencies import get_current_user
    from app.contexts.identity.models import User
    from app.contexts.run.views.view import RunView
    from app.core.enums import ModuleStatus, RunStatus
    from app.core.run_models import RunModule

    run = RunView(
        run_id="run1",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PASSED,
        status_label="정상",
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="m1", name="로그인", group="인증", order=1, status=ModuleStatus.PASSED
            )
        ],
    )

    class _Queries:
        async def get_run_detail(self, run_id: str) -> RunView:
            return run

    class _Healing:
        async def list_events(self, **kwargs):
            return {"items": items, "systems": []}

    app = FastAPI()
    app.include_router(routes_dashboard.router)
    app.dependency_overrides[get_run_queries] = lambda: _Queries()
    app.dependency_overrides[get_healing_service] = lambda: _Healing()
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="u1",
        email="t@t.local",
        name="t",
        role="admin",
        hashed_password="x",
        created_at=datetime.now(UTC),
    )
    with TestClient(app) as client:
        response = client.get("/runs/run1")
        assert response.status_code == 200, response.text
        return response.text


def _item(action: str) -> dict:
    return {
        "event_id": "e1",
        "run_id": "run1",
        "module_id": "m1",
        "system_code": "HOM",
        "module_name": "로그인",
        "broken_selector": "#login-btn",
        "healed_selector": "[data-testid=login]",
        "action": action,
        "heal_count": 1,
    }


def test_auto_healed_event_is_shown() -> None:
    html = _html_with_heals([_item("AUTO_HEALED")])
    assert "자동 복구" in html
    assert "#login-btn" in html
    assert "/self-healing#patches" in html


def test_suggested_event_is_labelled_as_suggestion() -> None:
    html = _html_with_heals([_item("SUGGESTED")])
    assert "제안됨" in html


def test_no_candidate_event_is_not_shown() -> None:
    """복구되지 않은 시도는 화면에 올리지 않는다(설계 §3.5)."""
    html = _html_with_heals([_item("NO_CANDIDATE")])
    assert "#login-btn" not in html


def test_module_without_heals_shows_nothing() -> None:
    html = _html_with_heals([])
    assert "셀렉터" not in html
