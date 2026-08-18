"""Run 상세 화면의 자동 복구 배지 렌더링 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_dashboard
from app.api.dependencies import get_run_queries
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.views.view import RunView
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import RunModule


def _run_view(*, recovered: bool) -> RunView:
    """모듈 1개만 담은 Run 상세 뷰."""
    return RunView(
        run_id="run1",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PASSED,
        status_label="정상",
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="m1",
                name="로그인",
                group="인증",
                order=1,
                status=ModuleStatus.PASSED,
                retry_count=2 if recovered else 0,
                attempt=3 if recovered else 1,
                max_attempts=3,
                recovered=recovered,
                recovery_tiers=[0, 1] if recovered else [],
                failure_signals=["TIMEOUT", "DIALOG"] if recovered else [],
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


def _build_client(run: RunView) -> TestClient:
    app = FastAPI()
    app.include_router(routes_dashboard.router)
    app.dependency_overrides[get_run_queries] = lambda: _StubRunQueries(run)
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="u1",
        email="tester@test.local",
        name="tester",
        role="admin",
        hashed_password="x",
        created_at=datetime.now(UTC),
    )
    return TestClient(app)


@pytest.fixture
def recovered_client() -> TestClient:
    with _build_client(_run_view(recovered=True)) as client:
        yield client


@pytest.fixture
def clean_client() -> TestClient:
    with _build_client(_run_view(recovered=False)) as client:
        yield client


@pytest.mark.spec("SPEC-RUN-006", "AC-004")
def test_run_detail_shows_recovered_badge(recovered_client: TestClient) -> None:
    html = recovered_client.get("/runs/run1").text

    assert "자동 복구됨" in html
    assert "badge--recovered" in html


def test_run_detail_omits_badge_for_clean_module(clean_client: TestClient) -> None:
    html = clean_client.get("/runs/run1").text

    assert "자동 복구됨" not in html
