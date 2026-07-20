from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.status_labels import run_status_label

if TYPE_CHECKING:
    from app.contexts.run.contracts.query_rows import RunSummaryRow
    from app.contexts.run.views.actor import ActorContext


def summarize_row(row: RunSummaryRow, actor_context: ActorContext | None = None) -> dict:
    """홈 화면 "진행 중 / 최근 Run" 패널용 Run 요약(읽기 전용 뷰).

    입력은 ``run_history_index`` 프로젝션 행 — 진행률·현재/이슈 모듈명 등 파생 값은
    이벤트 처리 시점에 이미 계산되어 있다(PII 없음). 여기서는 표시용 라벨과 실행자
    보정(actor context)만 얹는다.
    """
    created_by_user_id = row.created_by_user_id
    created_by_user_name = row.created_by_user_name
    if actor_context is not None:
        created_by_user_id, created_by_user_name = actor_context.resolve(row)

    return {
        "run_id": row.run_id,
        "system_code": row.system_code,
        "system_name": row.system_name,
        "status": row.status,
        "status_label": run_status_label(row.status),
        "requested_at": row.requested_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "awaiting_input_module_id": row.awaiting_input_module_id,
        "awaiting_input_prompt": row.awaiting_input_prompt,
        "module_total": row.module_total,
        "module_defined_total": row.module_defined_total,
        "module_skipped": row.module_skipped,
        "module_passed": row.module_passed,
        "current_module_name": row.current_module_name,
        "failed_module_name": row.failed_module_name,
        "triggered_by": row.triggered_by,
        "suite_id": row.suite_id,
        "schedule_id": row.schedule_id,
        "created_by_user_id": created_by_user_id,
        "created_by_user_name": created_by_user_name,
    }
