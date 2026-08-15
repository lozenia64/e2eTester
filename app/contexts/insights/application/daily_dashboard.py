"""사용자 대시보드 — 일간 점검 현황 집계기(순수 함수).

로그인한 사용자가 접근 가능한 각 시스템의 **오늘(KST) 점검 결과**를 시스템·모듈 단위로
한눈에 볼 수 있도록 집계한다. 시스템별로 오늘 실행된 Run 들을 모아, 모듈마다 가장 최근의
'의미 있는' 상태(제외/미도달 제외)를 골라 일간 현황을 만든다.

I/O 없는 순수 함수라 브라우저·DB 없이 단위 테스트할 수 있다(집계 규칙만 담당).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.core.enums import ModuleStatus
from app.core.status_labels import (
    MODULE_ANOMALY_STATUSES,
    MODULE_ERROR_STATUSES,
    module_status_badge_tone,
    module_status_label,
    run_status_badge_tone,
    run_status_label,
)

if TYPE_CHECKING:
    from app.contexts.insights.contracts.query_rows import DailyRunSummaryRow, DailyStatusRow
    from app.core.run_models import Run, RunModule
    from app.core.system_models import SystemDefinition

# 모듈의 '오늘 점검 결과'로 채택하지 않는 상태(아직 도달 못 했거나 대상에서 제외).
# 이 상태는 더 오래된 Run 쪽으로 계속 탐색한다.
_NON_RESULT_STATUSES = frozenset({ModuleStatus.PENDING, ModuleStatus.QUEUED, ModuleStatus.SKIPPED})


def _module_bucket(status: ModuleStatus | None) -> str:
    """시스템 요약 카운트를 위한 대분류 버킷."""
    if status is None:
        return "not_inspected"
    if status == ModuleStatus.PASSED:
        return "passed"
    if status in MODULE_ANOMALY_STATUSES:
        return "anomaly"
    if status in MODULE_ERROR_STATUSES:
        return "error"
    if status in {ModuleStatus.RUNNING, ModuleStatus.WAITING_INPUT}:
        return "running"
    return "other"  # BLOCKED / CANCELLED


# 주의 큐·정렬용 버킷 우선순위(높을수록 먼저 노출).
_ATTENTION_RANK = {
    "error": 50,
    "anomaly": 40,
    "running": 30,
    "other": 20,
    "not_inspected": 10,
    "passed": 0,
}


def system_attention_rank(counts: dict[str, int], *, module_total: int) -> int:
    """시스템 단위 주의 등급 — error > anomaly > running > other > 미점검 > 전체정상."""
    if module_total == 0:
        return 0
    if counts.get("error", 0) > 0:
        return _ATTENTION_RANK["error"]
    if counts.get("anomaly", 0) > 0:
        return _ATTENTION_RANK["anomaly"]
    if counts.get("running", 0) > 0:
        return _ATTENTION_RANK["running"]
    if counts.get("other", 0) > 0:
        return _ATTENTION_RANK["other"]
    if counts.get("not_inspected", 0) > 0:
        return _ATTENTION_RANK["not_inspected"]
    return _ATTENTION_RANK["passed"]


def sort_systems_attention_first(system_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """주의 등급 내림차순, 동률이면 display_order."""
    return sorted(
        system_views,
        key=lambda s: (
            -system_attention_rank(s["counts"], module_total=s["module_total"]),
            s.get("display_order", 0),
        ),
    )


def system_summary_badge(system_view: dict[str, Any]) -> dict[str, str]:
    counts = system_view.get("counts") or {}
    total = system_view.get("module_total") or 0
    if counts.get("error", 0) > 0:
        return {"label": "점검실패", "tone": "error"}
    if counts.get("anomaly", 0) > 0:
        return {"label": "이상징후", "tone": "anomaly"}
    if counts.get("running", 0) > 0:
        return {"label": "진행 중", "tone": "running"}
    if counts.get("other", 0) > 0:
        return {"label": "주의", "tone": "blocked"}
    if counts.get("not_inspected", 0) > 0:
        return {"label": "미점검", "tone": "not_inspected"}
    if total > 0 and counts.get("passed", 0) == total:
        return {"label": "정상", "tone": "passed"}
    return {"label": "미점검", "tone": "not_inspected"}


_MODULE_ATTENTION_BUCKETS = frozenset({"error", "anomaly", "running"})


def build_attention_items(system_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Zone C 주의 스트립 — 문제 모듈·미점검 시스템(PII 없음)."""
    items: list[dict[str, Any]] = []
    for sys in system_views:
        for mod in sys.get("modules", []):
            if mod["bucket"] not in _MODULE_ATTENTION_BUCKETS:
                continue
            items.append(
                {
                    "kind": "module",
                    "system_code": sys["system_code"],
                    "system_name": sys.get("system_name", sys["system_code"]),
                    "module_id": mod["module_id"],
                    "module_name": mod["name"],
                    "status_label": mod["status_label"],
                    "tone": mod["tone"],
                    "run_id": mod["run_id"] or sys.get("latest_run_id"),
                    "rank": _ATTENTION_RANK.get(mod["bucket"], 0),
                }
            )
        if sys["counts"].get("not_inspected", 0) > 0 and not any(
            m["bucket"] in _MODULE_ATTENTION_BUCKETS for m in sys.get("modules", [])
        ):
            items.append(
                {
                    "kind": "system",
                    "system_code": sys["system_code"],
                    "system_name": sys.get("system_name", sys["system_code"]),
                    "module_id": None,
                    "module_name": None,
                    "status_label": f"미점검 {sys['counts']['not_inspected']}개",
                    "tone": "not_inspected",
                    "run_id": sys.get("latest_run_id"),
                    "rank": _ATTENTION_RANK["not_inspected"],
                }
            )
    items.sort(key=lambda it: (-it["rank"], it["system_name"], it["module_name"] or ""))
    return items


