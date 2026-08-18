"""Insights 컨텍스트 읽기 모델 쿼리 행(row) 타입."""

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
    duration_ms: int | None
    updated_at: datetime
    # 자동 복구 가시성(설계 §3.4) — 재시도를 거쳐 통과했는지. 과거(마이그레이션 이전) 행은
    # NULL 이므로 어댑터가 False 로 읽는다.
    recovered: bool = False


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
