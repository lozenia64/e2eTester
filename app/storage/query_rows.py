"""읽기 모델 쿼리 포트가 반환하는 행(row) 타입."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.enums import ModuleStatus, RunStatus


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
