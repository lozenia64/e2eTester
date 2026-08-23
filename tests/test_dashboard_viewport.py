"""일간 대시보드 뷰포트 무스크롤 Playwright 테스트.

Chromium 미설치 시 ``python3 -m playwright install chromium`` 후 재실행.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.api.dependencies import get_daily_queries, get_daily_summary_queries, get_run_service
from app.api.routes_daily import router as daily_router
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.insights.application.daily_dashboard import build_daily_dashboard_from_projection
from app.registry.loader import ModuleRegistry
from tests.test_dashboard_fragments_http import (
    FakeDailyDashboardQueries,
    FakeDailySummaryQueries,
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


def _sidebar_inset_metrics(page) -> dict:
    return page.evaluate(
        """() => {
            const sb = document.querySelector('#app-sidebar');
            const dash = document.querySelector('.dash');
            const main = document.querySelector('main');
            if (!sb || !dash || !main) return { ok: false, reason: 'missing' };
            const sr = sb.getBoundingClientRect();
            const dr = dash.getBoundingClientRect();
            const mcs = getComputedStyle(main);
            const overlapPx = Math.max(0, sr.right - dr.left);
            return {
                ok: overlapPx <= 1 && dr.left >= sr.right - 1,
                dashLeft: dr.left,
                sidebarRight: sr.right,
                sidebarWidth: sr.width,
                overlapPx,
                mainPaddingLeft: mcs.paddingLeft,
                dashWidth: dr.width,
                innerWidth: window.innerWidth,
            };
        }"""
    )


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


def _wait_for_density_stable(page) -> None:
    page.wait_for_function(
        """() => {
            const sys = document.querySelector('.dash__systems');
            if (!sys) return false;
            return sys.scrollHeight <= sys.clientHeight + 1;
        }""",
        timeout=20000,
    )
    page.wait_for_timeout(200)


def _load_dashboard_1280x720(page, base_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{base_url}/")
    page.wait_for_selector("#dash-zone-matrix[data-system-count='6']", timeout=15000)
    page.wait_for_selector(".dash__systems")
    _wait_for_density_stable(page)


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
    app.dependency_overrides[get_daily_summary_queries] = lambda: FakeDailySummaryQueries(
        dashboard_data
    )
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
    data = build_daily_dashboard_from_projection(
        registry.list_systems(),
        [],
        [],
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
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
        pytest.skip(f"Chromium 미설치 — python3 -m playwright install chromium 후 재실행: {exc}")
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
@pytest.mark.spec("SPEC-UI-007", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-002")
@pytest.mark.parametrize("width,height", VIEWPORTS_MOBILE)
def test_dashboard_no_scroll_mobile(
    page,
    live_server: str,
    width: int,
    height: int,
) -> None:
    _load_dashboard_and_assert_no_scroll(page, live_server, width, height)


@pytest.mark.spec("SPEC-UI-004", "AC-002")
@pytest.mark.spec("SPEC-UI-007", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-002")
def test_dashboard_no_scroll_1280x720(page, live_server: str) -> None:
    width, height = VIEWPORT_DESKTOP_720
    _load_dashboard_and_assert_no_scroll(page, live_server, width, height)


@pytest.mark.spec("SPEC-UI-004", "AC-003")
@pytest.mark.spec("SPEC-UI-007", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-002")
def test_dashboard_no_scroll_1920x1080(page, live_server: str) -> None:
    width, height = VIEWPORT_DESKTOP_1080
    _load_dashboard_and_assert_no_scroll(page, live_server, width, height)


@pytest.mark.spec("SPEC-UI-005", "AC-001")
def test_dashboard_hero_visible_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".status-hero__headline")
    headline = page.locator(".status-hero__headline")
    ring = page.locator(".status-hero__ring")
    assert headline.is_visible()
    assert ring.is_visible()
    assert ring.get_attribute("data-passed") is not None
    assert ring.get_attribute("data-total") is not None
    # _build_realistic_six_system_dashboard 는 hom 시스템에 ERROR 를 심어 두므로
    # 히어로 문장은 진행 링 아래에 보존된 점검실패 분기를 탄다.
    headline_text = headline.inner_text()
    assert "점검실패" in headline_text and "우선 확인이 필요합니다" in headline_text
    box = headline.bounding_box()
    assert box is not None and box["height"] >= 16 and box["width"] >= 120
    first_card = page.locator(".status-hero__cards .kpi-card").first
    assert first_card.is_visible()


@pytest.mark.spec("SPEC-UI-007", "AC-002")
def test_dashboard_zone_c_fits_without_scroll(page, live_server: str) -> None:
    _load_dashboard_1280x720(page, live_server)
    _assert_no_scroll(page, ".dash__systems")
    doc = page.evaluate(
        "() => ({ sh: document.documentElement.scrollHeight, ih: window.innerHeight })"
    )
    assert doc["sh"] <= doc["ih"]


@pytest.mark.spec("SPEC-UI-007", "AC-002")
def test_zone_c_no_internal_scroll_1280x720(page, live_server: str) -> None:
    _load_dashboard_1280x720(page, live_server)
    _assert_no_scroll(page, ".dash__systems")
    has_scrollable = page.evaluate(
        "() => document.querySelector('.dash__systems')?.dataset.scrollable"
    )
    assert has_scrollable in (None, "", "false")


@pytest.mark.spec("SPEC-UI-007", "AC-003")
def test_system_rows_equal_partition_1280x720(page, live_server: str) -> None:
    _load_dashboard_1280x720(page, live_server)
    page.wait_for_selector(".dash-sys-row")
    metrics = page.evaluate(
        """() => {
            const rows = [...document.querySelectorAll('.dash-sys-row')];
            const heights = rows.map((r) => r.clientHeight);
            const sys = document.querySelector('.dash__systems');
            const gap = parseFloat(getComputedStyle(sys).rowGap || getComputedStyle(sys).gap) || 0;
            const sum = heights.reduce((a, b) => a + b, 0) + gap * Math.max(0, heights.length - 1);
            return {
                heights,
                spread: Math.max(...heights) - Math.min(...heights),
                sum,
                container: sys.clientHeight,
            };
        }"""
    )
    assert metrics["spread"] <= 2, metrics
    assert abs(metrics["sum"] - metrics["container"]) <= 4, metrics


@pytest.mark.spec("SPEC-UI-007", "AC-007")
@pytest.mark.parametrize("width,height", [(1280, 720), (1920, 1080), (320, 568)])
def test_no_data_scrollable_dataset(page, live_server: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-matrix")
    assert page.evaluate(
        "() => !document.querySelector('.dash__systems')?.hasAttribute('data-scrollable')"
        " || document.querySelector('.dash__systems').dataset.scrollable === 'false'"
    )


@pytest.mark.spec("SPEC-UI-007", "AC-006")
def test_no_density_dataset_and_still_fits_at_568(page, live_server: str) -> None:
    """밀도 티어 JS 철거 후에도 좁은 뷰포트에서 넘치지 않아야 한다."""
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(live_server, wait_until="networkidle")
    page.set_viewport_size({"width": 1280, "height": 568})
    page.wait_for_timeout(300)
    state = page.evaluate(
        """() => {
            const de = document.documentElement;
            const sys = document.querySelector('#dash-zone-matrix');
            return {
                density: sys ? sys.dataset.density ?? null : null,
                inlineFlex: sys
                    ? [...sys.querySelectorAll('.dash-sys-row')].some((r) => r.style.flex !== '')
                    : false,
                docOk: de.scrollHeight <= window.innerHeight + 1,
                zoneOk: sys ? sys.scrollHeight <= sys.clientHeight + 1 : false,
            };
        }"""
    )
    assert state["density"] is None, "data-density 가 남아 있다 — 밀도 JS 가 살아있음"
    assert state["inlineFlex"] is False, "행에 인라인 flex 가 남아 있다 — 밀도 JS 가 살아있음"
    assert state["docOk"], "문서가 세로로 넘친다"
    assert state["zoneOk"], "매트릭스 존이 내부 스크롤을 만든다"


@pytest.mark.spec("SPEC-UI-007", "AC-008")
def test_attention_row_inset_accent_1280x720(page, live_server: str) -> None:
    _load_dashboard_1280x720(page, live_server)
    result = page.evaluate(
        """() => {
            const row = document.querySelector('.dash-sys-row[data-system-code="hom"]');
            if (!row) return { ok: false, reason: 'no hom row' };
            const cs = getComputedStyle(row);
            const shadow = cs.boxShadow || '';
            const borderLeft = cs.borderLeftWidth;
            return {
                ok: row.dataset.priority === 'attention'
                    && shadow.includes('inset')
                    && shadow.includes('3px')
                    && (borderLeft === '0px' || cs.borderStyle === 'none'),
                priority: row.dataset.priority,
                boxShadow: shadow,
                borderLeftWidth: borderLeft,
            };
        }"""
    )
    assert result["ok"], result


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


@pytest.mark.spec("SPEC-UI-007", "AC-009")
def test_matrix_run_cell_has_token_focus_outline(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-cell--link")
    page.locator(".dash-cell--link").first.focus()
    outline = page.eval_on_selector(
        ".dash-cell--link",
        """el => {
            const style = getComputedStyle(el);
            const probe = document.createElement('span');
            probe.style.color = 'var(--st-running-solid)';
            document.body.append(probe);
            const tokenColor = getComputedStyle(probe).color;
            probe.remove();
            return {
                width: style.outlineWidth,
                style: style.outlineStyle,
                color: style.outlineColor,
                offset: style.outlineOffset,
                tokenColor,
            };
        }""",
    )
    assert outline == {
        "width": "2px",
        "style": "solid",
        "color": outline["tokenColor"],
        "offset": "2px",
        "tokenColor": outline["tokenColor"],
    }


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
    page.wait_for_selector(".status-hero__headline")
    rect = _rect_in_container(page, ".status-hero__headline")
    assert rect and rect["width"] >= 120 and rect["height"] >= 16 and rect["inBox"]
    assert "아직 점검이 시작되지 않았습니다" in page.locator(".status-hero__headline").inner_text()
    ring = page.locator(".status-hero__ring")
    assert ring.get_attribute("data-passed") == "0"
    assert ring.get_attribute("data-total") is not None
    assert page.locator(".status-hero__cards .kpi-card").first.is_visible()


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
    page.wait_for_selector(".status-hero__cards .kpi-card")
    tiles = page.locator(".status-hero__cards .kpi-card")
    assert tiles.count() == 4
    for i in range(4):
        sel = f".status-hero__cards .kpi-card:nth-child({i + 1})"
        rect = _rect_in_container(page, sel)
        assert rect and rect["inBox"], f"tile {i} outside .dash"


@pytest.mark.spec("SPEC-UI-008", "AC-001")
def test_dash_not_under_sidebar_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#app-sidebar")
    page.wait_for_selector(".dash")
    m = _sidebar_inset_metrics(page)
    assert m["ok"], m
    assert m["overlapPx"] <= 1, m


@pytest.mark.spec("SPEC-UI-008", "AC-002")
def test_main_padding_left_desktop_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("main")
    pl = page.eval_on_selector("main", "el => getComputedStyle(el).paddingLeft")
    assert pl in ("256px", "16rem") or float(pl.replace("px", "")) >= 250, pl


@pytest.mark.spec("SPEC-UI-008", "AC-003")
def test_hero_and_first_kpi_right_of_sidebar(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".status-hero__headline")
    m = _sidebar_inset_metrics(page)
    sw = m["sidebarWidth"]
    headline_left = page.eval_on_selector(
        ".status-hero__headline", "el => el.getBoundingClientRect().left"
    )
    tile_left = page.eval_on_selector(
        ".status-hero__cards .kpi-card:first-child",
        "el => el.getBoundingClientRect().left",
    )
    assert headline_left >= sw - 1, {"headline_left": headline_left, "sidebarWidth": sw}
    assert tile_left >= sw - 1, {"tile_left": tile_left, "sidebarWidth": sw}


@pytest.mark.spec("SPEC-UI-008", "AC-004")
def test_system_identity_right_of_sidebar(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row__icon")
    sw = _sidebar_inset_metrics(page)["sidebarWidth"]
    icon_left = page.eval_on_selector(
        ".dash-sys-row__icon", "el => el.getBoundingClientRect().left"
    )
    name_left = page.eval_on_selector(
        ".dash-sys-row__name", "el => el.getBoundingClientRect().left"
    )
    assert icon_left >= sw - 1
    assert name_left >= sw - 1


@pytest.mark.spec("SPEC-UI-008", "AC-005")
def test_no_main_inset_mobile_390x844(page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash")
    pl = page.eval_on_selector("main", "el => getComputedStyle(el).paddingLeft")
    assert pl == "0px", pl
    dash_left = page.eval_on_selector(".dash", "el => el.getBoundingClientRect().left")
    assert dash_left <= 1, dash_left


# ── Task 7: status-hero 지배 상태 계약 ──────────────────────────────────────


@pytest.fixture()
def kpi_fragment_html():
    from app.api.dependencies import get_daily_queries, get_daily_summary_queries
    from app.api.routes_daily import router as daily_router
    from app.contexts.identity.dependencies import get_current_user
    from tests.test_daily_summary_http import SUMMARY, FakeDailySummaryQueries, _member

    app = FastAPI()
    app.include_router(daily_router)
    app.dependency_overrides[get_daily_summary_queries] = lambda: FakeDailySummaryQueries()
    app.dependency_overrides[get_daily_queries] = lambda: None
    app.dependency_overrides[get_current_user] = _member
    with TestClient(app) as client:
        response = client.get("/api/dashboard/daily/fragments/kpi")
        assert response.status_code == 200, response.text
        return response.text


def test_status_hero_contains_ring_headline_and_card_stack(kpi_fragment_html):
    """밴드를 더하지 않고 교체한다. 넌스크롤 예산이 늘면 안 된다."""
    assert 'class="status-hero"' in kpi_fragment_html
    assert 'class="status-hero__ring"' in kpi_fragment_html
    assert 'data-passed="' in kpi_fragment_html
    assert 'data-total="' in kpi_fragment_html
    assert 'class="status-hero__headline"' in kpi_fragment_html
    assert 'class="status-hero__cards"' in kpi_fragment_html
    assert "dash-stats" not in kpi_fragment_html
    assert "kpi-band" not in kpi_fragment_html


def test_status_hero_renders_exactly_four_cards(kpi_fragment_html):
    assert kpi_fragment_html.count('class="kpi-card"') == 4


def test_status_hero_ring_exposes_passed_and_total(kpi_fragment_html):
    assert 'data-passed="' in kpi_fragment_html
    assert 'data-total="' in kpi_fragment_html


def test_estimated_card_shows_badge_and_note(kpi_fragment_html):
    assert "kpi-card__badge" in kpi_fragment_html
    assert "추정" in kpi_fragment_html


def test_pending_patches_card_links_to_patches(kpi_fragment_html):
    assert 'href="/self-healing#patches"' in kpi_fragment_html


def test_three_column_layout_at_1920(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(live_server, wait_until="networkidle")
    boxes = page.evaluate(
        """() => {
            const pick = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { left: Math.round(r.left), top: Math.round(r.top), w: Math.round(r.width) };
            };
            return {
                hero: pick('#dash-host-kpi'),
                matrix: pick('#dash-host-matrix'),
                activity: pick('#dash-host-activity'),
            };
        }"""
    )
    assert boxes["hero"] and boxes["matrix"] and boxes["activity"]
    # 세 열이 같은 행에 나란히 — 좌→우 순서
    assert boxes["hero"]["left"] < boxes["matrix"]["left"] < boxes["activity"]["left"]
    assert abs(boxes["hero"]["top"] - boxes["matrix"]["top"]) <= 2
    assert abs(boxes["matrix"]["top"] - boxes["activity"]["top"]) <= 2


def test_only_activity_column_scrolls_internally(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(live_server, wait_until="networkidle")
    state = page.evaluate(
        """() => {
            const ov = (sel) => {
                const el = document.querySelector(sel);
                return el ? getComputedStyle(el).overflowY : null;
            };
            return {
                doc: document.documentElement.scrollHeight <= window.innerHeight + 1,
                hero: ov('#dash-host-kpi'),
                matrix: ov('#dash-host-matrix'),
                activity: ov('#dash-host-activity'),
            };
        }"""
    )
    assert state["doc"], "문서가 세로로 넘친다"
    assert state["hero"] == "hidden"
    assert state["matrix"] == "hidden"
    assert state["activity"] in ("auto", "scroll")


def test_stacks_to_single_column_on_mobile(page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server, wait_until="networkidle")
    boxes = page.evaluate(
        """() => {
            const pick = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { left: Math.round(r.left), top: Math.round(r.top) };
            };
            return { hero: pick('#dash-host-kpi'), matrix: pick('#dash-host-matrix') };
        }"""
    )
    assert boxes["hero"]["left"] == boxes["matrix"]["left"], "모바일에서 열이 나란히 있다"
    assert boxes["matrix"]["top"] > boxes["hero"]["top"], "모바일에서 세로 스택이 아니다"


def test_dashboard_uses_two_columns_at_1280_with_shell_relative_padding(
    page, live_server: str
) -> None:
    """dash-shell 분기 누락으로 생기는 빈 셋째 열과 viewport 기준 cqi를 막는다."""
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(live_server, wait_until="networkidle")
    state = page.evaluate(
        """() => {
            const pick = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    left: r.left,
                    top: r.top,
                    right: r.right,
                    bottom: r.bottom,
                };
            };
            const dash = document.querySelector('.dash');
            const matrix = pick('#dash-host-matrix');
            return {
                dash: dash ? pick('.dash') : null,
                hero: pick('#dash-host-kpi'),
                matrix,
                activity: pick('#dash-host-activity'),
                paddingLeft: dash ? parseFloat(getComputedStyle(dash).paddingLeft) : null,
            };
        }"""
    )
    assert state["dash"] and state["hero"] and state["matrix"] and state["activity"]
    assert state["hero"]["left"] < state["matrix"]["left"]
    assert state["activity"]["left"] == pytest.approx(state["hero"]["left"], abs=2)
    assert state["activity"]["top"] > state["hero"]["top"]
    assert state["matrix"]["top"] == pytest.approx(state["hero"]["top"], abs=2)
    assert state["matrix"]["bottom"] == pytest.approx(state["activity"]["bottom"], abs=2)
    assert state["matrix"]["right"] == pytest.approx(
        state["dash"]["right"] - state["paddingLeft"], abs=2
    )
    assert 18 <= state["paddingLeft"] <= 22, state


def test_matrix_row_is_single_line_with_cells(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(live_server, wait_until="networkidle")
    shape = page.evaluate(
        """() => {
            const row = document.querySelector('.dash-sys-row');
            if (!row) return null;
            const cells = row.querySelectorAll('.dash-cell');
            const tops = [...cells].map((c) => Math.round(c.getBoundingClientRect().top));
            return {
                cellCount: cells.length,
                displays: [...cells].map((c) => getComputedStyle(c).display),
                sameLine: tops.length > 0 && new Set(tops).size === 1,
                legacyPills: row.querySelectorAll('.dash-mod').length,
                legacySegments: row.querySelectorAll('.dash-seg').length,
            };
        }"""
    )
    assert shape is not None
    assert shape["cellCount"] > 0, "모듈 셀이 없다"
    assert set(shape["displays"]) == {"grid"}, "대시보드 CSS가 셀에 적용되지 않았다"
    assert shape["sameLine"], "셀이 한 줄에 있지 않다"
    assert shape["legacyPills"] == 0, "레거시 module_pill 이 남아 있다"
    assert shape["legacySegments"] == 0, "레거시 segment bar 가 남아 있다"


def test_reduced_motion_disables_cell_animation(browser, live_server: str) -> None:
    context = browser.new_context(reduced_motion="reduce", viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    page.goto(live_server, wait_until="networkidle")
    motion = page.evaluate(
        """() => [...document.querySelectorAll('.dash-cell')]
            .map((c) => {
                const style = getComputedStyle(c);
                return { animationName: style.animationName, transitionProperty: style.transitionProperty };
            })"""
    )
    context.close()
    assert motion, "셀이 없다"
    names = [item["animationName"] for item in motion]
    transitions = [item["transitionProperty"] for item in motion]
    assert all(name == "none" for name in names), f"reduced-motion 인데 애니메이션이 산다: {names}"
    assert all(transition == "none" for transition in transitions), (
        f"reduced-motion 인데 전이가 산다: {transitions}"
    )
