"""사용량 통계 읽기 모델 + 모듈 설정."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SystemUsageStat(BaseModel):
    system_code: str
    system_name: str
    runs: int
    modules_passed: int
    modules_failed: int
    total_duration_ms: int
    manual_seconds_saved: int


class UserUsageStat(BaseModel):
    user_id: str | None
    user_name: str | None
    email: str | None
    total_runs: int
    total_modules_passed: int
    total_modules_failed: int
    total_duration_ms: int
    manual_seconds_saved: int
    by_system: list[SystemUsageStat]


class UsageStats(BaseModel):
    period_from: datetime | None
    period_to: datetime | None
    generated_at: datetime
    total_runs: int
    total_users: int
    by_user: list[UserUsageStat]
    by_system: list[SystemUsageStat]
    charts: dict[str, Any] = Field(default_factory=dict)


class ModuleSettings(BaseModel):
    module_id: str
    estimated_manual_seconds: int
    updated_at: datetime
