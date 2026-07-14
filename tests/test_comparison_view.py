"""Run comparison 요약 뷰 단위 테스트."""

from __future__ import annotations

from app.contexts.run.views.comparison import attach_comparison, comparison_summary_dict
from app.storage.query_rows import RunComparisonRow


def test_comparison_summary_dict_new_failure_badge() -> None:
    row = RunComparisonRow(
        run_id="run_1",
        baseline_run_id="run_0",
        newly_failed=("로그인",),
        recovered=(),
        still_failing=(),
    )
    summary = comparison_summary_dict(row)
    assert summary is not None
    assert summary["badges"] == ["new_failure"]
    assert summary["newly_failed"] == ["로그인"]


def test_comparison_summary_dict_still_failing_badge() -> None:
    row = RunComparisonRow(
        run_id="run_1",
        baseline_run_id="run_0",
        newly_failed=(),
        recovered=(),
        still_failing=("로그인",),
    )
    summary = comparison_summary_dict(row)
    assert summary is not None
    assert summary["badges"] == ["still_failing"]
    assert summary["still_failing"] == ["로그인"]


def test_attach_comparison_skips_empty() -> None:
    item = {"run_id": "run_1"}
    attach_comparison(item, None)
    assert "comparison" not in item
