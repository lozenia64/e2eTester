"""Suite 도메인 이벤트 — 판별 유니온 + 이벤트 레코드."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from app.core.enums import SuiteStatus


class SuiteStepSummaryWire(TypedDict):
    system_code: str
    system_name: str
    order: int
    run_id: str | None
    status: str
    module_total: int


class SuiteSummaryWire(TypedDict):
    """``suite_summary_fields`` 가 만드는 fat-event 요약(dict 키 고정)."""

    status: str
    requested_at: str
    started_at: str | None
    ended_at: str | None
    current_step_index: int
    active_run_id: str | None
    awaiting_input_run_id: str | None
    awaiting_input_prompt: str | None
    browser_mode: str
    selected_system_codes: list[str]
    triggered_by: str
    schedule_id: str | None
    created_by_user_id: str | None
    created_by_user_name: str | None
    step_total: int
    steps: list[SuiteStepSummaryWire]


@dataclass(frozen=True)
class SuiteCreated:
    triggered_by: str


@dataclass(frozen=True)
class SuiteStarted:
    pass


@dataclass(frozen=True)
class SuiteStepStarted:
    step_index: int


@dataclass(frozen=True)
class SuiteStepRunLinked:
    step_index: int
    run_id: str


@dataclass(frozen=True)
class SuiteStepFinished:
    step_index: int
    error: str | None = None


@dataclass(frozen=True)
class SuiteWaitingInput:
    run_id: str


@dataclass(frozen=True)
class SuiteResumed:
    pass


@dataclass(frozen=True)
class SuiteFinished:
    status: SuiteStatus


SuiteEvent = (
    SuiteCreated
    | SuiteStarted
    | SuiteStepStarted
    | SuiteStepRunLinked
    | SuiteStepFinished
    | SuiteWaitingInput
    | SuiteResumed
    | SuiteFinished
)


@dataclass(frozen=True)
class SuiteEventRecord:
    event: SuiteEvent
    suite_summary: SuiteSummaryWire | None
    event_id: str
    occurred_at: datetime
    version: int = 1
