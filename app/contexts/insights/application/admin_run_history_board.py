"""관리자 Run 이력 보드 — KPI·7일 추이·주의 Run 집계(순수 함수).

입력은 ``run_history_index`` 에서 미리 조회한 행·집계뿐이다. I/O 없음.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label

ATTENTION_STATUSES = frozenset({RunStatus.ANOMALY, RunStatus.ERROR, RunStatus.FAILED})
DASHBOARD_TERMINAL = frozenset(
    {
        RunStatus.PASSED,
        RunStatus.ANOMALY,
        RunStatus.ERROR,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }
)

TrendStatus = Literal["passed", "anomaly", "error", "cancelled"]


@dataclass(frozen=True)
class BoardRunRow:
    """보드 빌더용 Run 요약 한 행."""

    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    module_total: int
    module_passed: int
    module_skipped: int
    failed_module_name: str | None
    triggered_by: str
    suite_id: str | None
    schedule_id: str | None
    created_by_user_name: str | None


def _local_day_key(moment: datetime, tz: ZoneInfo) -> str:
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(tz).strftime("%Y-%m-%d")


def _window_day_keys(now: datetime, tz: ZoneInfo, days: int = 7) -> list[str]:
    aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    today = aware.astimezone(tz).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


def _status_to_trend_key(status: RunStatus) -> TrendStatus | None:
    if status == RunStatus.PASSED:
        return "passed"
    if status in {RunStatus.ANOMALY, RunStatus.FAILED}:
        return "anomaly"
    if status == RunStatus.ERROR:
        return "error"
    if status == RunStatus.CANCELLED:
        return "cancelled"
    return None


def build_trend_7d(
    counts_by_day: dict[str, dict[str, int]],
    *,
    now: datetime,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """7일 슬롯을 0으로 채운 뒤 집계를 병합한다."""
    trend: list[dict[str, Any]] = []
    for day_key in _window_day_keys(now, tz):
        bucket = counts_by_day.get(day_key, {})
        trend.append(
            {
                "day": day_key,
                "passed": bucket.get("passed", 0),
                "anomaly": bucket.get("anomaly", 0),
                "error": bucket.get("error", 0),
                "cancelled": bucket.get("cancelled", 0),
            }
        )
    return trend


def merge_daily_status_counts(
    raw: list[tuple[str, str, int]],
) -> dict[str, dict[str, int]]:
    """(day_key, status_value, count) 목록 → trend 키별 집계."""
    result: dict[str, dict[str, int]] = {}
    for day_key, status_value, count in raw:
        try:
            status = RunStatus(status_value)
        except ValueError:
            continue
        trend_key = _status_to_trend_key(status)
        if trend_key is None:
            continue
        result.setdefault(day_key, {})
        result[day_key][trend_key] = result[day_key].get(trend_key, 0) + count
    return result


def build_by_system_recent(rows: list[BoardRunRow]) -> list[dict[str, Any]]:
    """시스템별 가장 최근 완료 Run 한 건."""
    latest: dict[str, BoardRunRow] = {}
    for row in sorted(rows, key=lambda item: item.requested_at, reverse=True):
        if row.system_code not in latest:
            latest[row.system_code] = row
    items = sorted(latest.values(), key=lambda item: item.system_code)
    return [
        {
            "system_code": row.system_code,
            "system_name": row.system_name,
            "last_status": row.status.value,
            "last_status_label": run_status_label(row.status),
            "last_at": (row.ended_at or row.requested_at).isoformat(),
            "run_id": row.run_id,
        }
        for row in items
    ]


def summarize_attention_row(row: BoardRunRow) -> dict[str, Any]:
    duration_sec = None
    if row.started_at and row.ended_at:
        duration_sec = max(0, int((row.ended_at - row.started_at).total_seconds()))
    return {
        "run_id": row.run_id,
        "system_code": row.system_code,
        "system_name": row.system_name,
        "status": row.status.value,
        "status_label": run_status_label(row.status),
        "requested_at": row.requested_at.isoformat(),
        "failed_module_name": row.failed_module_name,
        "module_passed": row.module_passed,
        "module_total": row.module_total,
        "triggered_by": row.triggered_by,
        "suite_id": row.suite_id,
        "created_by_user_name": row.created_by_user_name,
        "duration_seconds": duration_sec,
    }


def build_admin_run_history_board(
    *,
    now: datetime,
    tz: ZoneInfo,
    today_start: datetime,
    total_finished: int,
    today_status_counts: dict[str, int],
    trend_counts_raw: list[tuple[str, str, int]],
    attention_rows: list[BoardRunRow],
    by_system_recent_rows: list[BoardRunRow],
    attention_open_count: int,
) -> dict[str, Any]:
    """관리자 Run 이력 상단 보드 페이로드."""
    today_finished = sum(today_status_counts.get(status.value, 0) for status in DASHBOARD_TERMINAL)
    trend = build_trend_7d(merge_daily_status_counts(trend_counts_raw), now=now, tz=tz)
    attention = [summarize_attention_row(row) for row in attention_rows]
    return {
        "generated_at": now.isoformat(),
        "timezone": str(tz),
        "today_start": today_start.isoformat(),
        "kpis": {
            "total_finished": total_finished,
            "today_finished": today_finished,
            "today_passed": today_status_counts.get(RunStatus.PASSED.value, 0),
            "today_anomaly": today_status_counts.get(RunStatus.ANOMALY.value, 0)
            + today_status_counts.get(RunStatus.FAILED.value, 0),
            "today_error": today_status_counts.get(RunStatus.ERROR.value, 0),
            "today_cancelled": today_status_counts.get(RunStatus.CANCELLED.value, 0),
            "attention_open": attention_open_count,
        },
        "trend_7d": trend,
        "by_system_recent": build_by_system_recent(by_system_recent_rows),
        "attention_runs": attention,
    }
