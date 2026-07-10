from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import AnomalyState, ModuleStatus, RunStatus, SuiteStatus


class ModuleDefinition(BaseModel):
    module_id: str
    system_code: str
    name: str
    description: str
    group: str
    order: int
    depends_on: list[str] = Field(default_factory=list)
    timeout_seconds: int = 180
    simulated_duration_ms: int = 1800
    simulated_outcome: str = "PASSED"
    execution_mode: str = "simulated"
    script_path: str | None = None
    workflow_name: str | None = None
    workflow_step: str | None = None
    estimated_manual_seconds: int = 0
    # 이 모듈이 실행 도중 사람 입력(휴대폰 OTP 등)을 요구해 Run 을 WAITING_INPUT 으로
    # 일시정지시킬 수 있는지를 **매니페스트가 선언**한다(일시정지 '정책'의 단일 출처). 실행
    # 어댑터는 입력이 필요하다는 '사실'(StepNeedsInput)만 보고할 뿐, 일시정지를 '허가'하는
    # 권한은 도메인이 이 플래그로 가진다 — 선언하지 않은 모듈의 입력 요구는 정책 위반(ERROR).
    requires_user_input: bool = False


class RunFormOption(BaseModel):
    label: str
    value: str


class RunFormField(BaseModel):
    key: str
    label: str
    type: str = "text"
    required: bool = False
    placeholder: str = ""
    default: str = ""
    help_text: str = ""
    options: list[RunFormOption] = Field(default_factory=list)
    show_when: dict[str, str | list[str]] = Field(default_factory=dict)


class SystemDefinition(BaseModel):
    system_code: str
    name: str
    description: str
    modules: list[ModuleDefinition]
    run_form: list[RunFormField] = Field(default_factory=list)
    supported_auth_methods: list[str] = Field(default_factory=list)
    # 홈 화면 시스템 카드 노출 순서(작을수록 먼저). 미지정 시 뒤로 밀린다.
    display_order: int = 1000


class FailureAnalysis(BaseModel):
    category: str
    probable_cause: str
    retryable: bool
    user_summary: str
    developer_details: str
    recommended_action: str
    provider: str | None = None
    model: str | None = None


class RunModule(BaseModel):
    module_id: str
    name: str
    group: str
    order: int
    status: ModuleStatus = ModuleStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    message: str = "대기 중"
    artifact_count: int = 0
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    # 모듈 종료 시점의 진단 컨텍스트. Run 종료 후 AI 실패 분석 구독자가 실행 컨텍스트
    # 없이 분석을 재구성할 수 있도록 모듈에 영속한다.
    current_url: str | None = None
    dialog_messages: list[str] = Field(default_factory=list)
    failure_analysis: FailureAnalysis | None = None


class FailureAnalysisRequest(BaseModel):
    run_id: str
    system_code: str
    system_name: str
    module_id: str
    module_name: str
    module_group: str
    execution_mode: str
    workflow_name: str | None = None
    workflow_step: str | None = None
    current_url: str | None = None
    last_error: str | None = None
    recent_logs: list[str] = Field(default_factory=list)
    dialog_messages: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None
    system_definition: dict = Field(default_factory=dict)


class RunComparison(BaseModel):
    """직전 Run(같은 시스템) 대비 모듈 상태 변화 요약."""

    has_baseline: bool = False
    baseline_run_id: str | None = None
    baseline_requested_at: datetime | None = None
    newly_failed: list[str] = Field(default_factory=list)
    recovered: list[str] = Field(default_factory=list)
    still_failing: list[str] = Field(default_factory=list)


class AnomalyHandling(BaseModel):
    """한 이상건(ANOMALY/ERROR 모듈)의 **처리 레코드**(이상징후 인박스 전용 영속 상태).

    Run 은 시간순 실행 기록이라 "누가 봤고 조치했는지"를 담지 못하므로, 모듈-Run 단위로
    처리상태·담당자·메모를 별도 스토어(``AnomalyHandlingStorePort``)에 둔다. 스토어에 행이 없는
    이상건은 기본 ``UNRESOLVED`` 로 간주하므로, 정상적으로 처리 안 된 이상건까지 미리 행을
    만들지 않는다(사용자가 처음 상태를 바꿀 때 upsert).
    """

    # f"{run_id}::{module_id}" — 이상건(모듈 실행 1건)의 안정적 식별자.
    module_run_id: str
    state: AnomalyState = AnomalyState.UNRESOLVED
    assignee_user_id: str | None = None
    assignee_name: str | None = None
    memo: str = ""
    updated_at: datetime | None = None
    updated_by_user_id: str | None = None


class PendingExecution(BaseModel):
    """OTP 일시정지된 Run 의 **재개 컨텍스트**(비-PII 제어 메타데이터).

    라이브 브라우저는 게이트웨이 ``session_id`` 토큰으로만 가리키며, 이 토큰은 같은 프로세스
    수명 안에서만 유효하다(재기동하면 dangling → ``reconcile_interrupted_runs`` 가 봉인).
    PII 입력값은 여기 담지 않고 ``RunInputStorePort`` 가 따로 보관한다. OTP 값도 담지 않는다
    (재개 시 OTP 는 게이트웨이가 런타임에 주입한 ``runtime.config`` 에서 읽는다).
    """

    session_id: str
    execution_mode: str
    resume_index: int
    module_id: str


