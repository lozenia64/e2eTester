from __future__ import annotations

from app.core.enums import ModuleStatus
from app.core.models import Run


def summarize_run(run: Run) -> dict:
    """홈 화면 "진행 중 / 최근 Run" 패널용 Run 요약(읽기 전용 뷰).

    PII 가 섞일 수 있는 입력값은 포함하지 않고, 진행률·현재/실패 모듈명 등 표시용
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
    failed_module = next(
        (
            module
            for module in ordered_modules
            if module.module_id in selected_module_ids and module.status == ModuleStatus.FAILED
        ),
        None,
    )
    return {
        "run_id": run.run_id,
        "system_code": run.system_code,
        "system_name": run.system_name,
        "status": run.status,
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
        "failed_module_name": failed_module.name if failed_module else None,
        "triggered_by": run.triggered_by,
        "suite_id": run.suite_id,
    }
