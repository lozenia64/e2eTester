"""수트 상세 넌스크롤 좌표 계약 — Playwright 회귀(설계 §5).

`is_visible()` 은 뷰포트 밖 요소를 통과시킨다 — 좌표(`bounding_box()`)로 단언한다.
넌스크롤 예산 여유가 최악 조건에서 ~109px 뿐이라(설계 §3.1) 이 케이스가 경계다.

Chromium 미설치 시 ``python3 -m playwright install chromium`` 후 재실행.
서버 기동 픽스처는 tests/test_dashboard_viewport.py 를 본떴다 — 세 번째 사용처가
생기면 공통으로 뽑는다(지금은 두 번째).
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

from app.api.dependencies import get_run_summary_query, get_suite_service
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteRun, SuiteStep

pytest.importorskip("playwright")

GEN_AT = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)

SUITE_RUNNING_ID = "suite_running"
SUITE_SIX_WAITING_ID = "suite_six_waiting"

_SIX = [
    ("hom", "대표홈"),
    ("mhm", "모바일대표홈"),
    ("fp", "위촉서류"),
    ("hrp", "현장출동"),
    ("hwtc", "연수원"),
    ("chbot", "챗봇"),
]
_BASELINES = {
    "hom": 192_000,
    "mhm": 108_000,
    "fp": 150_000,
    "hrp": 125_000,
    "hwtc": 90_000,
    "chbot": 55_000,
}


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


def _step(order: int, code: str, name: str, status: SuiteStatus, run_id: str | None) -> SuiteStep:
    return SuiteStep(
        system_code=code,
        system_name=name,
        order=order,
        run_id=run_id,
        status=status,
        module_total=3,
    )


def _suite_running() -> SuiteRun:
    """3~4 스텝 진행 중 — order 2 가 RUNNING 이라 expanded_step_order == 2."""
    steps = [
        _step(0, "hom", "대표홈", SuiteStatus.PASSED, "r0"),
        _step(1, "mhm", "모바일대표홈", SuiteStatus.PASSED, "r1"),
        _step(2, "fp", "위촉서류", SuiteStatus.RUNNING, "r2"),
        _step(3, "hrp", "현장출동", SuiteStatus.PENDING, None),
    ]
    return SuiteRun(
        suite_id=SUITE_RUNNING_ID,
        status=SuiteStatus.RUNNING,
        steps=steps,
        current_step_index=2,
        requested_at=GEN_AT,
        started_at=GEN_AT,
        selected_system_codes=[c for c, _ in _SIX[:4]],
    )


def _suite_six_waiting() -> SuiteRun:
    """시스템 6개 + OTP 대기 — 설계 §3.1 예산의 최악 조건."""
    steps = [
        _step(0, "hom", "대표홈", SuiteStatus.PASSED, "r0"),
        _step(1, "mhm", "모바일대표홈", SuiteStatus.PASSED, "r1"),
        _step(2, "fp", "위촉서류", SuiteStatus.WAITING_INPUT, "r2"),
        _step(3, "hrp", "현장출동", SuiteStatus.PENDING, None),
        _step(4, "hwtc", "연수원", SuiteStatus.PENDING, None),
        _step(5, "chbot", "챗봇", SuiteStatus.PENDING, None),
    ]
    return SuiteRun(
        suite_id=SUITE_SIX_WAITING_ID,
        status=SuiteStatus.WAITING_INPUT,
        steps=steps,
        current_step_index=2,
        requested_at=GEN_AT,
        started_at=GEN_AT,
        awaiting_input_run_id="r2",
        awaiting_input_prompt="휴대폰으로 받은 OTP를 입력하세요.",
        selected_system_codes=[c for c, _ in _SIX],
    )


class _FakeSuiteService:
    _suites = {SUITE_RUNNING_ID: _suite_running, SUITE_SIX_WAITING_ID: _suite_six_waiting}

    async def get_suite(self, suite_id: str) -> SuiteRun:
        try:
            return self._suites[suite_id]()
        except KeyError as exc:  # noqa: TRY003
            raise KeyError(suite_id) from exc


class _FakeRunSummaryQuery:
    async def avg_duration_ms_by_system(self, *, days: int = 30) -> dict[str, int]:
        return dict(_BASELINES)


def _user() -> User:
    return User(
        user_id="suite_viewport",
        email="suite-viewport@test.local",
        name="Suite Viewport",
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
    app.dependency_overrides[get_suite_service] = _FakeSuiteService
    app.dependency_overrides[get_run_summary_query] = _FakeRunSummaryQuery
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
        browser = playwright.chromium.launch()
    except Exception as exc:  # noqa: BLE001
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


def _page_overflow(page) -> int:
    return page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )


@pytest.mark.parametrize("width,height", [(1366, 768), (1920, 1080), (2560, 1440)])
def test_no_page_scroll(page, live_server: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/suites/{SUITE_RUNNING_ID}")
    page.wait_for_selector(".suite")
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    overflow = _page_overflow(page)
    assert overflow <= 1, f"{width}x{height} 에서 세로 스크롤 {overflow}px"


def test_expanded_step_is_inside_the_viewport(page, live_server: str) -> None:
    """is_visible() 은 뷰포트 밖 요소를 통과시킨다 — 좌표로 단언한다(설계 §5).

    모듈 칩은 서버 렌더 시 native ``hidden`` 이고 WS 이벤트가 채운다. Playwright
    하네스에는 라이브 WS 가 없으므로, 모듈 이벤트가 도착한 상태를 흉내내 칩을
    열고 대표 길이의 텍스트를 넣은 뒤 좌표를 잰다 — 이 단언이 지키는 것은
    "전개된 행의 칩이 넌스크롤 예산 안에 들어오는가" 다(설계 §3.1).
    """
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{live_server}/suites/{SUITE_RUNNING_ID}")
    page.wait_for_selector('[data-expanded="true"]')
    page.evaluate(
        """() => {
            const chip = document.querySelector('[data-expanded="true"] [data-role="step-module-progress"]');
            chip.hidden = false;
            chip.dataset.tone = 'active';
            chip.textContent = '모듈 2/3 실행 중 · 서류 업로드';
        }"""
    )
    box = page.locator('[data-expanded="true"] [data-role="step-module-progress"]').bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= 768


def test_exactly_one_internal_scroller(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/suites/{SUITE_RUNNING_ID}")
    page.wait_for_selector(".suite")
    scrollers = page.evaluate(
        """() => Array.from(document.querySelectorAll('.suite *'))
              .filter((el) => {
                  const style = getComputedStyle(el);
                  return /auto|scroll/.test(style.overflowY)
                      && el.scrollHeight > el.clientHeight + 1;
              })
              .map((el) => el.className)"""
    )
    assert len(scrollers) <= 1, f"내부 스크롤러가 여럿: {scrollers}"


def test_worst_case_six_steps_with_otp_fits(page, live_server: str) -> None:
    """설계 §3.1 예산의 최악 조건. 여유가 109px 뿐이라 이 케이스가 경계다."""
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{live_server}/suites/{SUITE_SIX_WAITING_ID}")
    page.wait_for_selector("#suite-otp-panel:not([hidden])")
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    overflow = _page_overflow(page)
    assert overflow <= 1, f"6 스텝 + OTP 에서 세로 스크롤 {overflow}px"
