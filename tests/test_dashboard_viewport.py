"""일간 대시보드 뷰포트 무스크롤 Playwright 테스트.

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

from app.api.dependencies import get_daily_queries, get_run_service
from app.api.routes_daily import router as daily_router
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.insights.application.daily_dashboard import build_daily_dashboard
from app.registry.loader import ModuleRegistry
from tests.test_dashboard_fragments_http import (
    FakeDailyDashboardQueries,
    FakeRunService,
    _build_realistic_six_system_dashboard,
)

pytest.importorskip("playwright")

GEN_AT = datetime(2026, 8, 15, 5, 0, tzinfo=UTC)

VIEWPORTS_MOBILE = [(320, 568), (390, 844)]
VIEWPORT_DESKTOP_720 = (1280, 720)
VIEWPORT_DESKTOP_1080 = (1920, 1080)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _rect_in_container(page, selector: str, *, container: str = ".dash") -> dict | None:
    return page.evaluate(
        """([sel, boxSel]) => {
            const el = document.querySelector(sel);
            const box = document.querySelector(boxSel);
            if (!el || !box) return null;
            const r = el.getBoundingClientRect();
            const b = box.getBoundingClientRect();
            return {
                left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                width: r.width, height: r.height,
                inBox: r.left >= b.left - 1 && r.right <= b.right + 1
                    && r.top >= b.top - 1 && r.bottom <= b.bottom + 1,
            };
        }""",
        [selector, container],
    )


def _wait_for_server(host: str, port: int, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"테스트 서버가 {timeout}s 내에 준비되지 않았습니다: {host}:{port}")


def _build_dashboard_test_app(
    *,
    user: User,
    dashboard_data: dict,
    registry: ModuleRegistry,
) -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router)
    app.include_router(daily_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_daily_queries] = lambda: FakeDailyDashboardQueries(dashboard_data)
    app.dependency_overrides[get_run_service] = lambda: FakeRunService(registry)
    return app


@pytest.fixture(scope="module")
def registry() -> ModuleRegistry:
    return ModuleRegistry()


@pytest.fixture(scope="module")
def dashboard_data(registry: ModuleRegistry) -> dict:
    data = _build_realistic_six_system_dashboard()
    assert len(data["systems"]) >= 6
    return data


@pytest.fixture(scope="module")
def dashboard_user(registry: ModuleRegistry) -> User:
    codes = [s.system_code for s in registry.list_systems()]
    return User(
        user_id="dash_viewport_user",
        email="dash-viewport@test.local",
        name="Dash Viewport",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=codes,
        created_at=GEN_AT,
    )


@pytest.fixture(scope="module")
def live_server(
    registry: ModuleRegistry,
    dashboard_data: dict,
    dashboard_user: User,
) -> str:
    port = _free_port()
    app = _build_dashboard_test_app(
        user=dashboard_user,
        dashboard_data=dashboard_data,
        registry=registry,
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server("127.0.0.1", port)
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def empty_day_live_server(
    registry: ModuleRegistry,
    dashboard_user: User,
) -> str:
    """All-not-inspected payload for HF-1 summary AC."""
    data = build_daily_dashboard(
        registry.list_systems(),
        [],
        generated_at=GEN_AT,
        date_label="2026-08-15",
    )
    port = _free_port()
    app = _build_dashboard_test_app(
        user=dashboard_user,
        dashboard_data=data,
        registry=registry,
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server("127.0.0.1", port)
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch()
    except Exception as exc:
        playwright.stop()
        pytest.skip(
            f"Chromium 미설치 — python3 -m playwright install chromium 후 재실행: {exc}"
        )
    yield browser
    browser.close()
    playwright.stop()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def _load_dashboard_and_assert_no_scroll(page, base_url: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{base_url}/")
    page.wait_for_selector("#dash-zone-matrix[data-system-count='6']", timeout=15000)
    page.wait_for_selector(".dash-sys-row", timeout=15000)
    page.evaluate(
        "() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    metrics = page.evaluate(
        """() => ({
            sh: document.documentElement.scrollHeight,
            ih: window.innerHeight,
            sw: document.documentElement.scrollWidth,
            iw: window.innerWidth,
        })"""
    )
    assert metrics["sh"] <= metrics["ih"], (
        f"vertical scroll: scrollHeight={metrics['sh']} > innerHeight={metrics['ih']} "
        f"at {width}x{height}"
    )
    assert metrics["sw"] <= metrics["iw"], (
        f"horizontal scroll: scrollWidth={metrics['sw']} > innerWidth={metrics['iw']} "
        f"at {width}x{height}"
    )


@pytest.mark.spec("SPEC-UI-004", "AC-001")
@pytest.mark.spec("SPEC-UI-005", "AC-005")
@pytest.mark.parametrize("width,height", VIEWPORTS_MOBILE)
def test_dashboard_no_scroll_mobile(
    page,
    live_server: str,
    width: int,
    height: int,
) -> None:
    _load_dashboard_and_assert_no_scroll(page, live_server, width, height)


@pytest.mark.spec("SPEC-UI-004", "AC-002")
@pytest.mark.spec("SPEC-UI-005", "AC-005")
def test_dashboard_no_scroll_1280x720(page, live_server: str) -> None:
    width, height = VIEWPORT_DESKTOP_720
    _load_dashboard_and_assert_no_scroll(page, live_server, width, height)


@pytest.mark.spec("SPEC-UI-004", "AC-003")
@pytest.mark.spec("SPEC-UI-005", "AC-005")
def test_dashboard_no_scroll_1920x1080(page, live_server: str) -> None:
    width, height = VIEWPORT_DESKTOP_1080
    _load_dashboard_and_assert_no_scroll(page, live_server, width, height)


@pytest.mark.spec("SPEC-UI-005", "AC-001")
def test_dashboard_hero_visible_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-hero__title")
    title = page.locator(".dash-hero__title")
    assert title.is_visible()
    assert title.inner_text() == "오늘의 점검 현황"
    label = page.locator(".dash-hero__rate-label")
    assert label.is_visible()
    assert label.inner_text() == "통과율"
    box = title.bounding_box()
    assert box is not None and box["height"] >= 16 and box["width"] >= 120


@pytest.mark.spec("SPEC-UI-005", "AC-005")
def test_dashboard_zone_c_internal_scroll_document_fixed(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-matrix")
    overflow = page.eval_on_selector(".dash__systems", "el => getComputedStyle(el).overflowY")
    assert overflow == "auto"
    metrics = page.evaluate(
        "() => ({ sh: document.documentElement.scrollHeight, ih: window.innerHeight })"
    )
    assert metrics["sh"] <= metrics["ih"]


@pytest.mark.spec("SPEC-UI-005", "AC-003")
def test_dashboard_system_name_min_font(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row__name")
    fs = page.eval_on_selector(
        ".dash-sys-row__name",
        "el => parseFloat(getComputedStyle(el).fontSize)",
    )
    assert fs >= 14


@pytest.mark.spec("SPEC-UI-005", "AC-008")
def test_dashboard_attention_visible_mobile(page, live_server: str) -> None:
    page.set_viewport_size({"width": 320, "height": 568})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-attention")
    assert page.locator("#dash-zone-attention").is_visible()
    assert page.locator('a.dash-attention__inbox[href="/anomalies"]').count() == 1


@pytest.mark.spec("SPEC-UI-006", "AC-001")
def test_hero_title_in_view_1280x720(page, empty_day_live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{empty_day_live_server}/")
    page.wait_for_selector(".dash-hero__title")
    rect = _rect_in_container(page, ".dash-hero__title")
    assert rect and rect["width"] >= 120 and rect["height"] >= 16 and rect["inBox"]
    assert "아직 점검이 시작되지 않았습니다" in page.locator(".dash-hero__summary").inner_text()
    assert page.locator(".dash-hero__rate-label").is_visible()


@pytest.mark.spec("SPEC-UI-006", "AC-002")
def test_system_identity_in_view_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row__icon")
    icon = _rect_in_container(page, ".dash-sys-row__icon")
    name = _rect_in_container(page, ".dash-sys-row__name")
    assert icon and icon["width"] >= 24 and icon["height"] >= 24 and icon["inBox"]
    assert name and name["width"] >= 40 and name["inBox"]
    fs = page.eval_on_selector(
        ".dash-sys-row__name",
        "el => parseFloat(getComputedStyle(el).fontSize)",
    )
    assert fs >= 14


@pytest.mark.spec("SPEC-UI-006", "AC-003")
def test_all_four_kpi_tiles_in_dash_box(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-stats .dash-stats__tile")
    tiles = page.locator("#dash-zone-stats .dash-stats__tile")
    assert tiles.count() == 4
    for i in range(4):
        sel = f"#dash-zone-stats .dash-stats__tile:nth-child({i + 1})"
        rect = _rect_in_container(page, sel)
        assert rect and rect["inBox"], f"tile {i} outside .dash"
    assert tiles.first.locator(".dash-stats__label").inner_text() == "이상징후"
