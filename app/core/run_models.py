"""Run 도메인 엔티티 + 실행 관련 DTO(모듈·비교·재개 컨텍스트·이상건·실시간 이벤트)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import AnomalyState, ModuleStatus, RunStatus


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
    attempt: int = 1
    max_attempts: int = 1
    message: str = "대기 중"
    artifact_count: int = 0
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    # 모듈 종료 시점의 진단 컨텍스트. Run 종료 후 AI 실패 분석 구독자가 실행 컨텍스트
    # 없이 분석을 재구성할 수 있도록 모듈에 영속한다.
    current_url: str | None = None
    dialog_messages: list[str] = Field(default_factory=list)
    # 자동 복구 가시성(설계 §3.4). "통과했다"와 "불안정하다"는 직교하는 축이므로,
    # 상태(PASSED/ANOMALY/ERROR)를 건드리지 않고 별도 필드로 표현한다.
    recovered: bool = False
    recovery_tiers: list[int] = Field(default_factory=list)
    failure_signals: list[str] = Field(default_factory=list)
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
    # OTP 대기(WAITING_INPUT) 진입 시각. SMS 중계의 대기 Run 자동 탐색이 "방금 도착한 SMS 에
    # 대응하는 Run" = 가장 최근에 대기에 들어간 Run 을 고르는 정렬 키다(Run 생성 시각은 잘못된
    # 프록시 — 먼저 생성됐지만 나중에 멈춘 Run 이 있으면 오주입된다). 레거시 행은 None.
    paused_at: datetime | None = None


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


class DashboardEvent(BaseModel):
    event_type: str
    run_id: str
    system_code: str
    run_status: RunStatus
    payload: dict
