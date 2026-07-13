"""Suite(전체 시스템 순차 점검) 사가의 **결정 규칙(명시적 전이표)** 을 소유하는 순수 도메인 컴포넌트.

``RunStateMachine`` 과 **동형(isomorphic)** 이다. 과거에는 "하위 Run 이 끝나면 다음에 무엇을
할지"라는 결정이 ``SuiteService`` 의 이벤트 핸들러·``_advance`` 루프 안에 ``suite.status = ...``
같은 인라인 변이와 뒤섞여 있었다(상태머신이 코드 형태로만 존재). 이 모듈은 그 **결정(decision)**
을 **효과(effect)** 와 분리해, ``(상태·신호) → 명령`` 으로 매핑하는 명시적 표로 끌어낸다.

- 결정(이 파일): 순수 함수. ``await`` 없음, 저장소/이벤트/RunService import 없음 → 브라우저·DB
  없이 단독 단위 테스트(``tests/test_suite_state_machine.py``).
- 효과(``SuiteService``): 결정을 받아 ``save_suite``·WS 이벤트·하위 Run 명령 같은 I/O 만 수행한다.
- 상태 *변경* 은 ``SuiteAggregate`` 가 책임진다.

전이표(요약):

  하위 Run 종료 후(decide_after_run_finished):
    run_status                            → 스텝 상태(step_status_for_run)
    run CANCELLED 또는 cancel_requested    → RecordAndCancel
    그 외                                  → RecordAndAdvance

  다음 스텝 진입(decide_advance):
    cancel_requested                      → CancelSuite
    남은 PENDING 스텝 없음                  → FinalizeSuite
    그 외                                  → StartStep(index)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import RunStatus, SuiteStatus
from app.core.status_labels import RUN_ERROR_STATUSES

# --- 하위 Run 종료 후 결정 ---------------------------------------------------


@dataclass(frozen=True)
class RecordAndAdvance:
    """스텝 결과를 기록하고 다음 PENDING 스텝으로 전진한다(정상 흐름)."""

    step_status: SuiteStatus


@dataclass(frozen=True)
class RecordAndCancel:
    """스텝 결과를 기록하되 Suite 를 취소로 봉인한다.

    하위 Run 이 사용자 취소로 끝났거나(연쇄 취소), Suite 취소 의도가 이미 관측된 경우.
    """

    step_status: SuiteStatus


AfterRunDecision = RecordAndAdvance | RecordAndCancel


# --- 다음 스텝 진입 결정 -----------------------------------------------------


@dataclass(frozen=True)
class StartStep:
    """다음 PENDING 스텝의 하위 Run 을 시작한다."""

    index: int


@dataclass(frozen=True)
class FinalizeSuite:
    """남은 PENDING 스텝이 없음 → 집계된 최종 상태(ERROR>ANOMALY>PASSED)로 Suite 를 종료한다."""


@dataclass(frozen=True)
class CancelSuite:
    """취소 의도가 관측됨 → 남은 스텝을 CANCELLED 로 봉인하고 Suite 를 종료한다."""


AdvanceDecision = StartStep | FinalizeSuite | CancelSuite


@dataclass(frozen=True)
class ResumeFromModule:
    """Suite 가 하위 Run 의 부분 재실행을 위임한다."""

    from_module_id: str


@dataclass(frozen=True)
class RejectInvalidResumePoint:
    """Suite 부분 재실행 거부."""


SuitePartialRerunDecision = ResumeFromModule | RejectInvalidResumePoint


class SuiteStateMachine:
    """Suite 사가의 결정 규칙(전이표). 상태값/불리언만 받아 명령을 돌려주는 순수 함수 모음.

    상태 *변경* 은 ``SuiteAggregate`` 가, 결정의 *실행*(I/O) 은 ``SuiteService`` 가 책임진다.
    이 컴포넌트는 오직 "무엇을 할지"만 결정한다.
    """

    @staticmethod
    def step_status_for_run(run_status: RunStatus) -> SuiteStatus:
        """하위 Run 의 최종 상태를 그 스텝의 종료 상태로 변환한다(순수 매핑)."""
        if run_status == RunStatus.PASSED:
            return SuiteStatus.PASSED
        if run_status == RunStatus.CANCELLED:
            return SuiteStatus.CANCELLED
        if run_status in RUN_ERROR_STATUSES:
            return SuiteStatus.ERROR
        return SuiteStatus.ANOMALY

    @staticmethod
    def decide_after_run_finished(
        *, run_status: RunStatus, cancel_requested: bool
    ) -> AfterRunDecision:
        step_status = SuiteStateMachine.step_status_for_run(run_status)
        cancelled = run_status == RunStatus.CANCELLED or cancel_requested
        if cancelled:
            return RecordAndCancel(step_status=step_status)
        return RecordAndAdvance(step_status=step_status)

    @staticmethod
    def decide_advance(
        *, cancel_requested: bool, next_pending_index: int | None
    ) -> AdvanceDecision:
        if cancel_requested:
            return CancelSuite()
        if next_pending_index is None:
            return FinalizeSuite()
        return StartStep(index=next_pending_index)

    @staticmethod
    def decide_partial_rerun(
        *,
        from_module_id: str,
        active_run_id: str | None,
        partial_rerun_allowed: bool,
    ) -> SuitePartialRerunDecision:
        """하위 Run 부분 재실행 위임 결정(RunStateMachine.decide_partial_rerun 과 동형)."""
        if active_run_id is None:
            return RejectInvalidResumePoint()
        if not partial_rerun_allowed:
            return RejectInvalidResumePoint()
        return ResumeFromModule(from_module_id=from_module_id)
