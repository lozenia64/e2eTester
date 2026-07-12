from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from typing import TYPE_CHECKING, Any

from app.automation.wiring import build_engine_for_execution_mode
from app.runner.artifact_manager import ArtifactManager

if TYPE_CHECKING:
    from app.contexts.healing.engine import SelfHealingEngine


def load_workflow_executors(
    system_codes: Iterable[str],
    artifact_manager: ArtifactManager,
    healing_engine: SelfHealingEngine | None = None,
) -> dict[str, Any]:
    executors: dict[str, Any] = {}
    for system_code in system_codes:
        module_name = f"app.systems.{system_code}.executor"
        try:
            executor_module = import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        create_executor = getattr(executor_module, "create_executor", None)
        if create_executor is None:
            continue

        executor = create_executor(artifact_manager)
        # 자가 치유 엔진은 선택 협력자 — 생성자 시그니처를 바꾸지 않고 생성 직후 부착한다
        # (모든 실행기는 BaseWorkflowExecutor 의 attach_healing 을 상속).
        if healing_engine is not None:
            attach = getattr(executor, "attach_healing", None)
            if attach is not None:
                attach(healing_engine)
        # Automation BC: execution_mode 에 맞는 ScenarioEngine 을 부착한다.
        attach_auto = getattr(executor, "attach_automation", None)
        if attach_auto is not None:
            engine = build_engine_for_execution_mode(executor.execution_mode)
            if engine is not None:
                attach_auto(engine)
        executors[executor.execution_mode] = executor
    return executors
