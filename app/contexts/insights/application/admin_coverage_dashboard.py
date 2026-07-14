"""관리자 대시보드 — 최근 7일 × 3타임(주간/저녁/야간) 점검 커버리지 집계기(순수 함수).

KST 기준 하루 3구간(06–18 / 18–22 / 22–06) × 7일 = 21슬롯 매트릭스로
시스템별 점검 여부를 한눈에 본다. I/O 없음 — 단위 테스트 가능.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from app.core.enums import RunStatus
from app.core.status_labels import run_status_badge_tone, run_status_label

if TYPE_CHECKING:
    from app.core.system_models import SystemDefinition

SlotId = Literal["day", "evening", "night"]

WINDOW_DAYS = 7
SLOTS_PER_DAY = 3

_SLOT_LABELS: dict[SlotId, str] = {
    "day": "주간",
    "evening": "저녁",
    "night": "야간",
}
_SLOT_ORDER: tuple[SlotId, ...] = ("day", "evening", "night")
_DOW_LABELS = ["월", "화", "수", "목", "금", "토", "일"]

_TERMINAL_STATUSES = frozenset(
    {
        RunStatus.PASSED,
        RunStatus.ANOMALY,
        RunStatus.ERROR,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }
)
_ACTIVE_STATUSES = frozenset({RunStatus.RUNNING, RunStatus.PENDING, RunStatus.WAITING_INPUT})


@dataclass(frozen=True)
class CoverageRunRow:
    """커버리지 빌더 입력 — ``run_history_index`` 요약 한 행."""

    run_id: str
    system_code: str
    status: RunStatus
    requested_at: datetime


def bucket_run_to_slot(moment: datetime, tz: ZoneInfo) -> tuple[str, SlotId]:
    """KST(또는 스케줄 TZ) 시각을 (day_key, slot_id) 로 귀속한다.

    야간(22–06)은 22시가 속한 날을 앵커 일자로 쓴다 — 03:00 은 전날 야간 슬롯.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    local = aware.astimezone(tz)
    hour = local.hour
    day_key = local.strftime("%Y-%m-%d")

    if hour < 6:
        anchor = (local - timedelta(days=1)).strftime("%Y-%m-%d")
        return anchor, "night"
    if hour < 18:
        return day_key, "day"
    if hour < 22:
        return day_key, "evening"
    return day_key, "night"


def _window_day_keys(now: datetime, tz: ZoneInfo) -> list[str]:
    """오늘 포함 과거 6일 — 총 7일의 day_key 목록(오래된 순)."""
    aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    today = aware.astimezone(tz).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]


def _column_label(day_key: str, slot_id: SlotId, tz: ZoneInfo) -> str:
    dt = datetime.fromisoformat(f"{day_key}T12:00:00").replace(tzinfo=tz)
    dow = _DOW_LABELS[dt.weekday()]
    return f"{dow} {_SLOT_LABELS[slot_id]}"


def _cell_status(runs: list[CoverageRunRow]) -> tuple[str, str | None, str | None, datetime | None]:
    """슬롯 내 Run 목록 → (status_key, status_label, tone, checked_at)."""
    if not runs:
        return "not_checked", "미점검", "not_checked", None

    sorted_runs = sorted(runs, key=lambda row: row.requested_at, reverse=True)
    latest = sorted_runs[0]
    terminal = [row for row in sorted_runs if row.status in _TERMINAL_STATUSES]
    if terminal:
        pick = terminal[0]
        status = pick.status
        if status == RunStatus.FAILED:
            status = RunStatus.ANOMALY
        return (
            str(status),
            run_status_label(status),
            run_status_badge_tone(status),
            pick.requested_at,
        )

    if any(row.status in _ACTIVE_STATUSES for row in sorted_runs):
        return "RUNNING", run_status_label(RunStatus.RUNNING), "running", latest.requested_at

    return "not_checked", "미점검", "not_checked", None


def _row_latest_tone(cells: list[dict[str, Any]]) -> str:
    """행 요약 신호등 — 오늘 슬롯 우선, 없으면 가장 최근 점검 셀."""
    priority = {
        "error": 0,
        "anomaly": 1,
        "running": 2,
        "passed": 3,
        "cancelled": 4,
        "not_checked": 5,
    }
    best = "not_checked"
    best_rank = 99
    for cell in reversed(cells):
        tone = cell.get("tone") or "not_checked"
        rank = priority.get(tone, 6)
        if rank < best_rank:
            best_rank = rank
            best = tone
    return best


