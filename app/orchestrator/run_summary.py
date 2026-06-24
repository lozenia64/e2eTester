from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.enums import ModuleStatus
from app.core.models import Run
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES, run_status_label

if TYPE_CHECKING:
    from app.orchestrator.run_actor import ActorContext


def summarize_run(run: Run, actor_context: ActorContext | None = None) -> dict:
    """홈 화면 "진행 중 / 최근 Run" 패널용 Run 요약(읽기 전용 뷰).

    PII 가 섞일 수 있는 입력값은 포함하지 않고, 진행률·현재/이슈 모듈명 등 표시용
    파생 값만 추린다.
    """
    ordered_modules = sorted(run.modules, key=lambda module: module.order)
    selected_module_ids = set(run.selected_module_ids) or {
        module.module_id for module in ordered_modules if module.status != ModuleStatus.SKIPPED
    }
    current_module = next(
        (
            module
            for module in ordered_modules
            if module.module_id in selected_module_ids
            and module.status in {ModuleStatus.RUNNING, ModuleStatus.WAITING_INPUT}
        ),
        None,
    )
    issue_module = next(
        (
            module
            for module in ordered_modules
            if module.module_id in selected_module_ids
            and module.status in MODULE_ANOMALY_STATUSES | MODULE_ERROR_STATUSES
        ),
        None,
    )
    created_by_user_id = run.created_by_user_id
    created_by_user_name = run.created_by_user_name
    if actor_context is not None:
        created_by_user_id, created_by_user_name = actor_context.resolve(run)

    return {
        "run_id": run.run_id,
        "system_code": run.system_code,
        "system_name": run.system_name,
        "status": run.status,
        "status_label": run_status_label(run.status),
        "requested_at": run.requested_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "awaiting_input_module_id": run.awaiting_input_module_id,
        "awaiting_input_prompt": run.awaiting_input_prompt,
        "module_total": len(selected_module_ids),
        "module_defined_total": len(run.modules),
        "module_skipped": sum(1 for module in run.modules if module.status == ModuleStatus.SKIPPED),
        "module_passed": sum(
            1
            for module in run.modules
            if module.module_id in selected_module_ids and module.status == ModuleStatus.PASSED
        ),
        "current_module_name": current_module.name if current_module else None,
        "failed_module_name": issue_module.name if issue_module else None,
        "triggered_by": run.triggered_by,
        "suite_id": run.suite_id,
        "created_by_user_id": created_by_user_id,
        "created_by_user_name": created_by_user_name,
    }
