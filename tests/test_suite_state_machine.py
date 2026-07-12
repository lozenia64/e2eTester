"""Suite 사가 결정 전이표(``SuiteStateMachine``)의 순수 단위 테스트.

브라우저·DB·이벤트 루프 없이 (상태·신호) → 명령 매핑만 검증한다(``RunStateMachine`` 테스트와 동형).
"""

from __future__ import annotations

from app.contexts.suite.domain.state_machine import (
    CancelSuite,
    FinalizeSuite,
    RecordAndAdvance,
    RecordAndCancel,
    StartStep,
    SuiteStateMachine,
)
from app.core.enums import RunStatus, SuiteStatus

# --- 하위 Run 상태 → 스텝 상태 매핑 -----------------------------------------


def test_step_status_for_run_maps_each_run_outcome():
    assert SuiteStateMachine.step_status_for_run(RunStatus.PASSED) == SuiteStatus.PASSED
    assert SuiteStateMachine.step_status_for_run(RunStatus.CANCELLED) == SuiteStatus.CANCELLED
    assert SuiteStateMachine.step_status_for_run(RunStatus.ERROR) == SuiteStatus.ERROR
    # 레거시 FAILED 와 ANOMALY 는 이상징후로 귀속된다.
    assert SuiteStateMachine.step_status_for_run(RunStatus.ANOMALY) == SuiteStatus.ANOMALY
    assert SuiteStateMachine.step_status_for_run(RunStatus.FAILED) == SuiteStatus.ANOMALY


# --- 하위 Run 종료 후 결정 ---------------------------------------------------


def test_after_run_finished_advances_on_normal_outcome():
    decision = SuiteStateMachine.decide_after_run_finished(
        run_status=RunStatus.PASSED, cancel_requested=False
    )
    assert isinstance(decision, RecordAndAdvance)
    assert decision.step_status == SuiteStatus.PASSED


def test_after_run_finished_cancels_when_run_cancelled():
    # 하위 Run 이 취소로 끝나면(연쇄 취소) Suite 도 취소로 봉인한다.
    decision = SuiteStateMachine.decide_after_run_finished(
        run_status=RunStatus.CANCELLED, cancel_requested=False
    )
    assert isinstance(decision, RecordAndCancel)
    assert decision.step_status == SuiteStatus.CANCELLED


def test_after_run_finished_cancels_when_cancel_requested():
    # 정상 종료여도 Suite 취소 의도가 관측되면 결과는 기록하되 취소로 마무리한다.
    decision = SuiteStateMachine.decide_after_run_finished(
        run_status=RunStatus.PASSED, cancel_requested=True
    )
    assert isinstance(decision, RecordAndCancel)
    assert decision.step_status == SuiteStatus.PASSED


def test_after_run_finished_records_error_outcome_before_advancing():
    decision = SuiteStateMachine.decide_after_run_finished(
        run_status=RunStatus.ERROR, cancel_requested=False
    )
    assert isinstance(decision, RecordAndAdvance)
    assert decision.step_status == SuiteStatus.ERROR


# --- 다음 스텝 진입 결정 -----------------------------------------------------


def test_advance_starts_next_pending_step():
    decision = SuiteStateMachine.decide_advance(cancel_requested=False, next_pending_index=2)
    assert isinstance(decision, StartStep)
    assert decision.index == 2


def test_advance_finalizes_when_no_pending_step():
    decision = SuiteStateMachine.decide_advance(cancel_requested=False, next_pending_index=None)
    assert isinstance(decision, FinalizeSuite)


def test_advance_cancel_takes_priority_over_pending_step():
    # 다음 스텝이 남아 있어도 취소 의도가 우선한다.
    decision = SuiteStateMachine.decide_advance(cancel_requested=True, next_pending_index=0)
    assert isinstance(decision, CancelSuite)
