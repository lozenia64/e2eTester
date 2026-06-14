from __future__ import annotations

from importlib import import_module
from typing import Any, Iterable

from app.runner.artifact_manager import ArtifactManager


def load_workflow_executors(system_codes: Iterable[str], artifact_manager: ArtifactManager) -> dict[str, Any]:
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
        executors[executor.execution_mode] = executor
    return executors
