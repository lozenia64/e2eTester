"""Run 실행 결정 전이표(``RunStateMachine``)의 순수 단위 테스트.

브라우저·DB·I/O 없이 (상태·신호) → 명령 매핑만 검증한다.
"""

from __future__ import annotations

from app.core.enums import ModuleStatus
from app.domain.run_state_machine import (
    BlockModule,
    CancelRemaining,
    CompleteStep,
    ExecuteModule,
    PauseForInput,
    RejectUnexpectedInput,
    RunStateMachine,
)

# --- 모듈 진입 결정 ----------------------------------------------------------


def test_entry_cancel_takes_priority_over_dependencies():
    decision = RunStateMachine.decide_module_entry(
        cancel_requested=True, dependencies_satisfied=False
    )
    assert isinstance(decision, CancelRemaining)


def test_entry_blocks_when_dependencies_unsatisfied():
    decision = RunStateMachine.decide_module_entry(
        cancel_requested=False, dependencies_satisfied=False
    )
    assert isinstance(decision, BlockModule)


def test_entry_executes_when_clear():
    decision = RunStateMachine.decide_module_entry(
        cancel_requested=False, dependencies_satisfied=True
    )
    assert isinstance(decision, ExecuteModule)


# --- 단계 종료 후 결정 -------------------------------------------------------


def test_post_step_completes_on_normal_status():
    for status in (ModuleStatus.PASSED, ModuleStatus.ANOMALY, ModuleStatus.ERROR):
        decision = RunStateMachine.decide_post_step(
            step_status=status, cancel_requested=False, module_requires_user_input=True
        )
        assert isinstance(decision, CompleteStep)


def test_post_step_pauses_when_input_allowed():
    decision = RunStateMachine.decide_post_step(
        step_status=ModuleStatus.WAITING_INPUT,
        cancel_requested=False,
        module_requires_user_input=True,
    )
    assert isinstance(decision, PauseForInput)


def test_post_step_cancel_overrides_pause():
    decision = RunStateMachine.decide_post_step(
        step_status=ModuleStatus.WAITING_INPUT,
        cancel_requested=True,
        module_requires_user_input=True,
    )
    assert isinstance(decision, CancelRemaining)


def test_post_step_rejects_input_not_declared_in_manifest():
    # 매니페스트가 일시정지를 허가하지 않은 모듈의 입력 요구 → 정책 위반(ERROR).
    decision = RunStateMachine.decide_post_step(
        step_status=ModuleStatus.WAITING_INPUT,
        cancel_requested=False,
        module_requires_user_input=False,
    )
    assert isinstance(decision, RejectUnexpectedInput)


def test_post_step_rejection_takes_priority_over_cancel():
    # 선언되지 않은 입력 요구는 취소보다 먼저 정책 위반으로 판정한다.
    decision = RunStateMachine.decide_post_step(
        step_status=ModuleStatus.WAITING_INPUT,
        cancel_requested=True,
        module_requires_user_input=False,
    )
    assert isinstance(decision, RejectUnexpectedInput)
