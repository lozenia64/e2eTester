"""Run 수준 자동 재실행 게이트(순수 결정) 테스트."""

from __future__ import annotations

import pytest

from app.contexts.run.domain.state_machine import (
    RunStateMachine,
    SkipAutoRerun,
    TriggerAutoRerun,
)
from app.core.enums import RunStatus


def _decide(**overrides):
    kwargs = {
        "run_status": RunStatus.ERROR,
        "triggered_by": "schedule",
        "is_auto_rerun": False,
        "budget_remaining": 1,
    }
    kwargs.update(overrides)
    return RunStateMachine.decide_auto_rerun(**kwargs)


@pytest.mark.spec("SPEC-RUN-006", "AC-006")
def test_scheduled_error_run_triggers_auto_rerun():
    assert isinstance(_decide(), TriggerAutoRerun)


@pytest.mark.parametrize("status", [RunStatus.ANOMALY, RunStatus.PASSED, RunStatus.CANCELLED])
def test_non_error_status_never_reruns(status):
    """설계 §3.5·§3.6 — 사이트 이상은 절대 자동 재실행하지 않는다."""
    assert isinstance(_decide(run_status=status), SkipAutoRerun)


def test_manual_run_never_reruns():
    """사람이 보고 있는 실행은 판단을 뺏지 않는다."""
    assert isinstance(_decide(triggered_by="manual"), SkipAutoRerun)


def test_auto_rerun_does_not_chain():
    assert isinstance(_decide(is_auto_rerun=True), SkipAutoRerun)


def test_exhausted_budget_skips():
    assert isinstance(_decide(budget_remaining=0), SkipAutoRerun)


def test_auto_rerun_emits_event_with_original_run_id():
    from app.contexts.run.domain.events import RunAutoRerunTriggered

    event = RunAutoRerunTriggered(original_run_id="run1", from_module_id="m2")

    assert event.original_run_id == "run1"
    assert event.from_module_id == "m2"
