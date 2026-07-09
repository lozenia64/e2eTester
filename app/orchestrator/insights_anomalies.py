"""이상징후 인박스 집계기(순수 함수).

전 Run 을 스캔해 ANOMALY/ERROR 로 끝난 모듈(이상건)만 모으고, 각 이상건에 처리 레코드
(``AnomalyHandling``: 미확인/확인함/처리완료·담당자·메모)를 조인한다. Run 이력은 시간순 실행
기록일 뿐이라 "누가 봤고 조치했는지"를 담지 못하므로, 이 인박스가 미해결 이상만 모은 팀 단위
워크리스트가 된다.

I/O 없는 순수 함수라 브라우저·DB 없이 단위 테스트할 수 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.enums import AnomalyState
from app.core.models import AnomalyHandling
from app.core.status_labels import (
    anomaly_state_label,
    module_status_badge_tone,
    module_status_label,
)
from app.orchestrator.insights_common import (
    ANOMALY_OR_ERROR_STATUSES,
    module_kind,
    module_occurred_at,
    module_run_id,
    screenshot_url,
)

if TYPE_CHECKING:
    from app.core.models import Run, SystemDefinition


def _handling_view(handling: AnomalyHandling | None) -> dict[str, Any]:
    resolved = handling or AnomalyHandling(module_run_id="", state=AnomalyState.UNRESOLVED)
    return {
        "state": str(resolved.state),
        "state_label": anomaly_state_label(resolved.state),
        "assignee_user_id": resolved.assignee_user_id,
        "assignee_name": resolved.assignee_name,
        "memo": resolved.memo,
        "updated_at": resolved.updated_at.isoformat() if resolved.updated_at else None,
    }


def build_anomaly_items(
    systems: list[SystemDefinition],
    runs: list[Run],
    handlings: dict[str, AnomalyHandling],
    *,
    allowed_system_codes: list[str] | None = None,
) -> dict[str, Any]:
    """이상건 목록 + 상태별 카운트를 만든다.

    ``systems`` 는 시스템명 조회·권한 필터용, ``runs`` 는 전체 Run, ``handlings`` 는
    ``module_run_id → AnomalyHandling`` 맵. ``allowed_system_codes`` 지정 시 그 시스템만.
    """
    system_names = {s.system_code: s.name for s in systems}
    allowed = set(allowed_system_codes) if allowed_system_codes is not None else None

    items: list[dict[str, Any]] = []
    for run in runs:
        if allowed is not None and run.system_code not in allowed:
            continue
        for module in run.modules:
            if module.status not in ANOMALY_OR_ERROR_STATUSES:
                continue
            mr_id = module_run_id(run.run_id, module.module_id)
            handling = handlings.get(mr_id)
            analysis = module.failure_analysis
            items.append(
                {
                    "module_run_id": mr_id,
                    "run_id": run.run_id,
                    "system_code": run.system_code,
                    "system_name": system_names.get(run.system_code, run.system_name),
                    "module_id": module.module_id,
                    "module_name": module.name,
                    "status": str(module.status),
                    "status_label": module_status_label(module.status),
                    "tone": module_status_badge_tone(module.status),
                    "kind": module_kind(module.status),
                    "occurred_at": module_occurred_at(run, module).isoformat(),
                    "triggered_by": run.triggered_by,
                    "current_url": module.current_url,
                    "message": module.message,
                    "screenshot": screenshot_url(module),
                    "ai_summary": analysis.user_summary if analysis else None,
                    "ai_category": analysis.category if analysis else None,
                    "handling": _handling_view(handling),
                }
            )

    items.sort(key=lambda it: it["occurred_at"], reverse=True)

    counts = {
        "total": len(items),
        "unresolved": sum(1 for it in items if it["handling"]["state"] == AnomalyState.UNRESOLVED),
        "acknowledged": sum(
            1 for it in items if it["handling"]["state"] == AnomalyState.ACKNOWLEDGED
        ),
        "resolved": sum(1 for it in items if it["handling"]["state"] == AnomalyState.RESOLVED),
        "anomaly": sum(1 for it in items if it["kind"] == "anomaly"),
        "error": sum(1 for it in items if it["kind"] == "error"),
    }
    # 시스템 필터 드롭다운용(권한 내 시스템만, 이상건 유무와 무관하게 노출).
    system_options = [
        {"system_code": s.system_code, "system_name": s.name}
        for s in systems
        if allowed is None or s.system_code in allowed
    ]

    return {"items": items, "counts": counts, "systems": system_options}
