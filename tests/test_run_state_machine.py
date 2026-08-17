"""Run 실행 결정 전이표(``RunStateMachine``)의 순수 단위 테스트.

브라우저·DB·I/O 없이 (상태·신호) → 명령 매핑만 검증한다.
"""

from __future__ import annotations

import pytest

from app.contexts.run.domain.state_machine import (
    BlockModule,
    CancelRemaining,
    CompleteStep,
    ExecuteModule,
    PauseForInput,
    RejectInvalidResumePoint,
    RejectUnexpectedInput,
    ResumeFromModule,
    RetryModule,
    RunStateMachine,
)
from app.core.enums import ModuleStatus

# --- 모듈 진입 결정 ----------------------------------------------------------


def test_entry_cancel_takes_priority_over_dependencies():
    decision = RunStateMachine.decide_module_entry(
        cancel_requested=True, dependencies_satisfied=False
    )
    assert isinstance(decision, CancelRemaining)


@pytest.mark.spec("SPEC-RUN-001", "AC-001")
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


@pytest.mark.spec("SPEC-RUN-001", "AC-002")
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


# --- 단계 실패 후 결정(재시도) ------------------------------------------------


def test_post_step_failure_retries_when_policy_allows():
    decision = RunStateMachine.decide_post_step_failure(
        step_status=ModuleStatus.ERROR,
        cancel_requested=False,
        current_attempt=1,
        max_attempts=3,
        retryable_on=frozenset({ModuleStatus.ERROR}),
        backoff_ms=500,
    )
    assert isinstance(decision, RetryModule)
    assert decision.backoff_ms == 500


def test_post_step_failure_completes_when_attempts_exhausted():
    decision = RunStateMachine.decide_post_step_failure(
        step_status=ModuleStatus.ERROR,
        cancel_requested=False,
        current_attempt=3,
        max_attempts=3,
        retryable_on=frozenset({ModuleStatus.ERROR}),
        backoff_ms=500,
    )
    assert isinstance(decision, CompleteStep)


def test_post_step_failure_cancel_takes_priority():
    decision = RunStateMachine.decide_post_step_failure(
        step_status=ModuleStatus.ERROR,
        cancel_requested=True,
        current_attempt=1,
        max_attempts=3,
        retryable_on=frozenset({ModuleStatus.ERROR}),
        backoff_ms=500,
    )
    assert isinstance(decision, CancelRemaining)


def test_post_step_failure_skips_non_retryable_status():
    decision = RunStateMachine.decide_post_step_failure(
        step_status=ModuleStatus.ANOMALY,
        cancel_requested=False,
        current_attempt=1,
        max_attempts=3,
        retryable_on=frozenset({ModuleStatus.ERROR}),
        backoff_ms=500,
    )
    assert isinstance(decision, CompleteStep)


# --- 부분 재실행 결정 --------------------------------------------------------


def test_partial_rerun_resumes_from_valid_module():
    decision = RunStateMachine.decide_partial_rerun(
        from_module_id="b",
        module_ids_in_order=["a", "b", "c"],
        partial_rerun_allowed=True,
    )
    assert isinstance(decision, ResumeFromModule)
    assert decision.from_index == 1


def test_partial_rerun_rejects_unknown_module():
    decision = RunStateMachine.decide_partial_rerun(
        from_module_id="z",
        module_ids_in_order=["a", "b"],
        partial_rerun_allowed=True,
    )
    assert isinstance(decision, RejectInvalidResumePoint)


@pytest.mark.spec("SPEC-RUN-002", "AC-002")
def test_partial_rerun_rejects_when_not_allowed():
    decision = RunStateMachine.decide_partial_rerun(
        from_module_id="a",
        module_ids_in_order=["a", "b"],
        partial_rerun_allowed=False,
    )
    assert isinstance(decision, RejectInvalidResumePoint)


# --- 복구 등급(RecoveryTier) 결정 --------------------------------------------

from app.core.enums import FailureSignal, RecoveryTier  # noqa: E402


def _failure_decision(**overrides):
    kwargs = {
        "step_status": ModuleStatus.ERROR,
        "cancel_requested": False,
        "current_attempt": 1,
        "max_attempts": 3,
        "retryable_on": frozenset({ModuleStatus.ERROR}),
        "backoff_ms": 500,
    }
    kwargs.update(overrides)
    return RunStateMachine.decide_post_step_failure(**kwargs)


@pytest.mark.parametrize(
    ("signal", "expected_tier"),
    [
        (FailureSignal.TIMEOUT, RecoveryTier.RETRY_IN_PLACE),
        (FailureSignal.SELECTOR_MISS, RecoveryTier.RETRY_IN_PLACE),
        (FailureSignal.UNKNOWN, RecoveryTier.RETRY_IN_PLACE),
        (FailureSignal.DIALOG, RecoveryTier.RESET_TO_MODULE_ENTRY),
        (FailureSignal.NAVIGATION, RecoveryTier.RESET_TO_MODULE_ENTRY),
        (FailureSignal.SESSION_LOST, RecoveryTier.REPLAY_FROM_LOGIN),
    ],
)
def test_signal_maps_to_base_tier(signal, expected_tier):
    decision = _failure_decision(failure_signal=signal)
    assert isinstance(decision, RetryModule)
    assert decision.tier is expected_tier


def test_tier_escalates_when_same_tier_already_attempted():
    """같은 등급으로 이미 실패했으면 한 단계 올린다."""
    decision = _failure_decision(
        failure_signal=FailureSignal.TIMEOUT,
        attempted_tiers=(RecoveryTier.RETRY_IN_PLACE,),
    )
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.RESET_TO_MODULE_ENTRY


def test_tier_escalation_stops_at_replay_from_login():
    decision = _failure_decision(
        failure_signal=FailureSignal.TIMEOUT,
        attempted_tiers=(
            RecoveryTier.RETRY_IN_PLACE,
            RecoveryTier.RESET_TO_MODULE_ENTRY,
            RecoveryTier.REPLAY_FROM_LOGIN,
        ),
    )
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.REPLAY_FROM_LOGIN


def test_site_signal_never_retries_even_when_policy_allows():
    """설계 §3.5 안전 규칙 — 매니페스트가 ANOMALY 재시도를 켜도 도메인이 거부한다."""
    decision = _failure_decision(
        step_status=ModuleStatus.ANOMALY,
        failure_signal=FailureSignal.SITE,
        retryable_on=frozenset({ModuleStatus.ERROR, ModuleStatus.ANOMALY}),
    )
    assert isinstance(decision, CompleteStep)


def test_default_signal_preserves_legacy_tier_zero_behaviour():
    """호출부가 신호를 넘기지 않으면 현행 동작(tier 0)과 동일하다."""
    decision = _failure_decision()
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.RETRY_IN_PLACE
    assert decision.backoff_ms == 500
