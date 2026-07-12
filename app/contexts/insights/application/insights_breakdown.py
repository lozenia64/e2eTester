"""모듈 딥다이브 집계기(순수 함수).

핵심 질문: "어느 단계가 약한가?" ``depends_on`` 기반 모듈 파이프라인을 노드별 최근 통과율·평균소요·
마지막 상태로 채우고, **자기 과거 대비 느려진 노드**(속도 저하)와 flaky 노드(취약)를 자동 표시한다
(절대 최장 소요는 스텝 수가 많을 뿐일 수 있어 병목으로 보지 않는다). 노드별로 소요시간
추이(스파크라인)·실패 유형 분포(``failure_analysis.category``, AI 꺼짐 시 마지막 에러메시지 Top-N)·
최근 스크린샷 스트립을 제공하고, 단계별 누적 소요로 어느 단계가 점검 시간을 잡아먹는지 보여준다.

I/O 없는 순수 함수라 브라우저·DB 없이 단위 테스트할 수 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.contexts.insights.application.insights_common import (
    ANOMALY_OR_ERROR_STATUSES,
    CONCLUSIVE_MODULE_STATUSES,
    RunHistoryView,
    screenshot_url,
    sort_runs_desc,
)
from app.core.enums import ModuleStatus
from app.core.status_labels import (
    module_status_badge_tone,
    module_status_label,
)

if TYPE_CHECKING:
    from app.core.system_models import SystemDefinition

_RECENT_RUNS = 40
_MAX_SHOTS = 6
_MAX_CATEGORIES = 6
# '느려짐(속도 저하)' 판정 — 절대 소요가 아니라 **자기 자신의 과거 대비** 최근이 느려진 정도로
# 잡는다(스텝이 많아 원래 오래 걸리는 모듈을 병목으로 오인하지 않기 위함). 충분한 표본이 있고
# 최근 절반 평균이 이전 절반 평균보다 이 임계 이상 느려졌을 때만 후보로 본다.
_SLOWDOWN_MIN_SAMPLES = 4
_SLOWDOWN_THRESHOLD_PCT = 20


def _truncate(text: str, length: int = 40) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= length else text[: length - 1] + "…"


def _module_deepdive(module_id: str, recent_desc: list[RunHistoryView]) -> dict[str, Any]:
    recent_asc = list(reversed(recent_desc))
    statuses: list[ModuleStatus] = []
    durations: list[int] = []
    passed = 0
    duration_series: list[dict[str, Any]] = []
    for run in recent_asc:
        for module in run.modules:
            if module.module_id != module_id:
                continue
            if module.status not in CONCLUSIVE_MODULE_STATUSES:
                continue
            statuses.append(module.status)
            if module.duration_ms is not None:
                durations.append(module.duration_ms)
                duration_series.append(
                    {
                        "run_id": run.run_id,
                        "at": run.requested_at.isoformat(),
                        "duration_ms": module.duration_ms,
                    }
                )
            if module.status == ModuleStatus.PASSED:
                passed += 1

    conclusive = len(statuses)
    flips = sum(
        1
        for a, b in zip(statuses, statuses[1:], strict=False)
        if (a == ModuleStatus.PASSED) != (b == ModuleStatus.PASSED)
    )

    # ── 실패 유형 분포(AI category → 없으면 마지막 에러 메시지) ────────────────
    cat_counts: dict[str, int] = {}
    cat_fallback = False
    for run in recent_desc:
        for module in run.modules:
            if module.module_id != module_id:
                continue
            if module.status not in ANOMALY_OR_ERROR_STATUSES:
                continue
            if module.ai_category:
                label = module.ai_category
            else:
                label = _truncate(module.message) or "원인 미상"
                cat_fallback = True
            cat_counts[label] = cat_counts.get(label, 0) + 1
    failure_categories = [
        {"label": label, "count": count}
        for label, count in sorted(cat_counts.items(), key=lambda kv: kv[1], reverse=True)
    ][:_MAX_CATEGORIES]

    # ── 최근 스크린샷 스트립(시간에 따른 화면 변화) ────────────────────────────
    shots: list[dict[str, Any]] = []
    for run in recent_desc:
        for module in run.modules:
            if module.module_id != module_id:
                continue
            url = screenshot_url(module)
            if url:
                shots.append(
                    {
                        "run_id": run.run_id,
                        "url": url,
                        "at": run.requested_at.isoformat(),
                        "status_tone": module_status_badge_tone(module.status),
                    }
                )
        if len(shots) >= _MAX_SHOTS:
            break

    last_status = statuses[-1] if statuses else None
    avg_duration = round(sum(durations) / len(durations)) if durations else None
    pass_rate = round(passed / conclusive * 100) if conclusive else None

    # 자기 자신 기준 속도 저하: 최근 절반 평균이 이전 절반 평균보다 느려진 정도(%).
    # durations 는 시간 오름차순이라 앞쪽 절반이 과거 기준선, 뒤쪽 절반이 최근이다.
    slowdown_pct = None
    if len(durations) >= _SLOWDOWN_MIN_SAMPLES:
        half = len(durations) // 2
        base = durations[:half]
        recent = durations[half:]
        base_avg = sum(base) / len(base)
        recent_avg = sum(recent) / len(recent)
        if base_avg > 0:
            slowdown_pct = round((recent_avg - base_avg) / base_avg * 100)

    return {
        "runs_count": conclusive,
        "pass_rate": pass_rate,
        "avg_duration_ms": avg_duration,
        "slowdown_pct": slowdown_pct,
        "flaky_score": flips,
        "last_status": str(last_status) if last_status else None,
        "last_status_label": module_status_label(last_status) if last_status else "미점검",
        "last_status_tone": (
            module_status_badge_tone(last_status) if last_status else "not_inspected"
        ),
        "duration_series": duration_series,
        "failure_categories": failure_categories,
        "failure_categories_fallback": cat_fallback,
        "screenshots": shots[:_MAX_SHOTS],
    }


def build_module_breakdown(system: SystemDefinition, runs: list[RunHistoryView]) -> dict[str, Any]:
    """시스템 1개의 모듈별 딥다이브 데이터 + 파이프라인(플로우) 노드를 만든다."""
    recent_desc = sort_runs_desc(runs)[:_RECENT_RUNS]
    ordered = sorted(system.modules, key=lambda m: m.order)

    modules: list[dict[str, Any]] = []
    for mod_def in ordered:
        deep = _module_deepdive(mod_def.module_id, recent_desc)
        modules.append(
            {
                "module_id": mod_def.module_id,
                "name": mod_def.name,
                "group": mod_def.group,
                "order": mod_def.order,
                "depends_on": list(mod_def.depends_on),
                **deep,
            }
        )

    # 느려짐(자기 과거 대비 최근이 임계 이상 느려진 모듈) / 가장 flaky 한 노드 자동 표시.
    # 절대 최장 소요는 '병목'이 아니다(스텝이 많으면 원래 오래 걸림) — 아무것도 안 느려졌으면
    # 아무 노드도 표시하지 않는다.
    degrading = [
        m
        for m in modules
        if m["slowdown_pct"] is not None and m["slowdown_pct"] >= _SLOWDOWN_THRESHOLD_PCT
    ]
    slowing_id = max(degrading, key=lambda m: m["slowdown_pct"])["module_id"] if degrading else None
    flakies = [m for m in modules if m["flaky_score"] > 0]
    flakiest_id = (
        max(flakies, key=lambda m: (m["flaky_score"], -(m["pass_rate"] or 0)))["module_id"]
        if flakies
        else None
    )
    for module in modules:
        module["is_slowing"] = module["module_id"] == slowing_id
        module["is_flaky"] = module["module_id"] == flakiest_id

    cumulative = [
        {
            "module_id": m["module_id"],
            "name": m["name"],
            "order": m["order"],
            "avg_duration_ms": m["avg_duration_ms"] or 0,
        }
        for m in modules
    ]

    return {
        "system_code": system.system_code,
        "system_name": system.name,
        "runs_analyzed": len(recent_desc),
        "modules": modules,
        "cumulative": cumulative,
        "summary": {
            "slowing_module_id": slowing_id,
            "flakiest_module_id": flakiest_id,
        },
    }
