"""Run 영속(persistence) DTO 와 도메인 ↔ 레코드 매퍼."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import FailureAnalysis, Run, RunComparison, RunModule


class RunModuleRecord(BaseModel):
    """``RunModule`` 의 영속 스키마. **``logs`` 필드가 없다**(별도 집합체 소유)."""

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
    attempt: int = 1
    max_attempts: int = 1
    message: str = "대기 중"
    artifact_count: int = 0
    artifacts: list[str] = Field(default_factory=list)
    current_url: str | None = None
    dialog_messages: list[str] = Field(default_factory=list)
    # 자동 복구 가시성(설계 §3.4). "통과했다"와 "불안정하다"는 직교하는 축이므로,
    # 상태(PASSED/ANOMALY/ERROR)를 건드리지 않고 별도 필드로 표현한다.
    recovered: bool = False
    recovery_tiers: list[int] = Field(default_factory=list)
    failure_signals: list[str] = Field(default_factory=list)
    failure_analysis: FailureAnalysis | None = None

    @classmethod
    def from_domain(cls, module: RunModule) -> RunModuleRecord:
        return cls.model_validate(module.model_dump(exclude={"logs"}))

    def to_domain(self) -> RunModule:
        return RunModule.model_validate({**self.model_dump(), "logs": []})


class RunRecord(BaseModel):
    """``Run`` 상태 집합체의 영속 스키마(모듈 로그 제외)."""

    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    modules: list[RunModuleRecord]
    selected_module_ids: list[str] = Field(default_factory=list)
    awaiting_input_module_id: str | None = None
    awaiting_input_prompt: str | None = None
    triggered_by: str = "manual"
    schedule_id: str | None = None
    suite_id: str | None = None
    comparison: RunComparison | None = None
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None

    @classmethod
    def from_domain(cls, run: Run) -> RunRecord:
        return cls(
            **run.model_dump(exclude={"modules"}),
            modules=[RunModuleRecord.from_domain(module) for module in run.modules],
        )

    def to_domain(self) -> Run:
        return Run(
            **self.model_dump(exclude={"modules"}),
            modules=[module.to_domain() for module in self.modules],
        )

    @classmethod
    def deserialize(cls, data: str) -> Run:
        return cls.model_validate_json(data).to_domain()

    @staticmethod
    def serialize(run: Run) -> str:
        return RunRecord.from_domain(run).model_dump_json()
