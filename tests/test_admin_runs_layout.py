"""관리자 Run 이력 레이아웃 계약 — 시스템 지도 리뉴얼(대시보드 중복 영역 삭제)."""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path("app/web/templates/admin/runs.html").read_text(encoding="utf-8")
SCRIPT = Path("app/web/static/admin-runs.js").read_text(encoding="utf-8")


def test_admin_runs_template_has_system_map_and_no_duplicates() -> None:
    for marker in (
        'id="runs-system-map-chart"',
        'id="runs-system-map-summary"',
        'id="runs-explore"',
    ):
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
    for removed in (
        "renderKpis",
        "renderTrend",
        "renderAttention",
        "renderSystemRecent",
        "boardRunStub",
    ):
        assert removed not in SCRIPT


def _function_body(name: str) -> str:
    start = SCRIPT.index(f"function {name}(")
    return SCRIPT[start : SCRIPT.index("\n  }\n", start)]


def test_tile_click_has_no_upper_bound_so_list_matches_tile() -> None:
    """`to` 는 분 단위로 잘려 그 분의 Run 이 목록에서 빠진다 — 월초 하한만 건다."""
    body = _function_body("focusExploreOnSystem")
    assert "from: period.from" in body
    assert "to:" not in body


def test_tile_click_registers_unlisted_system_in_filter() -> None:
    """레지스트리에서 빠진 시스템도 필터 체크박스가 있어야 필터가 조용히 사라지지 않는다."""
    assert "ensureSystemFilterOption(" in _function_body("focusExploreOnSystem")
