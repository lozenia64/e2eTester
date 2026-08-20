"""사용량 통계 읽기 모델 + 모듈 설정."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class SavingsSummary(BaseModel):
    """절감 시간 요약(비관리자 노출용).

    사용자별 분해를 담지 않는다 — ``UserUsageStat`` 은 이름·이메일을 포함하므로
    전직원에게 열면 "누가 얼마나 돌렸나"가 노출된다. 전사 합계와 본인 기여분만 담는다.
    """

    total_seconds: int
    my_seconds: int
    run_count: int
    module_count: int
    basis_updated_at: datetime | None
    estimated: bool
    note: str

    @model_validator(mode="after")
    def _estimated_requires_note(self) -> SavingsSummary:
        if self.estimated and not self.note.strip():
            msg = "estimated=True 인 지표는 산출 근거(note)가 있어야 한다."
            raise ValueError(msg)
        return self
