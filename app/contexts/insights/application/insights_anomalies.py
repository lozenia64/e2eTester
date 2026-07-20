"""이상징후 인박스 집계기(순수 함수).

``anomaly_inbox_index`` 프로젝션 행 + 처리 레코드를 조인해 이상건 워크리스트를 만든다.
레거시 ``build_anomaly_items`` 는 단위 테스트용 Run 스캔 경로로 유지한다.

I/O 없는 순수 함수라 브라우저·DB 없이 단위 테스트할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.contexts.insights.application.insights_common import (
    ANOMALY_OR_ERROR_STATUSES,
    RunHistoryView,
    module_kind,
    module_occurred_at,
    module_run_id,
    screenshot_url,
)
from app.core.enums import AnomalyState
from app.core.run_models import AnomalyHandling
from app.core.status_labels import (
    anomaly_state_label,
    module_status_badge_tone,
    module_status_label,
)

if TYPE_CHECKING:
    from app.contexts.insights.contracts.query_rows import AnomalyInboxRow
    from app.core.system_models import SystemDefinition


@dataclass(frozen=True)
class AnomalyModuleEnrichment:
    """인박스 인덱스 행에 조인할 Run 모듈 상세(표시용)."""

    module_name: str
    system_name: str
    triggered_by: str
    current_url: str | None
    message: str
    screenshot: str | None
    ai_summary: str | None
    ai_category: str | None
    occurred_at: datetime


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


def _anomaly_items_payload(
    systems: list[SystemDefinition],
    items: list[dict[str, Any]],
    allowed: set[str] | None,
) -> dict[str, Any]:
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
    system_options = [
        {"system_code": s.system_code, "system_name": s.name}
        for s in systems
        if allowed is None or s.system_code in allowed
    ]
    return {"items": items, "counts": counts, "systems": system_options}


def build_anomaly_items_from_index(
    systems: list[SystemDefinition],
    index_rows: list[AnomalyInboxRow],
    enrichments: dict[str, AnomalyModuleEnrichment],
    handlings: dict[str, AnomalyHandling],
    *,
    allowed_system_codes: list[str] | None = None,
) -> dict[str, Any]:
    """``anomaly_inbox_index`` 행 + 처리 레코드로 이상건 목록을 만든다."""
    system_names = {s.system_code: s.name for s in systems}
    allowed = set(allowed_system_codes) if allowed_system_codes is not None else None

    items: list[dict[str, Any]] = []
    for row in index_rows:
        if allowed is not None and row.system_code not in allowed:
            continue
        enrichment = enrichments.get(row.module_run_id)
        if enrichment is None:
            continue
        handling = handlings.get(row.module_run_id)
        items.append(
            {
                "module_run_id": row.module_run_id,
                "run_id": row.run_id,
                "system_code": row.system_code,
                "system_name": enrichment.system_name
                or system_names.get(row.system_code, row.system_code),
                "module_id": row.module_id,
                "module_name": enrichment.module_name,
                "status": str(row.status),
                "status_label": module_status_label(row.status),
                "tone": module_status_badge_tone(row.status),
                "kind": module_kind(row.status),
                "occurred_at": enrichment.occurred_at.isoformat(),
                "triggered_by": enrichment.triggered_by,
                "current_url": enrichment.current_url,
                "message": enrichment.message,
                "screenshot": enrichment.screenshot,
                "ai_summary": enrichment.ai_summary,
                "ai_category": enrichment.ai_category,
                "handling": _handling_view(handling),
            }
        )

    items.sort(key=lambda it: it["occurred_at"], reverse=True)
    return _anomaly_items_payload(systems, items, allowed)


def build_anomaly_items(
    systems: list[SystemDefinition],
    runs: list[RunHistoryView],
    handlings: dict[str, AnomalyHandling],
    *,
    allowed_system_codes: list[str] | None = None,
) -> dict[str, Any]:
    """이상건 목록 + 상태별 카운트를 만든다(읽기 뷰 스캔 — 단위 테스트용 보조 경로)."""
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
                    "ai_summary": module.ai_summary,
                    "ai_category": module.ai_category,
                    "handling": _handling_view(handling),
                }
            )

    items.sort(key=lambda it: it["occurred_at"], reverse=True)
    return _anomaly_items_payload(systems, items, allowed)
