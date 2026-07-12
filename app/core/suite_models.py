"""Suite 도메인 엔티티 + 실시간 이벤트 DTO."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import SuiteStatus


class SuiteStep(BaseModel):
    system_code: str
    system_name: str
    order: int
    run_id: str | None = None
    status: SuiteStatus = SuiteStatus.PENDING
    module_total: int = 0


class SuiteRun(BaseModel):
    suite_id: str
    status: SuiteStatus
    steps: list[SuiteStep]
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
    # Run 과 동일한 출처 추적 — 예약 관리 센터가 schedule_id 로 Suite 이력을 조회한다.
    triggered_by: str = "manual"
    schedule_id: str | None = None


class SuiteEvent(BaseModel):
    event_type: str
    suite_id: str
    suite_status: SuiteStatus
    payload: dict
