"""관리자 Run 이력 — 실행자×시스템 히트맵 집계기(순수 함수).

최근 7일 완료 Run 을 (실행자, 시스템) 셀별 최신 상태로 매핑해 ECharts heatmap 페이로드를 만든다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label

_TERMINAL = frozenset(
    {
        RunStatus.PASSED,
        RunStatus.ANOMALY,
        RunStatus.ERROR,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }
)

_STATUS_VALUE: dict[RunStatus, int] = {
    RunStatus.PASSED: 0,
    RunStatus.ANOMALY: 1,
    RunStatus.FAILED: 1,
    RunStatus.ERROR: 2,
    RunStatus.CANCELLED: 3,
}


@dataclass(frozen=True)
class HeatmapRunRow:
    """히트맵 입력 — ``run_history_index`` 요약 한 행."""

    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    created_by_user_id: str | None
    created_by_user_name: str | None

    @property
    def user_key(self) -> str:
        return self.created_by_user_id or self.created_by_user_name or "(시스템)"

    @property
    def user_label(self) -> str:
        return self.created_by_user_name or "(시스템)"


def _status_value(status: RunStatus) -> int:
    return _STATUS_VALUE.get(status, -1)


def build_user_system_heatmap(
    rows: list[HeatmapRunRow],
    systems: list[tuple[str, str]],
    *,
    max_users: int = 12,
) -> dict[str, Any]:
    """실행자(행) × 시스템(열) 최신 Run 상태 히트맵."""
    terminal_rows = [row for row in rows if row.status in _TERMINAL]
    latest: dict[tuple[str, str], HeatmapRunRow] = {}
    for row in terminal_rows:
        pair = (row.user_key, row.system_code)
        prev = latest.get(pair)
        if prev is None or row.requested_at > prev.requested_at:
            latest[pair] = row

    user_labels: dict[str, str] = {}
    for row in terminal_rows:
        user_labels[row.user_key] = row.user_label

    user_counts = Counter(row.user_key for row in terminal_rows)
    users = sorted(user_counts.keys(), key=lambda key: (-user_counts[key], key))[:max_users]

    system_codes = [code for code, _ in systems]
    system_names = dict(systems)

    matrix: list[list[int]] = []
    cells: list[list[Any]] = []
    for user_key in users:
        row_values: list[int] = []
        for system_code in system_codes:
            cell = latest.get((user_key, system_code))
            value = _status_value(cell.status) if cell is not None else -1
            row_values.append(value)
            if cell is not None:
                cells.append(
                    {
                        "user": user_labels.get(user_key, user_key),
                        "system_code": system_code,
                        "system_name": system_names.get(system_code, system_code),
                        "status": cell.status.value,
                        "status_label": run_status_label(cell.status),
                        "value": value,
                    }
                )
        matrix.append(row_values)

    return {
        "users": [user_labels.get(key, key) for key in users],
        "systems": [system_names.get(code, code.upper()) for code in system_codes],
        "system_codes": system_codes,
        "matrix": matrix,
        "cells": cells,
        "legend": [
            {"value": -1, "label": "없음", "color": "#f3f4f6"},
            {"value": 0, "label": "정상", "color": "#0ca30c"},
            {"value": 1, "label": "이상징후", "color": "#fab219"},
            {"value": 2, "label": "점검실패", "color": "#d03b3b"},
            {"value": 3, "label": "취소", "color": "#9ca3af"},
        ],
    }
