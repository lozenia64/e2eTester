from __future__ import annotations

from app.runner.artifact_manager import ArtifactManager
from app.systems.access_common.executor import AccessWorkflowExecutor, create_access_executor

DEFAULT_BASE_URL = "https://sls.hwgeneralins.com"


def create_executor(artifact_manager: ArtifactManager) -> AccessWorkflowExecutor:
    return create_access_executor(
        artifact_manager,
        execution_mode="hwtc_workflow_step",
        system_code="hwtc",
        base_url=DEFAULT_BASE_URL,
        mobile=False,
    )
