"""Run 커맨드 — Decider ``decide(cmd, state) -> events`` 의 입력 의도(intent).

각 커맨드는 애그리거트의 합법 상태 전이 하나에 대응한다. 커맨드는 **의도**만 담고(불변
frozen dataclass), 결과 이벤트 산출은 ``app/domain/run_decider.py:decide`` 가, 상태 유도는
``evolve`` 가 책임진다. 결정 규칙(취소 관측·선행 차단·OTP 정책·재시도)은 ``RunStateMachine``
이 판정하고, 그 결정이 어떤 커맨드로 이어질지는 인터프리터(``RunService``)가 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import FailureAnalysis, RunComparison


@dataclass(frozen=True)
class BeginRun:
    """Run 실행 시작(PENDING → RUNNING)."""


@dataclass(frozen=True)
class BlockModule:
    """선행 실패로 모듈을 BLOCKED 처리."""

    module_id: str


@dataclass(frozen=True)
class QueueModule:
    module_id: str


@dataclass(frozen=True)
class StartModule:
    module_id: str


@dataclass(frozen=True)
class RecordStepResult:
    """게이트웨이 실행 결과를 모듈에 기록하고 종료 시각을 확정한다(정상 종료 경로)."""

    module_id: str
    status: ModuleStatus
    message: str
    artifacts: tuple[str, ...] = ()
    current_url: str | None = None
    dialog_messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailModule:
    """단계 진입 전/도중 플랫폼 오류로 모듈을 ERROR 종료."""

    module_id: str
    message: str


@dataclass(frozen=True)
class MarkModuleFatal:
    """예상치 못한 실행 오류를 특정 모듈에 귀속해 ERROR 처리."""

    module_id: str
    message: str


@dataclass(frozen=True)
class RetryModule:
    """정책상 재시도 — attempt 증가 후 재큐잉."""

    module_id: str


@dataclass(frozen=True)
class PauseForInput:
    """OTP 등 사용자 입력 대기로 Run 을 WAITING_INPUT 일시정지."""

    module_id: str
    message: str
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResumeAfterInput:
    """입력 접수로 재개 대기(WAITING_INPUT → RUNNING, 모듈 재큐잉)."""

    module_id: str


@dataclass(frozen=True)
class CancelModules:
    """아직 끝나지 않은 모듈들을 사용자 취소로 종료."""

    module_ids: tuple[str, ...]


@dataclass(frozen=True)
class PreparePartialRerun:
    """지정 인덱스부터 모듈 상태를 초기화하고 Run 을 재개."""

    from_index: int


@dataclass(frozen=True)
class AttachComparison:
    comparison: RunComparison


@dataclass(frozen=True)
class AttachFailureAnalysis:
    module_id: str
    analysis: FailureAnalysis | None


@dataclass(frozen=True)
class FinalizeRun:
    """Run 을 종료 상태로 봉인(강제 상태가 있으면 우선)."""

    forced_status: RunStatus | None = None


@dataclass(frozen=True)
class SealInterrupted:
    """재기동으로 이어받을 수 없는 진행 중 Run 을 CANCELLED 로 봉인."""


RunCommand = (
    BeginRun
    | BlockModule
    | QueueModule
    | StartModule
    | RecordStepResult
    | FailModule
    | MarkModuleFatal
    | RetryModule
    | PauseForInput
    | ResumeAfterInput
    | CancelModules
    | PreparePartialRerun
    | AttachComparison
    | AttachFailureAnalysis
    | FinalizeRun
    | SealInterrupted
)
