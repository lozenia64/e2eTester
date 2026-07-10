"""영속(persistence) DTO 와 도메인 ↔ 레코드 매퍼.

도메인 엔티티(``Run``/``RunModule``/``SuiteRun``/``SuiteStep``)와 **온디스크 직렬화 스키마**를
명시적으로 분리하는 계층이다. 과거에는 저장소 어댑터가 도메인 엔티티를 그대로
``model_dump_json(exclude=...)`` 해서 영속했다 — 즉 *영속 스키마 = 도메인 모델 − 매직 exclude*
였고, 그 exclude 규칙("로그는 blob 에 담지 않는다")이 SQLite·인메모리 어댑터마다 **중복**됐다
(``_PERSIST_EXCLUDE`` / ``_persist_copy``). 그 결과 도메인 모델이 곧 DB blob 이라, 도메인 전용
필드를 하나 추가하면 그것이 그대로 디스크 스키마로 새어 나갔다.

이 모듈은 영속 스키마를 **1급 아티팩트**로 만든다:

- ``RunModuleRecord`` 에는 ``logs`` 필드가 **구조적으로 없다**. 모듈 로그는 별도 집합체
  (``RunLogStorePort``)가 소유하므로, 어댑터의 방어적 exclude 가 아니라 **타입 수준 사실**로
  blob 에 담길 수 없다.
- 매퍼(``from_domain``/``to_domain``)가 도메인 ↔ 영속 변환의 단일 경로다. 어댑터는 더 이상
  도메인 엔티티를 직접 직렬화하지 않고 이 레코드만 (역)직렬화한다.

디스크 JSON 형태는 종전(``Run.model_dump_json(exclude=logs)`` / ``SuiteRun.model_dump_json``)과
**동일**하므로 기존 SQLite 데이터와 정·역방향 호환된다(필드 집합이 일치).

Suite 쪽은 현재 도메인-전용 필드가 없어 레코드 형태가 도메인과 일치하지만, 영속 seam 을 Run 과
**동일하게** 두어 (1) 독립 진화 가능성을 열고 (2) 인메모리 어댑터가 도메인 객체를 공유 참조로
보관하던 잠재적 value-semantics 버그를 레코드 정규화로 함께 해소한다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.models import (
    FailureAnalysis,
    Run,
    RunComparison,
    RunModule,
    SuiteRun,
    SuiteStep,
)


class RunModuleRecord(BaseModel):
    """``RunModule`` 의 영속 스키마. **``logs`` 필드가 없다**(별도 집합체 소유)."""

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
    current_url: str | None = None
    dialog_messages: list[str] = Field(default_factory=list)
    failure_analysis: FailureAnalysis | None = None

    @classmethod
    def from_domain(cls, module: RunModule) -> RunModuleRecord:
        # logs 는 이 스키마에 없으므로(타입 수준) model_validate 가 자연히 떨어뜨린다.
        return cls.model_validate(module.model_dump(exclude={"logs"}))

    def to_domain(self) -> RunModule:
        # 읽기 모델의 로그는 RunService.get_run 이 로그 스토어에서 하이드레이션한다(여기선 빈 값).
        return RunModule.model_validate({**self.model_dump(), "logs": []})


class RunRecord(BaseModel):
    """``Run`` 상태 집합체의 영속 스키마(모듈 로그 제외)."""

    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    modules: list[RunModuleRecord]
    selected_module_ids: list[str] = Field(default_factory=list)
    awaiting_input_module_id: str | None = None
    awaiting_input_prompt: str | None = None
    triggered_by: str = "manual"
    schedule_id: str | None = None
    suite_id: str | None = None
    comparison: RunComparison | None = None
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None

    @classmethod
    def from_domain(cls, run: Run) -> RunRecord:
        return cls(
            **run.model_dump(exclude={"modules"}),
            modules=[RunModuleRecord.from_domain(module) for module in run.modules],
        )

    def to_domain(self) -> Run:
        return Run(
            **self.model_dump(exclude={"modules"}),
            modules=[module.to_domain() for module in self.modules],
        )

    @classmethod
    def deserialize(cls, data: str) -> Run:
        return cls.model_validate_json(data).to_domain()

    @staticmethod
    def serialize(run: Run) -> str:
        return RunRecord.from_domain(run).model_dump_json()


class SuiteStepRecord(BaseModel):
    """``SuiteStep`` 의 영속 스키마."""

    system_code: str
    system_name: str
    order: int
    run_id: str | None = None
    status: SuiteStatus = SuiteStatus.PENDING
    module_total: int = 0

    @classmethod
    def from_domain(cls, step: SuiteStep) -> SuiteStepRecord:
        return cls.model_validate(step.model_dump())

    def to_domain(self) -> SuiteStep:
        return SuiteStep.model_validate(self.model_dump())


class SuiteRecord(BaseModel):
    """``SuiteRun`` 집합체의 영속 스키마."""

    suite_id: str
    status: SuiteStatus
    steps: list[SuiteStepRecord]
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
    triggered_by: str = "manual"
    schedule_id: str | None = None

    @classmethod
    def from_domain(cls, suite: SuiteRun) -> SuiteRecord:
        return cls(
            **suite.model_dump(exclude={"steps"}),
            steps=[SuiteStepRecord.from_domain(step) for step in suite.steps],
        )

    def to_domain(self) -> SuiteRun:
        return SuiteRun(
            **self.model_dump(exclude={"steps"}),
            steps=[step.to_domain() for step in self.steps],
        )

    @classmethod
    def deserialize(cls, data: str) -> SuiteRun:
        return cls.model_validate_json(data).to_domain()

    @staticmethod
    def serialize(suite: SuiteRun) -> str:
        return SuiteRecord.from_domain(suite).model_dump_json()
