"""관리자 Run 이력 히트맵 빌더 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from app.contexts.insights.application.admin_run_history_heatmap import (
    HeatmapRunRow,
    build_user_system_heatmap,
)
from app.core.enums import RunStatus

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def test_build_user_system_heatmap_uses_latest_run_per_cell() -> None:
    rows = [
        HeatmapRunRow(
            system_code="hom",
            system_name="HOM",
            status=RunStatus.PASSED,
            requested_at=NOW,
            created_by_user_id="u1",
            created_by_user_name="Alice",
        ),
        HeatmapRunRow(
            system_code="hom",
            system_name="HOM",
            status=RunStatus.ANOMALY,
            requested_at=NOW.replace(hour=13),
            created_by_user_id="u1",
            created_by_user_name="Alice",
        ),
        HeatmapRunRow(
            system_code="mhm",
            system_name="MHM",
            status=RunStatus.PASSED,
            requested_at=NOW,
            created_by_user_id="u1",
            created_by_user_name="Alice",
        ),
    ]
    payload = build_user_system_heatmap(rows, [("hom", "HOM"), ("mhm", "MHM")])
    assert payload["users"] == ["Alice"]
    assert payload["matrix"] == [[1, 0]]


def test_build_user_system_heatmap_empty_matrix() -> None:
    payload = build_user_system_heatmap([], [("hom", "HOM")])
    assert payload["users"] == []
    assert payload["matrix"] == []
