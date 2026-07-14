"""관리자 커버리지 대시보드 빌더 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.contexts.insights.application.admin_coverage_dashboard import (
    CoverageRunRow,
    bucket_run_to_slot,
    build_admin_coverage_dashboard,
    coverage_window_start_utc,
)
from app.core.enums import RunStatus
from app.core.system_models import SystemDefinition

KST = ZoneInfo("Asia/Seoul")
GEN_AT = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)  # KST 2026-07-15 00:00


def _dt_kst(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=KST).astimezone(UTC)


def _system(code: str, name: str) -> SystemDefinition:
    return SystemDefinition(
        system_code=code,
        name=name,
        description="",
        display_order=0,
        modules=[],
        run_form=[],
        supported_auth_methods=[],
    )


@pytest.mark.parametrize(
    ("moment", "expected_day", "expected_slot"),
    [
        (_dt_kst(2026, 7, 14, 5, 59), "2026-07-13", "night"),
        (_dt_kst(2026, 7, 14, 6, 0), "2026-07-14", "day"),
        (_dt_kst(2026, 7, 14, 17, 59), "2026-07-14", "day"),
        (_dt_kst(2026, 7, 14, 18, 0), "2026-07-14", "evening"),
        (_dt_kst(2026, 7, 14, 21, 59), "2026-07-14", "evening"),
        (_dt_kst(2026, 7, 14, 22, 0), "2026-07-14", "night"),
        (_dt_kst(2026, 7, 15, 3, 0), "2026-07-14", "night"),
    ],
)
def test_bucket_run_to_slot_boundaries(
    moment: datetime, expected_day: str, expected_slot: str
) -> None:
    day_key, slot_id = bucket_run_to_slot(moment, KST)
    assert day_key == expected_day
    assert slot_id == expected_slot


def test_build_coverage_empty_slots() -> None:
    systems = [_system("hom", "HOM")]
    data = build_admin_coverage_dashboard(systems, [], now=GEN_AT, tz=KST)
    assert data["totals"]["systems"] == 1
    assert data["totals"]["slots"] == 21
    assert data["totals"]["not_checked"] == 21
    assert data["systems"][0]["cells"][0]["status"] == "not_checked"


def test_build_coverage_picks_latest_terminal_in_slot() -> None:
    systems = [_system("hom", "HOM")]
    day = "2026-07-14"
    runs = [
        CoverageRunRow("r1", "hom", RunStatus.PASSED, _dt_kst(2026, 7, 14, 10, 0)),
        CoverageRunRow("r2", "hom", RunStatus.ANOMALY, _dt_kst(2026, 7, 14, 11, 0)),
    ]
    data = build_admin_coverage_dashboard(systems, runs, now=GEN_AT, tz=KST)
    day_cell = next(
        cell
        for cell in data["systems"][0]["cells"]
        if cell["day_key"] == day and cell["slot_id"] == "day"
    )
    assert day_cell["status"] == "ANOMALY"
    assert day_cell["run_id"] == "r2"


def test_build_coverage_running_when_no_terminal() -> None:
    systems = [_system("hom", "HOM")]
    runs = [CoverageRunRow("r1", "hom", RunStatus.RUNNING, _dt_kst(2026, 7, 14, 10, 0))]
    data = build_admin_coverage_dashboard(systems, runs, now=GEN_AT, tz=KST)
    day_cell = next(
        c
        for c in data["systems"][0]["cells"]
        if c["slot_id"] == "day" and c["day_key"] == "2026-07-14"
    )
    assert day_cell["status"] == "RUNNING"
    assert day_cell["tone"] == "running"


def test_coverage_window_start_is_first_day_06_kst() -> None:
    start = coverage_window_start_utc(GEN_AT, KST)
    # GEN_AT = KST 2026-07-15 00:00 → 7-day window starts 2026-07-09 06:00 KST
    assert start == datetime(2026, 7, 8, 21, 0, tzinfo=UTC)
