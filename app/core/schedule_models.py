"""예약(Schedule) 도메인 엔티티 + 변경 이력 + 프레젠테이션 프로젝션."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.enums import RunStatus, SuiteStatus

SUITE_SCHEDULE_SYSTEM_CODE = "suite"
SUITE_SCHEDULE_SYSTEM_NAME = "전체 시스템 순차 점검"

# 예약 change_log 보존 한도(오래된 항목부터 잘려 나간다 — blob 비대 방지).
SCHEDULE_CHANGE_LOG_LIMIT = 30


class ScheduleChangeEntry(BaseModel):
    """예약 변경 이력 한 건(누가 언제 무엇을 바꿨나 — 예약 관리 센터 상세에 노출)."""

    at: datetime
    action: str  # created / updated / enabled / disabled / paused / pause_cleared / auto_resumed / duplicated
    detail: str = ""
    user_name: str | None = None


class Schedule(BaseModel):
    schedule_id: str
    schedule_kind: str = "system"
    system_code: str
    system_name: str
    name: str = ""
    cron: str
    timezone: str
    enabled: bool = True
    # 모바일 즉시 점검 URL(/m/{token}) 인증용 예약별 비밀 토큰. 예약 삭제가 곧 URL 폐기다.
    # to_summary 로는 소유자 화면(URL 복사 버튼)에만 노출되고 응답 어디에도 로그로 남기지 않는다.
    trigger_token: str | None = None
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    browser_mode: str | None = None
    suite_systems: dict[str, dict[str, str]] | None = None
    selected_system_codes: list[str] | None = None
    scope_system_codes: list[str] | None = None
    step_total: int | None = None
    created_at: datetime
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_id: str | None = None
    last_run_status: RunStatus | None = None
    last_suite_id: str | None = None
    last_suite_status: SuiteStatus | None = None
    # --- 예약 점검 관리 센터(관제 보드/라이프사이클) 필드 ---------------------
    # cron 주기가 왔지만 직전 실행이 진행 중이라 건너뛴 마지막 시각(관제 보드 '실행 누락' 신호).
    last_skipped_at: datetime | None = None
    # 이 시각까지 일시 중지(사이트 정기점검 기간 등). enabled 와 별개로 발사를 게이트하며,
    # 시각이 지나면 스케줄러 tick 이 자동으로 해제(자동 재개)한다.
    paused_until: datetime | None = None
    # 마지막으로 비활성화된 시각(관제 보드 '꺼진 지 오래' 판정용).
    disabled_at: datetime | None = None
    updated_at: datetime | None = None
    change_log: list[ScheduleChangeEntry] = Field(default_factory=list)

    def record_change(
        self,
        action: str,
        detail: str = "",
        user_name: str | None = None,
        at: datetime | None = None,
    ) -> None:
        """변경 이력을 append 하고 보존 한도를 넘는 오래된 항목을 잘라낸다."""
        self.change_log.append(
            ScheduleChangeEntry(
                at=at or datetime.now(UTC),
                action=action,
                detail=detail,
                user_name=user_name,
            )
        )
        if len(self.change_log) > SCHEDULE_CHANGE_LOG_LIMIT:
            self.change_log = self.change_log[-SCHEDULE_CHANGE_LOG_LIMIT:]

    def to_summary(self) -> dict:
        """API/UI 노출용 요약. input_data 는 PII 가 있을 수 있어 직렬화하지 않는다."""
        is_suite = self.schedule_kind == "suite"
        return {
            "schedule_id": self.schedule_id,
            "schedule_kind": self.schedule_kind,
            "system_code": self.system_code,
            "system_name": self.system_name,
            "name": self.name,
            "cron": self.cron,
            "timezone": self.timezone,
            "enabled": self.enabled,
            "trigger_token": self.trigger_token,
            "selected_module_ids": list(self.selected_module_ids or []),
            "module_count": len(self.selected_module_ids)
            if self.selected_module_ids is not None
            else None,
            "step_total": self.step_total if is_suite else None,
            "selected_system_codes": list(self.selected_system_codes or []) if is_suite else [],
            "selected_system_count": len(self.selected_system_codes)
            if is_suite and self.selected_system_codes is not None
            else None,
            "browser_mode": self.browser_mode if is_suite else None,
            "auth_method": None if is_suite else self.input_data.get("auth_method"),
            "created_at": self.created_at.isoformat(),
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_id": self.last_run_id,
            "last_run_status": self.last_run_status.value if self.last_run_status else None,
            "last_suite_id": self.last_suite_id,
            "last_suite_status": self.last_suite_status.value if self.last_suite_status else None,
            "last_skipped_at": self.last_skipped_at.isoformat() if self.last_skipped_at else None,
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
            "disabled_at": self.disabled_at.isoformat() if self.disabled_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_detail(self) -> dict:
        """상세 드로어용 — 요약 + 변경 이력 + 수정 폼 보조 정보.

        input_data 값(PII)은 여기서도 직렬화하지 않는다. 수정 폼이 "저장된 값 유지 / 새 값으로
        교체"를 구분할 수 있도록 어떤 키가 저장돼 있는지(키 이름)만 노출한다.
        """
        payload = self.to_summary()
        payload["change_log"] = [
            {
                "at": entry.at.isoformat(),
                "action": entry.action,
                "detail": entry.detail,
                "user_name": entry.user_name,
            }
            for entry in reversed(self.change_log)
        ]
        payload["input_data_keys"] = sorted(self.input_data.keys())
        payload["created_by_user_name"] = self.created_by_user_name
        return payload
