"""Suite 커맨드 — Suite Decider ``decide(cmd, state) -> events`` 의 입력 의도(intent).

``RunCommand`` 와 동형. 각 커맨드는 ``SuiteAggregate`` 의 합법 상태 전이 하나에 대응한다.
스텝은 인덱스로 지목한다(불변 상태에는 객체 참조가 없으므로).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import SuiteStatus


@dataclass(frozen=True)
class BeginSuite:
    """Suite 실행 시작(PENDING → RUNNING)."""


@dataclass(frozen=True)
class StartStep:
    index: int


@dataclass(frozen=True)
class LinkRun:
    step_index: int
    run_id: str


@dataclass(frozen=True)
class MarkStepError:
    step_index: int
    error: str


@dataclass(frozen=True)
class RecordStepResult:
    step_index: int
    status: SuiteStatus


@dataclass(frozen=True)
class MarkWaitingInput:
    run_id: str
    prompt: str | None


@dataclass(frozen=True)
class MarkResumed:
    """하위 Run 재개 → Suite RUNNING 복귀."""


@dataclass(frozen=True)
class FinalizeSuite:
    status: SuiteStatus
    cancel_remaining: bool = False


@dataclass(frozen=True)
class SealInterrupted:
    """재기동으로 이어받을 수 없는 진행 중 Suite 를 CANCELLED 로 봉인."""


SuiteCommand = (
    BeginSuite
    | StartStep
    | LinkRun
    | MarkStepError
    | RecordStepResult
    | MarkWaitingInput
    | MarkResumed
    | FinalizeSuite
    | SealInterrupted
)
