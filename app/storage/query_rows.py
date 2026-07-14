"""읽기 모델 쿼리 포트가 반환하는 행(row) 타입 + 질의 파라미터.

화면이 요구하는 모양(screen-shaped) 그대로의 불변 행이다. 질의 포트는 도메인 엔티티
(``Run``/``SuiteRun``)를 절대 반환하지 않는다 — 목록·집계·팬아웃 경로에서 blob 재수화를
타입 수준에서 봉쇄하는 것이 이 모듈의 존재 이유다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus


@dataclass(frozen=True)
class AnomalyInboxRow:
    module_run_id: str
    run_id: str
    module_id: str
    system_code: str
    status: ModuleStatus
    ended_at: datetime | None
    created_by_user_id: str | None


@dataclass(frozen=True)
class DailyStatusRow:
    day_key: str
    system_code: str
    module_id: str
    last_status: ModuleStatus
    last_run_id: str | None
    duration_ms: int | None
    updated_at: datetime


@dataclass(frozen=True)
class DailyRunSummaryRow:
    run_id: str
    system_code: str
    status: RunStatus
    requested_at: datetime
    triggered_by: str


@dataclass(frozen=True)
class StatsRollupRow:
    day_key: str
    system_code: str
    passed_count: int
    anomaly_count: int
    error_count: int
    cancelled_count: int


@dataclass(frozen=True)
class Page:
    """LIMIT/OFFSET 페이지 파라미터(정렬은 포트 계약상 requested_at DESC 고정)."""

    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class RunSummaryFilter:
    """Run 요약 목록 질의 필터 — 전부 SQL WHERE 로 내려간다(파이썬 후처리 금지)."""

    system_code: str | None = None
    system_codes: frozenset[str] | None = None
    statuses: frozenset[RunStatus] | None = None
    user_id: str | None = None
    user_name_query: str | None = None
    schedule_id: str | None = None
    suite_id: str | None = None
    requested_since: datetime | None = None
    requested_before: datetime | None = None
    schedule_tagged_only: bool = False
    triggered_by: str | None = None
    run_id_query: str | None = None


@dataclass(frozen=True)
class RunSummaryRow:
    """``run_history_index`` 한 행 — 목록 화면("진행 중 / 최근 Run")이 쓰는 모양 그대로."""

    run_id: str
    system_code: str
    system_name: str | None
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    schedule_id: str | None
    suite_id: str | None
    created_by_user_id: str | None
    created_by_user_name: str | None
    triggered_by: str
    awaiting_input_module_id: str | None
    awaiting_input_prompt: str | None
    module_total: int
    module_defined_total: int
    module_skipped: int
    module_passed: int
    current_module_name: str | None
    failed_module_name: str | None


@dataclass(frozen=True)
class ModuleHistoryRow:
    """``module_history_index`` 한 행 — 인사이트/통계/일간 소요시간의 모듈 실행 이력."""

    run_id: str
    module_id: str
    system_code: str
    module_name: str | None
    status: ModuleStatus
    message: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    current_url: str | None
    artifacts: tuple[str, ...]
    ai_category: str | None
    ai_summary: str | None
    ai_action: str | None
    suite_id: str | None
    schedule_id: str | None
    triggered_by: str | None
    requested_at: datetime | None
    created_by_user_id: str | None
    created_by_user_name: str | None


@dataclass(frozen=True)
class RunComparisonRow:
    """``run_comparison_cache`` 한 행 — 직전 Run 대비 모듈 상태 변화."""

    run_id: str
    baseline_run_id: str | None
    newly_failed: tuple[str, ...]
    recovered: tuple[str, ...]
    still_failing: tuple[str, ...]


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
