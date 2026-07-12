"""시스템 헬스 대시보드 집계기(순수 함수).

핵심 질문: "이 시스템, 요즘 건강한가?" 30일(기본) 통과율·연속 정상 스트릭·마지막 이상 이후
경과·평균 소요(전주 대비 증감), 일별 통과율/평균소요 추이, 모듈 안정성(flaky) 랭킹, 월별 통과율
캘린더 히트맵을 하나로 만든다. I/O 없는 순수 함수라 브라우저·DB 없이 단위 테스트할 수 있다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any

from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import (
    module_status_badge_tone,
    module_status_label,
)
from app.orchestrator.insights_common import (
    ANOMALY_OR_ERROR_STATUSES,
    CONCLUSIVE_MODULE_STATUSES,
    ModuleHistoryView,
    RunHistoryView,
    local_date_key,
    sort_runs_asc,
    sort_runs_desc,
)

if TYPE_CHECKING:
    from app.core.system_models import SystemDefinition


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _run_totals(run: RunHistoryView) -> tuple[int, int, int]:
    """(passed_modules, conclusive_modules, duration_ms) 한 Run 집계."""
    passed = sum(1 for m in run.modules if m.status == ModuleStatus.PASSED)
    conclusive = sum(1 for m in run.modules if m.status in CONCLUSIVE_MODULE_STATUSES)
    duration = sum(m.duration_ms or 0 for m in run.modules)
    return passed, conclusive, duration


def _score_tone(rate: int | None) -> str:
    if rate is None:
        return "not_inspected"
    if rate >= 95:
        return "passed"
    if rate >= 80:
        return "anomaly"
    return "error"


def _rate(passed: int, conclusive: int) -> int | None:
    return round(passed / conclusive * 100) if conclusive else None


def _date_axis(now_local_date, days: int) -> list[str]:
    start = now_local_date - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def _streak(runs_desc: list[RunHistoryView]) -> int:
    """가장 최근부터 연속으로 '정상(PASSED)'인 Run 수."""
    streak = 0
    for run in runs_desc:
        if run.status == RunStatus.PASSED:
            streak += 1
        else:
            break
    return streak


def _module_conclusive_status(module: ModuleHistoryView) -> ModuleStatus | None:
    return module.status if module.status in CONCLUSIVE_MODULE_STATUSES else None


def _stability_ranking(
    system: SystemDefinition, window_runs_asc: list[RunHistoryView]
) -> list[dict[str, Any]]:
    """모듈별 안정성: flaky 점수(상태 뒤집힘 횟수)·통과율·평균소요·마지막 상태."""
    ordered_modules = sorted(system.modules, key=lambda m: m.order)
    rows: list[dict[str, Any]] = []
    for mod_def in ordered_modules:
        statuses: list[ModuleStatus] = []
        durations: list[int] = []
        passed = 0
        for run in window_runs_asc:
            for module in run.modules:
                if module.module_id != mod_def.module_id:
                    continue
                status = _module_conclusive_status(module)
                if status is None:
                    continue
                statuses.append(status)
                if module.duration_ms is not None:
                    durations.append(module.duration_ms)
                if status == ModuleStatus.PASSED:
                    passed += 1
        conclusive = len(statuses)
        # flaky = '정상' 여부가 연속 결과 사이에서 뒤집힌 횟수.
        flips = sum(
            1
            for a, b in zip(statuses, statuses[1:], strict=False)
            if (a == ModuleStatus.PASSED) != (b == ModuleStatus.PASSED)
        )
        last_status = statuses[-1] if statuses else None
        rows.append(
            {
                "module_id": mod_def.module_id,
                "name": mod_def.name,
                "order": mod_def.order,
                "runs_count": conclusive,
                "flaky_score": flips,
                "pass_rate": _rate(passed, conclusive),
                "avg_duration_ms": round(sum(durations) / len(durations)) if durations else None,
                "last_status": str(last_status) if last_status else None,
                "last_status_label": module_status_label(last_status) if last_status else "미점검",
                "last_status_tone": (
                    module_status_badge_tone(last_status) if last_status else "not_inspected"
                ),
            }
        )
    # 불안정한(flaky 높고 통과율 낮은) 모듈이 위로.
    rows.sort(
        key=lambda r: (-r["flaky_score"], r["pass_rate"] if r["pass_rate"] is not None else 101)
    )
    return rows


def build_system_health(
    system: SystemDefinition,
    runs: list[RunHistoryView],
    *,
    days: int,
    now: datetime,
    tz: tzinfo,
) -> dict[str, Any]:
    """시스템 1개의 헬스 대시보드 데이터를 만든다.

    ``runs`` 는 해당 시스템의 전체 Run(임의 순서). ``days`` 는 헬스 윈도(기본 30). ``now``/``tz``
    는 일자 버킷팅 기준(서비스가 주입). 반환은 헬스 헤더·추이 시계열·안정성 랭킹·캘린더 히트맵.
    """
    now = _as_utc(now)
    window_start = now - timedelta(days=days)
    window_runs = [r for r in runs if _as_utc(r.requested_at) >= window_start]
    window_asc = sort_runs_asc(window_runs)
    window_desc = sort_runs_desc(window_runs)
    all_desc = sort_runs_desc(runs)

    # ── 헬스 스코어(윈도 전체 모듈 통과율) ──────────────────────────────────
    total_passed = total_conclusive = 0
    for run in window_runs:
        p, c, _d = _run_totals(run)
        total_passed += p
        total_conclusive += c
    score = _rate(total_passed, total_conclusive)

    # ── 마지막 이상 이후 경과 ────────────────────────────────────────────────
    last_anomaly_at = None
    for run in all_desc:
        if any(m.status in ANOMALY_OR_ERROR_STATUSES for m in run.modules):
            last_anomaly_at = _as_utc(run.requested_at)
            break

    # ── 평균 소요 + 전주 대비 ────────────────────────────────────────────────
    def _avg_duration(since: datetime, until: datetime) -> float | None:
        vals = [
            _run_totals(r)[2]
            for r in runs
            if since <= _as_utc(r.requested_at) < until and _run_totals(r)[1] > 0
        ]
        return sum(vals) / len(vals) if vals else None

    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    avg_recent = _avg_duration(week_ago, now)
    avg_prev = _avg_duration(two_weeks_ago, week_ago)
    if avg_recent is not None and avg_prev:
        duration_delta_pct = round((avg_recent - avg_prev) / avg_prev * 100)
    else:
        duration_delta_pct = None

    # ── 일별 시계열(연속 날짜축) ──────────────────────────────────────────────
    now_local_date = now.astimezone(tz).date()
    axis = _date_axis(now_local_date, days)
    daily_passed: dict[str, int] = dict.fromkeys(axis, 0)
    daily_conclusive: dict[str, int] = dict.fromkeys(axis, 0)
    daily_dur_sum: dict[str, int] = dict.fromkeys(axis, 0)
    daily_run_count: dict[str, int] = dict.fromkeys(axis, 0)
    for run in window_asc:
        key = local_date_key(run.requested_at, tz)
        if key not in daily_passed:
            continue
        p, c, dur = _run_totals(run)
        daily_passed[key] += p
        daily_conclusive[key] += c
        daily_dur_sum[key] += dur
        daily_run_count[key] += 1

    daily = [
        {
            "date": d,
            "pass_rate": _rate(daily_passed[d], daily_conclusive[d]),
            "avg_duration_ms": (
                round(daily_dur_sum[d] / daily_run_count[d]) if daily_run_count[d] else None
            ),
            "run_count": daily_run_count[d],
        }
        for d in axis
    ]

    return {
        "system_code": system.system_code,
        "system_name": system.name,
        "days": days,
        "generated_at": now.isoformat(),
        "header": {
            "score": score,
            "score_tone": _score_tone(score),
            "streak": _streak(window_desc),
            "total_runs": len(window_runs),
            "passed_runs": sum(1 for r in window_runs if r.status == RunStatus.PASSED),
            "last_anomaly_at": last_anomaly_at.isoformat() if last_anomaly_at else None,
            "avg_duration_ms": round(avg_recent) if avg_recent is not None else None,
            "duration_delta_pct": duration_delta_pct,
        },
        "daily": daily,
        "stability": _stability_ranking(system, window_asc),
    }
