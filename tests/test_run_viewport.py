"""런 상세 2열 넌스크롤 좌표 계약 — Playwright 회귀(설계 §3.1·D2·D7)."""

from __future__ import annotations

import socket
import threading
import time
from datetime import UTC, datetime

import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import get_healing_service, get_run_queries
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.views.view import RunView
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import FailureAnalysis, RunModule

pytest.importorskip("playwright")

GEN_AT = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
RUN_ID_FAILED = "run_viewport_failed"
VIEWPORTS = [(1366, 768), (1920, 1080), (2560, 1440)]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(host: str, port: int, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"테스트 서버가 {timeout}s 내에 준비되지 않았습니다: {host}:{port}")


def _failure_analysis() -> FailureAnalysis:
    return FailureAnalysis(
        category="셀렉터 오류",
        probable_cause="로그인 버튼의 식별자가 변경되었습니다.",
        retryable=False,
        user_summary="로그인 버튼을 찾지 못했습니다.",
        developer_details="[data-testid=login-submit] 셀렉터가 응답하지 않았습니다.",
        recommended_action="로그인 버튼의 셀렉터를 확인하세요.",
    )


def _failed_run() -> RunView:
    modules = [
        RunModule(
            module_id=f"module_{order}",
            name=f"대표홈 점검 모듈 {order} · 로그인과 고객 정보 표시 상태를 확인합니다",
            group="회귀",
            order=order,
            status=ModuleStatus.PASSED if order != 4 else ModuleStatus.ERROR,
            duration_ms=1_000 * order,
            message="점검을 마쳤습니다." if order != 4 else "로그인 버튼을 찾지 못했습니다.",
            failure_analysis=_failure_analysis() if order == 4 else None,
            logs=[f"모듈 {order} 로그 {line}" for line in range(80)],
        )
        for order in range(1, 11)
    ]
    return RunView(
        run_id=RUN_ID_FAILED,
        system_code="hom",
        system_name="대표홈",
        status=RunStatus.ERROR,
        status_label="오류",
        requested_at=GEN_AT,
        modules=modules,
    )


class _FakeRunQueries:
    async def get_run_detail(self, run_id: str) -> RunView:
        if run_id != RUN_ID_FAILED:
            raise KeyError(run_id)
        return _failed_run()


class _NoHealing:
    async def list_events(self, **kwargs) -> dict:
        return {"items": [], "systems": []}


def _user() -> User:
    return User(
        user_id="run_viewport",
        email="run-viewport@test.local",
        name="Run Viewport",
        role="admin",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=[],
        created_at=GEN_AT,
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_run_queries] = _FakeRunQueries
    app.dependency_overrides[get_healing_service] = _NoHealing

    @app.websocket("/ws/runs/{run_id}")
    async def run_snapshot(websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        if run_id == RUN_ID_FAILED:
            await websocket.send_json(
                {"event_type": "snapshot", "payload": _failed_run().model_dump(mode="json")}
            )
        await websocket.close()

    return app


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _free_port()
    config = uvicorn.Config(_build_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server("127.0.0.1", port)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        chromium = playwright.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        playwright.stop()
        pytest.skip(f"Chromium 미설치 — python3 -m playwright install chromium 후 재실행: {exc}")
    yield chromium
    chromium.close()
    playwright.stop()


@pytest.fixture()
def page_factory(browser, live_server: str):
    contexts = []

    def create(width: int, height: int):
        context = browser.new_context(viewport={"width": width, "height": height})
        contexts.append(context)
        page = context.new_page()
        page.goto(f"{live_server}/runs/{RUN_ID_FAILED}", wait_until="networkidle")
        page.wait_for_selector('[data-focus="true"]')
        page.wait_for_function(
            """() => {
                const focused = document.querySelector('[data-focus="true"]');
                const filter = document.querySelector('#log-filter');
                return focused && filter && filter.value === focused.dataset.moduleId;
            }"""
        )
        return page

    yield create
    for context in contexts:
        context.close()


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_page_scroll(page_factory, width: int, height: int) -> None:
    page = page_factory(width, height)
    page.wait_for_selector(".run")
    overflow = page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )
    assert overflow <= 1, f"{width}x{height} 에서 세로 스크롤 {overflow}px"


def test_exactly_two_internal_scrollers_one_per_column(page_factory) -> None:
    """설계 D2 — 좌우 열에 하나씩. 세로로 쌓인 영역은 0."""
    page = page_factory(1920, 1080)
    page.wait_for_selector(".run-split")
    ids = page.evaluate(
        """() => Array.from(document.querySelectorAll('.run *'))
              .filter((el) => {
                  const style = getComputedStyle(el);
                  return /auto|scroll/.test(style.overflowY)
                      && el.scrollHeight > el.clientHeight + 1;
              })
              .map((el) => el.id || el.className)"""
    )
    assert len(ids) == 2, f"내부 스크롤러가 2개가 아니다: {ids}"


def test_focused_module_analysis_is_inside_the_viewport(page_factory) -> None:
    """is_visible() 은 뷰포트 밖 요소를 통과시킨다 — 좌표로 단언한다."""
    page = page_factory(1366, 768)
    page.wait_for_selector('[data-focus="true"]')
    box = page.locator('[data-focus="true"] [data-role="failure-analysis"]').bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= 768


def test_log_filter_follows_focus_until_user_touches_it(page_factory) -> None:
    """설계 D7 — 자동 추종은 사용자가 손대면 꺼진다."""
    page = page_factory(1920, 1080)
    page.wait_for_selector('[data-focus="true"]')
    focused = page.locator('[data-focus="true"]').get_attribute("data-module-id")
    assert page.locator("#log-filter").input_value() == focused
    page.select_option("#log-filter", "")
    assert page.locator("#log-filter").input_value() == ""
