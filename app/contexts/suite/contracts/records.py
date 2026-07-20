"""Suite 영속(persistence) DTO 와 도메인 ↔ 레코드 매퍼."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteRun, SuiteStep


class SuiteStepRecord(BaseModel):
    """``SuiteStep`` 의 영속 스키마."""

    system_code: str
    system_name: str
    order: int
    run_id: str | None = None
    status: SuiteStatus = SuiteStatus.PENDING
    module_total: int = 0

    @classmethod
    def from_domain(cls, step: SuiteStep) -> SuiteStepRecord:
        return cls.model_validate(step.model_dump())

    def to_domain(self) -> SuiteStep:
        return SuiteStep.model_validate(self.model_dump())


class SuiteRecord(BaseModel):
    """``SuiteRun`` 집합체의 영속 스키마."""

    suite_id: str
    status: SuiteStatus
    steps: list[SuiteStepRecord]
    current_step_index: int = 0
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    active_run_id: str | None = None
    awaiting_input_run_id: str | None = None
    awaiting_input_prompt: str | None = None
    browser_mode: str = "headed"
    selected_system_codes: list[str] = Field(default_factory=list)
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None
    triggered_by: str = "manual"
    schedule_id: str | None = None

    @classmethod
    def from_domain(cls, suite: SuiteRun) -> SuiteRecord:
        return cls(
            **suite.model_dump(exclude={"steps"}),
            steps=[SuiteStepRecord.from_domain(step) for step in suite.steps],
        )

    def to_domain(self) -> SuiteRun:
        return SuiteRun(
            **self.model_dump(exclude={"steps"}),
            steps=[step.to_domain() for step in self.steps],
        )

    @classmethod
    def deserialize(cls, data: str) -> SuiteRun:
        return cls.model_validate_json(data).to_domain()

    @staticmethod
    def serialize(suite: SuiteRun) -> str:
        return SuiteRecord.from_domain(suite).model_dump_json()
