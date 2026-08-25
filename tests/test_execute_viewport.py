"""점검 실행 넌스크롤 Playwright 테스트.

Chromium 미설치 시 ``python3 -m playwright install chromium`` 후 재실행.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import UTC, datetime

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import get_run_service
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.registry.loader import ModuleRegistry
from tests.test_dashboard_fragments_http import FakeRunService

pytest.importorskip("playwright")

GEN_AT = datetime(2026, 8, 25, 5, 0, tzinfo=UTC)
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


def _assert_no_scroll(page, selector: str) -> None:
    result = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return { ok: false, reason: 'missing' };
            const oy = getComputedStyle(el).overflowY;
            return {
                ok: el.scrollHeight <= el.clientHeight + 1 && oy !== 'auto' && oy !== 'scroll',
                scrollHeight: el.scrollHeight,
                clientHeight: el.clientHeight,
                overflowY: oy,
            };
        }""",
        selector,
    )
    assert result["ok"], f"{selector}: {result}"


def _assert_in_viewport(locator, width: int, height: int) -> None:
    assert locator.is_visible()
    box = locator.bounding_box()
    assert box is not None
    assert 0 <= box["x"]
    assert 0 <= box["y"]
    assert box["x"] + box["width"] <= width
    assert box["y"] + box["height"] <= height


def _build_execute_test_app(*, user: User, registry: ModuleRegistry) -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_run_service] = lambda: FakeRunService(registry)
    return app


@pytest.fixture(scope="module")
def registry() -> ModuleRegistry:
    return ModuleRegistry()


@pytest.fixture(scope="module")
def execute_user(registry: ModuleRegistry) -> User:
    return User(
        user_id="execute_viewport_user",
        email="execute-viewport@test.local",
        name="Execute Viewport",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=[system.system_code for system in registry.list_systems()],
        created_at=GEN_AT,
    )


@pytest.fixture(scope="module")
def live_server(registry: ModuleRegistry, execute_user: User) -> str:
    port = _free_port()
    app = _build_execute_test_app(user=execute_user, registry=registry)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
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
    except Exception as exc:
        playwright.stop()
        pytest.skip(f"Chromium 미설치 — python3 -m playwright install chromium 후 재실행: {exc}")
    yield chromium
    chromium.close()
    playwright.stop()


@pytest.fixture()
def page(browser, live_server):
    """뷰포트를 바꿔 가며 쓰므로 컨텍스트를 테스트마다 새로 연다."""
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_page_scroll(page, live_server: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/runs/execute", wait_until="networkidle")
    page.wait_for_selector(".exec")
    overflow = page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )
    assert overflow <= 1, f"{width}x{height} 에서 세로 스크롤 {overflow}px"


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_start_button_is_visible_without_scrolling(
    page, live_server: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/runs/execute", wait_until="networkidle")
    page.wait_for_selector("#suite-start-button")
    button = page.locator("#suite-start-button")
    _assert_in_viewport(button, width, height)
    suite_bar = page.locator('[data-exec-panel="suite"] .exec-action-bar')
    assert suite_bar.count() == 1
    assert suite_bar.evaluate("el => getComputedStyle(el).position") == "sticky"


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_system_start_button_is_sticky_and_visible_without_scrolling(
    page, live_server: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/runs/execute", wait_until="networkidle")
    page.wait_for_selector('[data-exec-target="hom"]')
    page.click('[data-exec-target="hom"]')
    selector = 'button[type="submit"][data-system-code="hom"]'
    page.wait_for_selector(selector)
    button = page.locator(selector)
    _assert_in_viewport(button, width, height)
    system_bar = page.locator('[data-exec-panel="hom"] .exec-action-bar')
    assert system_bar.count() == 1
    assert system_bar.evaluate("el => getComputedStyle(el).position") == "sticky"


def test_left_column_does_not_scroll(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/runs/execute", wait_until="networkidle")
    page.wait_for_selector(".exec")
    _assert_no_scroll(page, ".exec-master")


def test_exactly_one_internal_scroller(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/runs/execute", wait_until="networkidle")
    page.wait_for_selector(".exec")
    scrollers = page.evaluate(
        """() => Array.from(document.querySelectorAll('.exec *'))
              .filter((el) => {
                  const style = getComputedStyle(el);
                  const scrollable = /auto|scroll/.test(style.overflowY);
                  return scrollable && el.scrollHeight > el.clientHeight + 1;
              })
              .map((el) => el.className)"""
    )
    assert len(scrollers) <= 1, f"내부 스크롤러가 여럿: {scrollers}"


def test_selecting_a_system_swaps_the_panel(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/runs/execute", wait_until="networkidle")
    page.wait_for_selector('[data-exec-target="hom"]')
    page.wait_for_selector('[data-exec-panel="suite"]:visible')
    page.click('[data-exec-target="hom"]')
    page.wait_for_selector('[data-exec-panel="hom"]:visible')
    assert page.locator('[data-exec-panel="hom"]').is_visible()
    assert not page.locator('[data-exec-panel="suite"]').is_visible()
