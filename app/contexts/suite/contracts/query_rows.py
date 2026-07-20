"""Suite 컨텍스트 읽기 모델 쿼리 행(row) 타입."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import SuiteStatus


@dataclass(frozen=True)
class SuiteStepRow:
    system_code: str
    system_name: str
    order: int
    run_id: str | None
    status: SuiteStatus
    module_total: int


@dataclass(frozen=True)
class SuiteSummaryRow:
    """``suite_history_index`` 한 행 — Suite 목록/운영 스냅샷용 요약."""

    suite_id: str
    status: SuiteStatus
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    current_step_index: int
    active_run_id: str | None
    awaiting_input_run_id: str | None
    awaiting_input_prompt: str | None
    browser_mode: str | None
    selected_system_codes: tuple[str, ...]
    triggered_by: str
    schedule_id: str | None
    created_by_user_id: str | None
    created_by_user_name: str | None
    step_total: int
    steps: tuple[SuiteStepRow, ...] = field(default_factory=tuple)