def _pick_module_status(
    module_id: str, system_runs: list[Run]
) -> tuple[ModuleStatus | None, str | None, int | None]:
    """오늘 실행된 Run 들(최신순) 중 해당 모듈의 가장 최근 '의미 있는' 상태를 고른다.

    반환: (status, run_id, duration_ms). 오늘 점검 결과가 없으면 (None, None, None).
    """
    for run in system_runs:
        for module in run.modules:
            if module.module_id != module_id:
                continue
            if module.status in _NON_RESULT_STATUSES:
                continue
            return module.status, run.run_id, module.duration_ms
    return None, None, None


def _module_view(module: RunModule | Any, system_runs: list[Run]) -> dict[str, Any]:
    status, run_id, duration_ms = _pick_module_status(module.module_id, system_runs)
    tone = module_status_badge_tone(status) if status is not None else "not_inspected"
    label = module_status_label(status) if status is not None else "미점검"
    return {
        "module_id": module.module_id,
        "name": module.name,
        "group": module.group,
        "order": module.order,
        "status": str(status) if status is not None else None,
        "status_label": label,
        "tone": tone,
        "bucket": _module_bucket(status),
        "run_id": run_id,
        "duration_ms": duration_ms,
    }


def _system_view(system: SystemDefinition, system_runs: list[Run]) -> dict[str, Any]:
    modules = sorted(system.modules, key=lambda m: m.order)
    module_views = [_module_view(m, system_runs) for m in modules]

    counts = {
        "passed": 0,
        "anomaly": 0,
        "error": 0,
        "running": 0,
        "other": 0,
        "not_inspected": 0,
    }
    for view in module_views:
        counts[view["bucket"]] += 1

    module_total = len(module_views)
    inspected = module_total - counts["not_inspected"]
    pass_rate = round(counts["passed"] / module_total * 100) if module_total else 0

    latest_run = system_runs[0] if system_runs else None

    return {
        "system_code": system.system_code,
        "system_name": system.name,
        "display_order": system.display_order,
        "module_total": module_total,
        "inspected": inspected,
        "pass_rate": pass_rate,
        "counts": counts,
        "latest_run_id": latest_run.run_id if latest_run else None,
        "latest_run_at": (latest_run.requested_at.isoformat() if latest_run else None),
        "latest_run_status": str(latest_run.status) if latest_run else None,
        "latest_run_status_label": (
            run_status_label(latest_run.status) if latest_run else "미점검"
        ),
        "latest_run_tone": (
            run_status_badge_tone(latest_run.status) if latest_run else "not_inspected"
        ),
        "triggered_by": latest_run.triggered_by if latest_run else None,
        "modules": module_views,
    }


