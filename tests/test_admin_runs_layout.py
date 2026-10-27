"""관리자 Run 이력 레이아웃 계약 — 시스템 지도 리뉴얼(대시보드 중복 영역 삭제)."""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path("app/web/templates/admin/runs.html").read_text(encoding="utf-8")
SCRIPT = Path("app/web/static/admin-runs.js").read_text(encoding="utf-8")


def test_admin_runs_template_has_system_map_and_no_duplicates() -> None:
    for marker in ('id="runs-system-map-chart"', 'id="runs-system-map-summary"', 'id="runs-explore"'):
        assert marker in TEMPLATE
    for removed in (
        "runs-kpi-grid",
        "runs-trend-canvas",
        "runs-attention-list",
        "runs-system-recent",
        "vendor-chart.ts",
    ):
        assert removed not in TEMPLATE


def test_admin_runs_script_draws_treemap_without_removed_panels() -> None:
    assert "treemap" in SCRIPT
    for removed in ("renderKpis", "renderTrend", "renderAttention", "renderSystemRecent", "boardRunStub"):
        assert removed not in SCRIPT
