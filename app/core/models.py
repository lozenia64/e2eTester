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


class RunComparison(BaseModel):
    """직전 Run(같은 시스템) 대비 모듈 상태 변화 요약."""

    has_baseline: bool = False
    baseline_run_id: str | None = None
    baseline_requested_at: datetime | None = None
    newly_failed: list[str] = Field(default_factory=list)
    recovered: list[str] = Field(default_factory=list)
    still_failing: list[str] = Field(default_factory=list)


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
    triggered_by: str = "manual"
    schedule_id: str | None = None
    comparison: RunComparison | None = None


class Schedule(BaseModel):
    schedule_id: str
    system_code: str
    system_name: str
    name: str = ""
    cron: str
    timezone: str
    enabled: bool = True
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    created_at: datetime
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_id: str | None = None
    last_run_status: RunStatus | None = None

    def to_summary(self) -> dict:
        """API/UI 노출용 요약. input_data 는 PII 가 있을 수 있어 직렬화하지 않는다."""
        return {
            "schedule_id": self.schedule_id,
            "system_code": self.system_code,
            "system_name": self.system_name,
            "name": self.name,
            "cron": self.cron,
            "timezone": self.timezone,
            "enabled": self.enabled,
            "selected_module_ids": list(self.selected_module_ids or []),
            "module_count": len(self.selected_module_ids) if self.selected_module_ids is not None else None,
            "auth_method": self.input_data.get("auth_method"),
            "created_at": self.created_at.isoformat(),
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_id": self.last_run_id,
            "last_run_status": self.last_run_status.value if self.last_run_status else None,
        }


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


class CreateScheduleRequest(BaseModel):
    cron: str
    name: str = ""
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    enabled: bool = True
