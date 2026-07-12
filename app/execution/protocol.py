from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition


class OpenSessionRequest(BaseModel):
    execution_mode: str
    input_data: dict[str, str]
    run_id: str
    module_id: str


class OpenSessionResponse(BaseModel):
    session_id: str


class RunStepRequest(BaseModel):
    run_id: str
    module: ModuleDefinition


class HealingAttemptPayload(BaseModel):
    broken_selector: str
    action: str
    healed_selector: str | None = None
    confidence: float = 0.0
    strategy: str = "heuristic-dom-scan"
    candidates_considered: int = 0
    error_excerpt: str = ""
    page_url: str | None = None
    duration_ms: int = 0
    retry_succeeded: bool | None = None


class RunStepResponse(BaseModel):
    status: ModuleStatus
    message: str
    artifacts: list[str] = Field(default_factory=list)
    current_url: str | None = None
    dialog_messages: list[str] = Field(default_factory=list)
    last_error: str | None = None
    screenshot_path: str | None = None
    healing_events: list[HealingAttemptPayload] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)


class SubmitInputRequest(BaseModel):
    value: str


class HeartbeatRequest(BaseModel):
    worker_id: str
    session_id: str


class HeartbeatResponse(BaseModel):
    ok: bool


class CloseSessionRequest(BaseModel):
    session_id: str


class ResumeFromStepRequest(BaseModel):
    module_index: int
    workflow_step: str


class ErrorResponse(BaseModel):
    detail: str


def healing_attempt_to_payload(attempt: Any) -> HealingAttemptPayload:
    return HealingAttemptPayload(
        broken_selector=attempt.broken_selector,
        action=str(attempt.action.value if hasattr(attempt.action, "value") else attempt.action),
        healed_selector=attempt.healed_selector,
        confidence=attempt.confidence,
        strategy=attempt.strategy,
        candidates_considered=attempt.candidates_considered,
        error_excerpt=attempt.error_excerpt,
        page_url=attempt.page_url,
        duration_ms=attempt.duration_ms,
        retry_succeeded=attempt.retry_succeeded,
    )
