"""관리자 월간 성과 집계. 한국 달력 기준, I/O 없는 읽기 모델 빌더."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from app.contexts.insights.application.savings_basis import saved_module_seconds
from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES

if TYPE_CHECKING:
    from app.contexts.run.contracts.query_rows import ModuleHistoryRow, RunSummaryRow
    from app.core.system_models import SystemDefinition

KST = ZoneInfo("Asia/Seoul")


def performance_periods(now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    local = (now if now.tzinfo else now.replace(tzinfo=UTC)).astimezone(KST)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_last = start - timedelta(microseconds=1)
    previous_start = previous_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(previous_start.year, previous_start.month)[1]
    previous_end = (
        previous_last
        if local.day > last_day
        else local.replace(year=previous_start.year, month=previous_start.month)
    )
    return start, local, previous_start, previous_end


def build_performance(
    now: datetime,
    runs: list[RunSummaryRow],
    modules: list[ModuleHistoryRow],
    systems: list[SystemDefinition],
    basis: dict[str, dict[str, int]],
) -> dict[str, Any]:
    start, end, previous_start, previous_end = performance_periods(now)
    modules_by_run: dict[str, list[ModuleHistoryRow]] = {}
    for module in modules:
        modules_by_run.setdefault(module.run_id, []).append(module)
    names = {s.system_code: s.name for s in systems}
    by_system = {
        code: {"system_code": code, "system_name": name, "saved_seconds": 0, "runs": 0}
        for code, name in names.items()
    }
    days = {(start + timedelta(days=i)).date().isoformat(): 0 for i in range(end.day)}
    previous_seconds = 0
    total_runs = 0
    for run in runs:
        if run.status not in ADMIN_VISIBLE_RUN_STATUSES:
            continue
        at = run.requested_at
        at = (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(KST)
        seconds = saved_module_seconds(
            modules_by_run.get(run.run_id, []), basis.get(run.system_code, {})
        )
        if previous_start <= at <= previous_end:
            previous_seconds += seconds
        if not start <= at <= end:
            continue
        total_runs += 1
        row = by_system.setdefault(
            run.system_code,
            {
                "system_code": run.system_code,
                "system_name": names.get(run.system_code, run.system_code),
                "saved_seconds": 0,
                "runs": 0,
            },
        )
        row["saved_seconds"] += seconds
        row["runs"] += 1
        days[at.date().isoformat()] += seconds
    cumulative = 0
    daily = []
    for day, seconds in days.items():
        cumulative += seconds
        daily.append({"date": day, "saved_seconds": seconds, "cumulative_seconds": cumulative})
    return {
        "generated_at": end.astimezone(UTC).isoformat(),
        "timezone": str(KST),
        "period": {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "previous_from": previous_start.isoformat(),
            "previous_to": previous_end.isoformat(),
        },
        "total_seconds": cumulative,
        "previous_seconds": previous_seconds,
        "change_percent": round((cumulative - previous_seconds) / previous_seconds * 100, 1)
        if previous_seconds
        else None,
        "total_runs": total_runs,
        "by_system": sorted(
            by_system.values(), key=lambda s: (-s["saved_seconds"], s["system_code"])
        ),
        "daily": daily,
        "basis_note": "정상·이상징후로 완료된 실행의 통과 모듈별 수동 점검 기준 초를 합산한 추정치입니다. "
        "실행 요청일 기준으로 집계하며, 기준 시간 설정을 바꾸면 과거 지표도 현재 기준으로 재계산됩니다. "
        "도구 오류·취소 실행은 제외합니다.",
    }