def build_daily_dashboard(
    systems: list[SystemDefinition],
    today_runs: list[Run],
    *,
    generated_at: datetime,
    date_label: str,
) -> dict[str, Any]:
    """접근 가능한 시스템별 일간 점검 현황을 집계한다.

    ``today_runs`` 는 KST '오늘' 요청된 Run 목록(어떤 트리거든 무관). 시스템별로 최신순
    정렬해 모듈 상태를 매핑한다. ``systems`` 는 이미 사용자 권한으로 필터링된 목록을 받는다.
    """
    runs_by_system: dict[str, list[Run]] = {}
    for run in today_runs:
        runs_by_system.setdefault(run.system_code, []).append(run)
    for run_list in runs_by_system.values():
        run_list.sort(key=lambda r: r.requested_at, reverse=True)

    system_views = sort_systems_attention_first(
        [
            _system_view(system, runs_by_system.get(system.system_code, []))
            for system in sorted(systems, key=lambda s: s.display_order)
        ]
    )

    totals = {
        "systems": len(system_views),
        "modules": sum(v["module_total"] for v in system_views),
        "inspected": sum(v["inspected"] for v in system_views),
        "passed": sum(v["counts"]["passed"] for v in system_views),
        "anomaly": sum(v["counts"]["anomaly"] for v in system_views),
        "error": sum(v["counts"]["error"] for v in system_views),
        "running": sum(v["counts"]["running"] for v in system_views),
        "other": sum(v["counts"]["other"] for v in system_views),
        "not_inspected": sum(v["counts"]["not_inspected"] for v in system_views),
    }
    totals["pass_rate"] = (
        round(totals["passed"] / totals["modules"] * 100) if totals["modules"] else 0
    )
    totals["systems_all_passed"] = sum(
        1
        for v in system_views
        if v["module_total"] > 0 and v["counts"]["passed"] == v["module_total"]
    )

    return {
        "generated_at": generated_at.isoformat(),
        "date_label": date_label,
        "totals": totals,
        "systems": system_views,
        "attention": build_attention_items(system_views),
    }


def _module_view_from_row(
    module: RunModule | Any,
    *,
    status_row: DailyStatusRow | None,
    duration_ms: int | None,
) -> dict[str, Any]:
    status = status_row.last_status if status_row is not None else None
    run_id = status_row.last_run_id if status_row is not None else None
    if status in _NON_RESULT_STATUSES:
        status = None
        run_id = None
        duration_ms = None
    tone = module_status_badge_tone(status) if status is not None else "not_inspected"
    label = module_status_label(status) if status is not None else "미점검"
    return {
        "module_id": module.module_id,
        "name": module.name,
        "group": module.group,
        "order": module.order,
        "status": str(status) if status is not None else None,
        "status_label": label,
        "tone": tone,
        "bucket": _module_bucket(status),
        "run_id": run_id,
        "duration_ms": duration_ms,
    }


