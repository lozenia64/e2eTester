"""Plotly 차트 빌더 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.stats_models import SystemUsageStat, UsageStats, UserUsageStat
from app.orchestrator.stats_charts import build_usage_charts


def _usage_stats() -> UsageStats:
    return UsageStats(
        period_from=None,
        period_to=None,
        generated_at=datetime.now(UTC),
        total_runs=3,
        total_users=1,
        by_user=[
            UserUsageStat(
                user_id="u1",
                user_name="테스트",
                email=None,
                total_runs=3,
                total_modules_passed=6,
                total_modules_failed=1,
                total_duration_ms=120_000,
                manual_seconds_saved=300,
                by_system=[],
            ),
        ],
        by_system=[
            SystemUsageStat(
                system_code="hom",
                system_name="대표홈페이지(PC)",
                runs=2,
                modules_passed=4,
                modules_failed=1,
                total_duration_ms=80_000,
                manual_seconds_saved=200,
            ),
            SystemUsageStat(
                system_code="mhm",
                system_name="대표홈페이지(모바일)",
                runs=1,
                modules_passed=2,
                modules_failed=0,
                total_duration_ms=40_000,
                manual_seconds_saved=100,
            ),
        ],
    )


def test_build_usage_charts_returns_four_plotly_figures():
    charts = build_usage_charts(_usage_stats())

    assert set(charts.keys()) == {
        "chart-system-runs",
        "chart-user-runs",
        "chart-system-savings",
        "chart-module-pass-fail",
    }
    for figure in charts.values():
        assert "data" in figure
        assert "layout" in figure
        assert figure["data"]


def test_build_usage_charts_empty_data_uses_annotations():
    empty = UsageStats(
        period_from=None,
        period_to=None,
        generated_at=datetime.now(UTC),
        total_runs=0,
        total_users=0,
        by_user=[],
        by_system=[],
    )
    charts = build_usage_charts(empty)

    for figure in charts.values():
        annotations = figure["layout"].get("annotations", [])
        assert any(a.get("text") == "표시할 데이터가 없습니다." for a in annotations)
