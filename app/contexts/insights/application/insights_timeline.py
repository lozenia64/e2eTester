"""시스템 수직 타임라인 집계기(순수 함수).

핵심 질문: "언제부터, 왜 틀어졌나?" Run 을 시간 역순 카드로 세우고, 이상/실패 Run 은 실패 모듈·
AI 원인분석·종료 스크린샷을 인라인으로 편다. ``comparison`` 의 newly_failed 를 스캔해 "○○ 모듈이
이 Run부터 깨지기 시작"하는 **회귀 시작점**을 카드에 표시하고, recovered/newly_failed 변화 칩을 붙인다.

I/O 없는 순수 함수라 브라우저·DB 없이 단위 테스트할 수 있다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.contexts.insights.application.insights_common import (
    ANOMALY_OR_ERROR_STATUSES,
    RunHistoryView,
    screenshot_url,
    sort_runs_desc,
)
from app.core.status_labels import (
    module_status_badge_tone,
    module_status_label,
    run_status_badge_tone,
    run_status_label,
)

if TYPE_CHECKING:
    from app.contexts.run.views.actor import ActorContext
    from app.core.system_models import SystemDefinition

TRIGGER_LABELS = {"manual": "수동", "schedule": "예약", "suite": "Suite"}


def _trigger(run: RunHistoryView) -> str:
    if run.suite_id:
        return "suite"
    if run.triggered_by == "schedule":
        return "schedule"
    return "manual"


def _duration_ms(run: RunHistoryView) -> int | None:
    if run.started_at and run.ended_at:
        delta = (run.ended_at - run.started_at).total_seconds() * 1000
        return round(delta)
    total = sum(m.duration_ms or 0 for m in run.modules)
    return total or None


def _names(module_ids: list[str], name_by_id: dict[str, str]) -> list[dict[str, str]]:
    return [{"module_id": mid, "name": name_by_id.get(mid, mid)} for mid in module_ids]


def build_system_timeline(
    system: SystemDefinition,
    runs: list[RunHistoryView],
    *,
    limit: int,
    actor_context: ActorContext | None = None,
) -> dict[str, Any]:
    """시스템 1개의 타임라인(최근 ``limit`` Run) 데이터를 만든다."""
    name_by_id = {m.module_id: m.name for m in system.modules}
    ordered = sort_runs_desc(runs)[:limit]

    cards: list[dict[str, Any]] = []
    for run in ordered:
        is_anomaly = any(m.status in ANOMALY_OR_ERROR_STATUSES for m in run.modules)

        failed_modules: list[dict[str, Any]] = []
        for module in run.modules:
            if module.status not in ANOMALY_OR_ERROR_STATUSES:
                continue
            failed_modules.append(
                {
                    "module_id": module.module_id,
                    "name": module.name,
                    "status": str(module.status),
                    "status_label": module_status_label(module.status),
                    "tone": module_status_badge_tone(module.status),
                    "current_url": module.current_url,
                    "message": module.message,
                    "screenshot": screenshot_url(module),
                    "ai_summary": module.ai_summary,
                    "ai_category": module.ai_category,
                    "ai_action": module.ai_action,
                }
            )

        comparison = run.comparison
        newly_failed = comparison.newly_failed if comparison else []
        recovered = comparison.recovered if comparison else []
        still_failing = comparison.still_failing if comparison else []

        if actor_context is not None:
            _uid, executor = actor_context.resolve(run)
        else:
            executor = run.created_by_user_name

        trigger = _trigger(run)
        cards.append(
            {
                "run_id": run.run_id,
                "status": str(run.status),
                "status_label": run_status_label(run.status),
                "status_tone": run_status_badge_tone(run.status),
                "requested_at": run.requested_at.isoformat(),
                "duration_ms": _duration_ms(run),
                "trigger": trigger,
                "trigger_label": TRIGGER_LABELS.get(trigger, trigger),
                "executor": executor or "(시스템)",
                "is_anomaly": is_anomaly,
                "failed_modules": failed_modules,
                # comparison.newly_failed 가 비어있지 않으면 이 Run 이 그 모듈들의 회귀 시작점.
                "regression_modules": _names(newly_failed, name_by_id),
                "recovered": _names(recovered, name_by_id),
                "newly_failed": _names(newly_failed, name_by_id),
                "still_failing": _names(still_failing, name_by_id),
            }
        )

    return {
        "system_code": system.system_code,
        "system_name": system.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "limit": limit,
        "cards": cards,
    }
