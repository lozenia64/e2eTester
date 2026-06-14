from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ModuleStatus, RunStatus


class ModuleDefinition(BaseModel):
    module_id: str
    system_code: str
    name: str
    description: str
    group: str
    order: int
    depends_on: list[str] = Field(default_factory=list)
    timeout_seconds: int = 180
    simulated_duration_ms: int = 1800
    simulated_outcome: str = "PASSED"
    execution_mode: str = "simulated"
    script_path: str | None = None
    workflow_name: str | None = None
    workflow_step: str | None = None


class RunFormOption(BaseModel):
    label: str
    value: str


class RunFormField(BaseModel):
    key: str
    label: str
    type: str = "text"
    required: bool = False
    placeholder: str = ""
    default: str = ""
    help_text: str = ""
    options: list[RunFormOption] = Field(default_factory=list)
    show_when: dict[str, str | list[str]] = Field(default_factory=dict)


class SystemDefinition(BaseModel):
    system_code: str
    name: str
    description: str
    modules: list[ModuleDefinition]
    run_form: list[RunFormField] = Field(default_factory=list)
    supported_auth_methods: list[str] = Field(default_factory=list)


class FailureAnalysis(BaseModel):
    category: str
    probable_cause: str
    retryable: bool
    user_summary: str
    developer_details: str
    recommended_action: str
    provider: str | None = None
    model: str | None = None


class RunModule(BaseModel):
    module_id: str
    name: str
    group: str
    order: int
    status: ModuleStatus = ModuleStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    message: str = "대기 중"
    artifact_count: int = 0
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    failure_analysis: FailureAnalysis | None = None


class FailureAnalysisRequest(BaseModel):
    run_id: str
    system_code: str
    system_name: str
    module_id: str
    module_name: str
    module_group: str
    execution_mode: str
    workflow_name: str | None = None
    workflow_step: str | None = None
    current_url: str | None = None
    last_error: str | None = None
    recent_logs: list[str] = Field(default_factory=list)
    dialog_messages: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None
    system_definition: dict = Field(default_factory=dict)


class Run(BaseModel):
    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    modules: list[RunModule]
    selected_module_ids: list[str] = Field(default_factory=list)
    awaiting_input_module_id: str | None = None
    awaiting_input_prompt: str | None = None


class DashboardEvent(BaseModel):
    event_type: str
    run_id: str
    system_code: str
    run_status: RunStatus
    payload: dict


class StartRunRequest(BaseModel):
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None


class SubmitOtpRequest(BaseModel):
    otp_code: str