def _system_view_from_projection(
    system: SystemDefinition,
    status_rows: dict[str, DailyStatusRow],
    run_summaries: list[DailyRunSummaryRow],
    *,
    duration_by_module_run: dict[tuple[str, str], int | None],
) -> dict[str, Any]:
    modules = sorted(system.modules, key=lambda m: m.order)
    module_views = [
        _module_view_from_row(
            module,
            status_row=status_rows.get(module.module_id),
            duration_ms=(
                duration_by_module_run.get(
                    (
                        status_rows[module.module_id].last_run_id or "",
                        module.module_id,
                    )
                )
                if module.module_id in status_rows and status_rows[module.module_id].last_run_id
                else None
            ),
        )
        for module in modules
    ]

    counts = {
        "passed": 0,
        "anomaly": 0,
        "error": 0,
        "running": 0,
        "other": 0,
        "not_inspected": 0,
    }
    for view in module_views:
        counts[view["bucket"]] += 1

    module_total = len(module_views)
    inspected = module_total - counts["not_inspected"]
    pass_rate = round(counts["passed"] / module_total * 100) if module_total else 0

    latest = run_summaries[0] if run_summaries else None

    return {
        "system_code": system.system_code,
        "system_name": system.name,
        "display_order": system.display_order,
        "module_total": module_total,
        "inspected": inspected,
        "pass_rate": pass_rate,
        "counts": counts,
        "latest_run_id": latest.run_id if latest else None,
        "latest_run_at": latest.requested_at.isoformat() if latest else None,
        "latest_run_status": str(latest.status) if latest else None,
        "latest_run_status_label": (run_status_label(latest.status) if latest else "미점검"),
        "latest_run_tone": (run_status_badge_tone(latest.status) if latest else "not_inspected"),
        "triggered_by": latest.triggered_by if latest else None,
        "modules": module_views,
    }


def build_daily_dashboard_from_projection(
    systems: list[SystemDefinition],
    status_rows: list[DailyStatusRow],
    run_summaries: list[DailyRunSummaryRow],
    *,
    duration_by_module_run: dict[tuple[str, str], int | None] | None = None,
    generated_at: datetime,
    date_label: str,
) -> dict[str, Any]:
    """``daily_system_status`` 프로젝션 + 당일 Run 요약으로 일간 현황을 집계한다."""
    durations = duration_by_module_run or {}
    status_by_system: dict[str, dict[str, DailyStatusRow]] = {}
    for row in status_rows:
        status_by_system.setdefault(row.system_code, {})[row.module_id] = row

    summaries_by_system: dict[str, list[DailyRunSummaryRow]] = {}
    for summary in run_summaries:
        summaries_by_system.setdefault(summary.system_code, []).append(summary)
    for summary_list in summaries_by_system.values():
        summary_list.sort(key=lambda item: item.requested_at, reverse=True)

    system_views = sort_systems_attention_first(
        [
            _system_view_from_projection(
                system,
                status_by_system.get(system.system_code, {}),
                summaries_by_system.get(system.system_code, []),
                duration_by_module_run=durations,
            )
            for system in sorted(systems, key=lambda s: s.display_order)
        ]
    )

    totals = {
        "systems": len(system_views),
        "modules": sum(v["module_total"] for v in system_views),
        "inspected": sum(v["inspected"] for v in system_views),
        "passed": sum(v["counts"]["passed"] for v in system_views),
        "anomaly": sum(v["counts"]["anomaly"] for v in system_views),
        "error": sum(v["counts"]["error"] for v in system_views),
        "running": sum(v["counts"]["running"] for v in system_views),
        "other": sum(v["counts"]["other"] for v in system_views),
        "not_inspected": sum(v["counts"]["not_inspected"] for v in system_views),
    }
    totals["pass_rate"] = (
        round(totals["passed"] / totals["modules"] * 100) if totals["modules"] else 0
    )
    totals["systems_all_passed"] = sum(
        1
        for v in system_views
        if v["module_total"] > 0 and v["counts"]["passed"] == v["module_total"]
    )

    return {
        "generated_at": generated_at.isoformat(),
        "date_label": date_label,
        "totals": totals,
        "systems": system_views,
        "attention": build_attention_items(system_views),
    }