class Run(BaseModel):
    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    modules: list[RunModule]
    selected_module_ids: list[str] = Field(default_factory=list)
    awaiting_input_module_id: str | None = None
    awaiting_input_prompt: str | None = None
    triggered_by: str = "manual"
    schedule_id: str | None = None
    suite_id: str | None = None
    comparison: RunComparison | None = None
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None


SUITE_SCHEDULE_SYSTEM_CODE = "suite"
SUITE_SCHEDULE_SYSTEM_NAME = "전체 시스템 순차 점검"


class ScheduleChangeEntry(BaseModel):
    """예약 변경 이력 한 건(누가 언제 무엇을 바꿨나 — 예약 관리 센터 상세에 노출)."""

    at: datetime
    action: str  # created / updated / enabled / disabled / paused / pause_cleared / auto_resumed / duplicated
    detail: str = ""
    user_name: str | None = None


# 예약 change_log 보존 한도(오래된 항목부터 잘려 나간다 — blob 비대 방지).
SCHEDULE_CHANGE_LOG_LIMIT = 30


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


class AuthPreset(BaseModel):
    """사용자별·시스템별 **인증 프리셋**(자주 쓰는 인증 수단·정보 저장 세트).

    매번 점검 폼에 인증 정보를 다시 입력하는 반복을 없애기 위해, 사용자가 이름을 붙여 저장한
    인증 수단 + 인증 정보(+선택 모듈)를 담는다. 개별 점검에서는 프리셋 클릭 한 번으로 폼을
    채우고, 전체 점검에서는 시스템별로 프리셋을 골라 인증 정보를 공급한다.

    ``input_data`` 에는 이름·생년월일·휴대폰 등 **PII 가 포함**될 수 있다 — 프리셋의 존재
    목적 자체가 인증 정보의 영속 저장이므로, Run/Suite 의 휘발성 입력 스토어와 달리 SQLite 에
    영속한다. 대신 소유자(``user_id``)만 조회/수정/삭제할 수 있도록 서비스·라우트가 엄격히
    소유권을 강제하고, 응답에는 소유자 본인에게만 ``input_data`` 를 돌려준다.
    """

    preset_id: str
    user_id: str
    system_code: str
    system_name: str
    name: str
    auth_method: str = ""
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    def to_public(self) -> dict:
        """소유자 화면용 프로젝션. 폼 자동 채움을 위해 ``input_data`` 를 포함한다(소유자 전용)."""
        return {
            "preset_id": self.preset_id,
            "system_code": self.system_code,
            "system_name": self.system_name,
            "name": self.name,
            "auth_method": self.auth_method,
            "input_data": dict(self.input_data),
            "selected_module_ids": list(self.selected_module_ids)
            if self.selected_module_ids is not None
            else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class CreatePresetRequest(BaseModel):
    system_code: str
    name: str
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None


class UpdatePresetRequest(BaseModel):
    name: str | None = None
    input_data: dict[str, str] | None = None
    selected_module_ids: list[str] | None = None


class DashboardEvent(BaseModel):
    event_type: str
    run_id: str
    system_code: str
    run_status: RunStatus
    payload: dict


class StartRunRequest(BaseModel):
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None


class SubmitOtpRequest(BaseModel):
    otp_code: str


class InboundOtpRequest(BaseModel):
    """SMS 중계기(안드로이드/문자 포워더)가 보내는 인바운드 OTP 요청.

    ``run_id`` 없이 코드만 보낸다(중계기는 어느 Run 이 대기 중인지 모른다). ``code`` 가 오면
    그대로 쓰고, 없으면 ``text``(SMS 원문)를 서버가 정규식으로 파싱한다.
    """

    code: str | None = None
    text: str | None = None


class CreateScheduleRequest(BaseModel):
    cron: str
    name: str = ""
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    enabled: bool = True


class CreateSuiteScheduleRequest(BaseModel):
    cron: str
    name: str = ""
    browser_mode: str = "headed"
    systems: dict[str, dict[str, str]] = Field(default_factory=dict)
    selected_system_codes: list[str] | None = None
    scope_system_codes: list[str] | None = None
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    """예약 in-place 수정 요청 — None 인 필드는 기존 값을 유지한다.

    ``input_data`` 는 제공된 키만 덮어쓴다(빈 문자열 값은 무시). 저장된 인증값(PII)을
    화면에 되돌려주지 않고도 교체할 수 있게 하는 병합 규약이다.
    """

    name: str | None = None
    cron: str | None = None
    input_data: dict[str, str] | None = None
    selected_module_ids: list[str] | None = None
    # suite 예약 전용
    browser_mode: str | None = None
    selected_system_codes: list[str] | None = None


class PauseScheduleRequest(BaseModel):
    """일시 중지(~시각까지) 요청. ``paused_until=None`` 은 즉시 재개."""

    paused_until: datetime | None = None


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


class StartSuiteRequest(BaseModel):
    browser_mode: str = "headed"
    systems: dict[str, dict[str, str]] = Field(default_factory=dict)
    selected_system_codes: list[str] | None = None
    scope_system_codes: list[str] | None = None
