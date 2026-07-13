"""시스템/모듈 정의 모델 — 매니페스트에서 로드되는 정적 구조(레지스트리 입력)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import ModuleStatus


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
    max_retries: int = 0
    retry_backoff_ms: int = 500
    retryable_on: list[str] = Field(default_factory=lambda: [ModuleStatus.ERROR.value])
    partial_rerun_allowed: bool = True


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
    execution_profile: str = "light"
