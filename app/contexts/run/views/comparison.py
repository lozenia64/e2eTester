from __future__ import annotations

from typing import Any

from app.storage.query_rows import RunComparisonRow


def comparison_summary_dict(row: RunComparisonRow | None) -> dict[str, Any] | None:
    """목록/드로어용 직전 Run 대비 변화 요약."""
    if row is None:
        return None
    newly_failed = list(row.newly_failed)
    recovered = list(row.recovered)
    still_failing = list(row.still_failing)
    if not row.baseline_run_id and not newly_failed and not recovered and not still_failing:
        return None
    badges: list[str] = []
    if newly_failed:
        badges.append("new_failure")
    if recovered:
        badges.append("recovered")
    if still_failing:
        badges.append("still_failing")
    return {
        "baseline_run_id": row.baseline_run_id,
        "newly_failed": newly_failed,
        "recovered": recovered,
        "still_failing": still_failing,
        "badges": badges,
    }


def attach_comparison(item: dict[str, Any], row: RunComparisonRow | None) -> dict[str, Any]:
    """요약 dict 에 comparison 필드를 붙인다(없으면 생략)."""
    summary = comparison_summary_dict(row)
    if summary is not None:
        item["comparison"] = summary
    return item
