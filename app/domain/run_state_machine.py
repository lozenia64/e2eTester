"""Run 실행 루프의 **결정 규칙(명시적 전이표)** 을 소유하는 순수 도메인 컴포넌트.

과거에는 "다음에 무엇을 할지"라는 결정이 ``RunService._execute_run_inner`` 의 긴 절차적
for 루프 안에 if/return 분기로 흩어져 있었다(취소 관측·선행 차단·OTP 일시정지·결과 기록이
I/O 와 뒤섞여, 상태머신이 코드 형태로만 존재했다). 이 모듈은 그 **결정(decision)** 을
**효과(effect)** 와 분리해, ``(상태·신호) → 명령`` 으로 매핑하는 명시적 표로 끌어낸다.

- 결정(이 파일): 순수 함수. ``await`` 없음, 저장소/게이트웨이/이벤트 import 없음 → 브라우저·DB
  없이 단독 단위 테스트(``tests/test_run_state_machine.py``).
- 효과(``RunService``): 결정을 받아 ``save_run``·WS 이벤트·게이트웨이 호출 같은 I/O 만 수행한다.

전이표(요약):

  모듈 진입(decide_module_entry):
    cancel_requested                      → CancelRemaining
    not dependencies_satisfied            → BlockModule
    그 외                                  → ExecuteModule

  단계 종료 후(decide_post_step):
    status == WAITING_INPUT 이고
        not module_requires_user_input    → RejectUnexpectedInput  (정책 위반)
        cancel_requested                  → CancelRemaining
        그 외                              → PauseForInput
    그 외(정상/실패 종료)                   → CompleteStep

  단계 실패 후(decide_post_step_failure):
    cancel_requested                      → CancelRemaining
    retryable 이고 attempt < max_attempts → RetryModule
    그 외                                  → CompleteStep

  부분 재실행(decide_partial_rerun):
    invalid module / not allowed          → RejectInvalidResumePoint
    그 외                                  → ResumeFromModule
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ModuleStatus

# --- 모듈 진입 결정 ----------------------------------------------------------


@dataclass(frozen=True)
class CancelRemaining:
    """취소 의도가 관측됨 → 남은 모듈을 CANCELLED 로 봉인하고 Run 을 종료한다."""


@dataclass(frozen=True)
class BlockModule:
    """선행 모듈이 PASSED 가 아님 → 이 모듈을 BLOCKED 처리하고 다음으로 넘어간다."""


@dataclass(frozen=True)
class ExecuteModule:
    """정상 진행 → 큐잉·실행 단계로 들어간다."""


ModuleEntryDecision = CancelRemaining | BlockModule | ExecuteModule


# --- 단계 종료 후 결정 -------------------------------------------------------


@dataclass(frozen=True)
class PauseForInput:
    """단계가 사람 입력을 요구하고 정책상 허용됨 → Run 을 WAITING_INPUT 으로 일시정지한다."""


@dataclass(frozen=True)
class CompleteStep:
    """단계 결과(정상/실패)를 모듈에 기록하고 종료한다."""


@dataclass(frozen=True)
class RejectUnexpectedInput:
    """입력을 선언하지 않은(``requires_user_input=False``) 모듈이 입력을 요구함.

    매니페스트가 일시정지를 허가하지 않았으므로 도메인 정책 위반이다 → ERROR 로 종료한다
    (과거에는 무한 일시정지로 빠질 수 있었다).
    """


PostStepDecision = CancelRemaining | PauseForInput | CompleteStep | RejectUnexpectedInput


# --- 단계 실패 후 결정(재시도 정책) ------------------------------------------


@dataclass(frozen=True)
class RetryModule:
    """정책상 재시도 가능 → 백오프 후 같은 모듈을 다시 실행한다."""

    backoff_ms: int


PostStepFailureDecision = CancelRemaining | PauseForInput | CompleteStep | RetryModule


# --- 부분 재실행 결정 --------------------------------------------------------


@dataclass(frozen=True)
class ResumeFromModule:
    """지정 모듈부터 Run 을 재개한다."""

    from_index: int


@dataclass(frozen=True)
class RejectInvalidResumePoint:
    """부분 재실행이 허용되지 않거나 모듈이 유효하지 않다."""


PartialRerunDecision = ResumeFromModule | RejectInvalidResumePoint


class RunStateMachine:
    """Run 실행의 결정 규칙(전이표). 상태(불리언/상태값)만 받아 명령을 돌려주는 순수 함수 모음.

    상태 *변경* 은 ``RunAggregate`` 가, 결정의 *실행*(I/O) 은 ``RunService`` 가 책임진다. 이
    컴포넌트는 오직 "무엇을 할지"만 결정한다.
    """

    @staticmethod
    def decide_module_entry(
        *, cancel_requested: bool, dependencies_satisfied: bool
    ) -> ModuleEntryDecision:
        if cancel_requested:
            return CancelRemaining()
        if not dependencies_satisfied:
            return BlockModule()
        return ExecuteModule()

    @staticmethod
    def decide_post_step(
        *,
        step_status: ModuleStatus,
        cancel_requested: bool,
        module_requires_user_input: bool,
    ) -> PostStepDecision:
        if step_status is ModuleStatus.WAITING_INPUT:
            if not module_requires_user_input:
                return RejectUnexpectedInput()
            if cancel_requested:
                return CancelRemaining()
            return PauseForInput()
        return CompleteStep()

    @staticmethod
    def decide_post_step_failure(
        *,
        step_status: ModuleStatus,
        cancel_requested: bool,
        current_attempt: int,
        max_attempts: int,
        retryable_on: frozenset[ModuleStatus],
        backoff_ms: int,
    ) -> PostStepFailureDecision:
        if cancel_requested:
            return CancelRemaining()
        if step_status is ModuleStatus.WAITING_INPUT:
            return CompleteStep()
        if step_status is ModuleStatus.PASSED:
            return CompleteStep()
        if step_status in retryable_on and current_attempt < max_attempts:
            return RetryModule(backoff_ms=backoff_ms)
        return CompleteStep()

    @staticmethod
    def decide_partial_rerun(
        *,
        from_module_id: str,
        module_ids_in_order: list[str],
        partial_rerun_allowed: bool,
    ) -> PartialRerunDecision:
        if from_module_id not in module_ids_in_order:
            return RejectInvalidResumePoint()
        if not partial_rerun_allowed:
            return RejectInvalidResumePoint()
        return ResumeFromModule(from_index=module_ids_in_order.index(from_module_id))
