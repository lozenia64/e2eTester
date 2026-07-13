"""이벤트 payload 에 동봉하는 요약 필드(fat event) — 프로젝션의 유일한 입력.

프로젝션이 blob 을 재수화하지 않는 것이 원칙이므로, 요약 인덱스(``run_history_index``·
``suite_history_index``)가 요구하는 모든 파생 값을 **이벤트 발행 시점에 애그리거트가 계산해
payload 에 싣는다**. 여기 함수들은 순수(시계·I/O 없음)하며 JSON 직렬화 가능한 값만 담는다
(enum → ``.value``, datetime → isoformat).
"""

from __future__ import annotations

from app.core.enums import ModuleStatus
from app.core.run_models import Run, RunModule
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES
from app.core.suite_models import SuiteRun

# ``ModuleFinished`` 로 프로젝션에 기록되는 종료 모듈 상태(스냅샷 backfill 과 동일 기준).
MODULE_HISTORY_STATUSES = frozenset(
    {
        ModuleStatus.PASSED,
        ModuleStatus.ANOMALY,
        ModuleStatus.ERROR,
        ModuleStatus.FAILED,
        ModuleStatus.BLOCKED,
        ModuleStatus.CANCELLED,
    }
)


def run_summary_fields(run: Run) -> dict:
    """Run 요약 인덱스 한 행을 만들 수 있는 파생 필드 전부(PII 없음)."""
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
    return {
        "system_code": run.system_code,
        "system_name": run.system_name,
        "status": run.status.value,
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
        "schedule_id": run.schedule_id,
        "suite_id": run.suite_id,
        "created_by_user_id": run.created_by_user_id,
        "created_by_user_name": run.created_by_user_name,
        # 실시간 프로젝터가 blob 재수화 없이 run_* WS payload(RunView)를 조립하는 데 필요.
        "selected_module_ids": list(run.selected_module_ids),
        "comparison": run.comparison.model_dump(mode="json") if run.comparison else None,
    }


def module_history_fields(run: Run, module: RunModule) -> dict:
    """``module_history_index`` 한 행을 만들 수 있는 모듈 종료 필드(PII 없음)."""
    fa = module.failure_analysis
    return {
        "module_id": module.module_id,
        "system_code": run.system_code,
        "module_name": module.name,
        "status": module.status.value,
        "message": module.message,
        "started_at": module.started_at.isoformat() if module.started_at else None,
        "ended_at": module.ended_at.isoformat() if module.ended_at else None,
        "duration_ms": module.duration_ms,
        "current_url": module.current_url,
        "artifacts": list(module.artifacts),
        "ai_category": fa.category if fa else None,
        "ai_summary": fa.user_summary if fa else None,
        "ai_action": fa.recommended_action if fa else None,
        "suite_id": run.suite_id,
        "schedule_id": run.schedule_id,
        "created_by_user_id": run.created_by_user_id,
    }


def module_history_fields_from_wire(run_summary: dict, wire: dict) -> dict:
    """``RunImported``/벌크 이벤트 와이어 모듈 → ``module_history_index`` 필드."""
    fa = wire.get("failure_analysis")
    return {
        "module_id": wire["module_id"],
        "system_code": run_summary["system_code"],
        "module_name": wire.get("name"),
        "status": wire["status"],
        "message": wire.get("message"),
        "started_at": wire.get("started_at"),
        "ended_at": wire.get("ended_at"),
        "duration_ms": wire.get("duration_ms"),
        "current_url": wire.get("current_url"),
        "artifacts": list(wire.get("artifacts") or []),
        "ai_category": fa.get("category") if fa else None,
        "ai_summary": fa.get("user_summary") if fa else None,
        "ai_action": fa.get("recommended_action") if fa else None,
        "suite_id": run_summary.get("suite_id"),
        "schedule_id": run_summary.get("schedule_id"),
        "created_by_user_id": run_summary.get("created_by_user_id"),
    }


def suite_summary_fields(suite: SuiteRun) -> dict:
    """Suite 요약 인덱스 한 행을 만들 수 있는 파생 필드 전부(PII 없음)."""
    return {
        "status": suite.status.value,
        "requested_at": suite.requested_at.isoformat(),
        "started_at": suite.started_at.isoformat() if suite.started_at else None,
        "ended_at": suite.ended_at.isoformat() if suite.ended_at else None,
        "current_step_index": suite.current_step_index,
        "active_run_id": suite.active_run_id,
        "awaiting_input_run_id": suite.awaiting_input_run_id,
        "awaiting_input_prompt": suite.awaiting_input_prompt,
        "browser_mode": suite.browser_mode,
        "selected_system_codes": list(suite.selected_system_codes),
        "triggered_by": suite.triggered_by,
        "schedule_id": suite.schedule_id,
        "created_by_user_id": suite.created_by_user_id,
        "created_by_user_name": suite.created_by_user_name,
        "step_total": len(suite.steps),
        "steps": [
            {
                "system_code": step.system_code,
                "system_name": step.system_name,
                "order": step.order,
                "run_id": step.run_id,
                "status": step.status.value,
                "module_total": step.module_total,
            }
            for step in suite.steps
        ],
    }
