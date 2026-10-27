"""관리자 Run 이력 보드 — 이번 달 시스템 지도 집계(순수 함수).

입력은 ``run_history_index`` 에서 미리 조회한 시스템×상태 집계뿐이다. I/O 없음.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.status_labels import RUN_ANOMALY_STATUSES

_ANOMALY_VALUES = frozenset(status.value for status in RUN_ANOMALY_STATUSES)


def _top(systems: list[dict[str, Any]], key: str) -> str | None:
    """``key`` 최댓값 시스템 코드 — 동률은 코드 오름차순, 전부 0이면 None."""
    best = min(systems, key=lambda s: (-s[key], s["system_code"]), default=None)
    return best["system_code"] if best and best[key] > 0 else None


def build_system_map(
    counts: list[tuple[str, str, str, int]],
    *,
    period_from: datetime,
    period_to: datetime,
) -> dict[str, Any]:
    """(system_code, system_name, status, count) → 트리맵용 시스템별 실행·이상징후 수."""
    by_code: dict[str, dict[str, Any]] = {}
    for code, name, status, count in counts:
        item = by_code.setdefault(
            code, {"system_code": code, "system_name": name, "runs": 0, "anomaly": 0}
        )
        item["runs"] += count
        if status in _ANOMALY_VALUES:
            item["anomaly"] += count
    systems = sorted(by_code.values(), key=lambda s: (-s["runs"], s["system_code"]))
    return {
        "period": {"from": period_from.isoformat(), "to": period_to.isoformat()},
        "systems": systems,
        "top_runs": _top(systems, "runs"),
        "top_anomaly": _top(systems, "anomaly"),
    }


def build_admin_run_history_board(
    *,
    now: datetime,
    tz: ZoneInfo,
    today_start: datetime,
    system_map: dict[str, Any],
) -> dict[str, Any]:
    """관리자 Run 이력 상단 보드 페이로드."""
    return {
        "generated_at": now.isoformat(),
        "timezone": str(tz),
        "today_start": today_start.isoformat(),
        "system_map": system_map,
    }
