"""Run 이력 격자 넌스크롤 좌표 계약 — Playwright 회귀(설계 §3.1·D1·D6).

미실행 칸이 실제로 그려지는지가 이 화면의 존재 이유다(§2.3 성공 기준).
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

from app.api.dependencies import get_admin_dashboard_queries, get_run_queries
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_runs import router as runs_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User

pytest.importorskip("playwright")

GEN_AT = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
VIEWPORTS = [(1366, 768), (1920, 1080), (2560, 1440)]
DAY_KEYS = [f"2026-08-{day:02d}" for day in range(27, 32)] + ["2026-09-01", "2026-09-02"]
SLOTS = ("morning", "afternoon", "evening")
SYSTEMS = (("hom", "대표홈"), ("mhm", "회원홈"))

# hom 의 8/29 는 3슬롯이 전부 비어 있다 — 미실행 칸이 그려져야 한다.
BLANK_DAY = "2026-08-29"


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


def _cell(day_key: str, slot_id: str, tone: str) -> dict:
    checked = tone != "not_checked"
    return {
        "day_key": day_key,
        "slot_id": slot_id,
        "status": tone,
        "status_label": None,
        "tone": tone,
        "run_id": f"run_{day_key}_{slot_id}" if checked else None,
        "checked_at": f"{day_key}T04:00:00+00:00" if checked else None,
    }


def _coverage_payload() -> dict:
    systems = []
    for system_code, system_name in SYSTEMS:
        cells = []
        for day_key in DAY_KEYS:
            for index, slot_id in enumerate(SLOTS):
                blank = system_code == "hom" and day_key == BLANK_DAY
                if blank or index > 0:
                    tone = "not_checked"
                elif day_key == "2026-08-28" and system_code == "mhm":
                    tone = "error"
                else:
                    tone = "passed"
                cells.append(_cell(day_key, slot_id, tone))
        systems.append(
            {
                "system_code": system_code,
                "system_name": system_name,
                "cells": cells,
                "latest_tone": "passed",
            }
        )
    return {
        "generated_at": GEN_AT.isoformat(),
        "window": {"days": 7, "slots_per_day": 3, "day_keys": DAY_KEYS},
        "totals": {},
        "columns": [],
        "systems": systems,
    }


class _StubAdminQueries:
    async def get_coverage_dashboard(self, *, system_codes=None) -> dict:
        return _coverage_payload()


class _StubRunQueries:
    async def list_run_summaries_page(self, **kwargs) -> dict:
        return {
            "items": [
                {
                    "run_id": "run_drill_1",
                    "system_code": kwargs.get("system_code", "hom"),
                    "status": "passed",
                    "status_label": "정상",
                    "requested_at": "2026-09-01T13:00:00+09:00",
                    "module_total": 3,
                    "module_passed": 3,
                    "suite_id": None,
                }
            ],
            "total": 1,
            "offset": 0,
            "limit": 200,
        }


def _user() -> User:
    return User(
        user_id="rhist_viewport",
        email="rhist-viewport@test.local",
        name="Runs History Viewport",
        role="user",
        hashed_password="x",
        is_active=True,
        allowed_system_codes=["hom", "mhm"],
        created_at=GEN_AT,
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router)
    app.include_router(runs_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_admin_dashboard_queries] = _StubAdminQueries
    app.dependency_overrides[get_run_queries] = _StubRunQueries
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
        page.goto(f"{live_server}/runs/history", wait_until="networkidle")
        page.wait_for_selector(".rhist-cell")
        return page

    yield create
    for context in contexts:
        context.close()


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_runs_history_does_not_scroll(page_factory, width: int, height: int) -> None:
    page = page_factory(width, height)

    overflow = page.evaluate("() => document.documentElement.scrollHeight - window.innerHeight")
    assert overflow <= 0

    box = page.locator("#rhist-grid").bounding_box()
    assert box is not None
    assert box["y"] + box["height"] <= height


def test_only_drilldown_scrolls(page_factory) -> None:
    page = page_factory(1920, 1080)

    scrollers = page.evaluate(
        """() => Array.from(document.querySelectorAll('.rhist *'))
            .filter((el) => {
              const style = getComputedStyle(el);
              const scrolls = style.overflowY === 'auto' || style.overflowY === 'scroll';
              return scrolls && el.scrollHeight > el.clientHeight + 1;
            })
            .map((el) => el.id || el.className)"""
    )
    assert scrollers in ([], ["rhist-drill"])


def test_not_checked_cell_is_rendered(page_factory) -> None:
    page = page_factory(1920, 1080)

    blanks = page.locator('.rhist-cell[data-tone="not_checked"]').count()
    assert blanks >= 1

    blank_cell = page.locator(f'.rhist-cell[data-system="hom"][data-day="{BLANK_DAY}"]')
    assert blank_cell.get_attribute("data-tone") == "not_checked"


def test_partial_slots_keep_the_running_tone(page_factory) -> None:
    """3슬롯 중 하나만 돌아도 미실행으로 보이면 안 된다(D6 2단계 규칙)."""
    page = page_factory(1920, 1080)

    cell = page.locator('.rhist-cell[data-system="hom"][data-day="2026-09-01"]')
    assert cell.get_attribute("data-tone") == "passed"


def test_cell_click_opens_drilldown(page_factory) -> None:
    page = page_factory(1920, 1080)

    page.locator(".rhist-cell").first.click()
    page.wait_for_selector('.rhist-cell[data-selected="true"]')
    page.wait_for_selector(".rhist-drill__row")

    assert page.locator("#rhist-drill").count() == 1
    assert page.locator('a[href="/runs/run_drill_1"]').count() == 1