def build_admin_coverage_dashboard(
    systems: list[SystemDefinition],
    run_rows: list[CoverageRunRow],
    *,
    now: datetime,
    tz: ZoneInfo,
) -> dict[str, Any]:
    """시스템 × 21슬롯 커버리지 매트릭스를 집계한다."""
    day_keys = _window_day_keys(now, tz)
    window_start_day = day_keys[0]
    tz_aware_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    window_start_local = datetime.fromisoformat(f"{window_start_day}T06:00:00").replace(tzinfo=tz)
    window_start_utc = window_start_local.astimezone(UTC)

    # 슬롯 귀속 후 윈도 밖 Run 은 버린다(쿼리가 넉넉해도 빌더가 최종 필터).
    bucketed: dict[tuple[str, str, SlotId], list[CoverageRunRow]] = {}
    for row in run_rows:
        aware = (
            row.requested_at if row.requested_at.tzinfo else row.requested_at.replace(tzinfo=UTC)
        )
        if aware < window_start_utc:
            continue
        day_key, slot_id = bucket_run_to_slot(row.requested_at, tz)
        if day_key not in day_keys:
            continue
        key = (row.system_code, day_key, slot_id)
        bucketed.setdefault(key, []).append(row)

    columns: list[dict[str, Any]] = []
    for day_key in day_keys:
        for slot_id in _SLOT_ORDER:
            columns.append(
                {
                    "day_key": day_key,
                    "slot_id": slot_id,
                    "label": _column_label(day_key, slot_id, tz),
                }
            )

    system_views: list[dict[str, Any]] = []
    totals_checked = 0
    totals_not_checked = 0
    totals_anomaly = 0
    totals_error = 0
    systems_all_green = 0

    for system in sorted(systems, key=lambda item: item.display_order):
        cells: list[dict[str, Any]] = []
        for day_key in day_keys:
            for slot_id in _SLOT_ORDER:
                slot_runs = bucketed.get((system.system_code, day_key, slot_id), [])
                status_key, status_label, tone, checked_at = _cell_status(slot_runs)
                run_id = None
                if slot_runs:
                    terminal = [
                        row
                        for row in sorted(slot_runs, key=lambda r: r.requested_at, reverse=True)
                        if row.status in _TERMINAL_STATUSES
                    ]
                    pick = terminal[0] if terminal else slot_runs[0]
                    run_id = pick.run_id

                if status_key == "not_checked":
                    totals_not_checked += 1
                else:
                    totals_checked += 1
                if tone == "anomaly":
                    totals_anomaly += 1
                elif tone == "error":
                    totals_error += 1

                cells.append(
                    {
                        "day_key": day_key,
                        "slot_id": slot_id,
                        "status": status_key,
                        "status_label": status_label,
                        "tone": tone,
                        "run_id": run_id,
                        "checked_at": checked_at.isoformat() if checked_at else None,
                    }
                )

        latest_tone = _row_latest_tone(cells)
        if latest_tone == "passed":
            systems_all_green += 1

        system_views.append(
            {
                "system_code": system.system_code,
                "system_name": system.name,
                "cells": cells,
                "latest_tone": latest_tone,
            }
        )

    generated = tz_aware_now.astimezone(UTC)
    return {
        "generated_at": generated.isoformat(),
        "window": {
            "days": WINDOW_DAYS,
            "slots_per_day": SLOTS_PER_DAY,
            "day_keys": day_keys,
            "slot_labels": dict(_SLOT_LABELS),
            "timezone": str(tz),
        },
        "totals": {
            "systems": len(system_views),
            "slots": len(day_keys) * SLOTS_PER_DAY,
            "checked": totals_checked,
            "not_checked": totals_not_checked,
            "anomaly": totals_anomaly,
            "error": totals_error,
            "systems_all_green": systems_all_green,
        },
        "columns": columns,
        "systems": system_views,
    }


def coverage_window_start_utc(now: datetime, tz: ZoneInfo) -> datetime:
    """7일 커버리지 쿼리용 하한(첫날 06:00 KST → UTC)."""
    day_keys = _window_day_keys(now, tz)
    window_start_local = datetime.fromisoformat(f"{day_keys[0]}T06:00:00").replace(tzinfo=tz)
    return window_start_local.astimezone(UTC)
