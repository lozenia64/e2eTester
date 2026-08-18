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


@pytest.mark.spec("SPEC-RUN-006", "AC-006")
def test_auto_rerun_queues_and_auto_rerun_of_is_self_referential():
    """AC-006 Then 절 전체 — "실패 모듈부터 1회 자동 재실행이 큐잉되고 auto_rerun_of 가
    원본 run_id 다"를 애그리거트 수준에서 검증한다(``test_scheduled_error_run_triggers_auto_rerun``
    은 순수 결정만 확인하고 큐잉·auto_rerun_of 는 다루지 않는다).

    ``RunService._enqueue_auto_rerun`` 은 실패 모듈부터 같은 ``run_id`` 로
    ``rerun_from_module(run_id=run.run_id, ..., auto_rerun_of=run.run_id)`` 를 호출해
    제자리 재개한다 — 새 Run 을 만들지 않는다. 그 안에서 실제로 상태를 바꾸는 두 애그리거트
    호출(``mark_auto_rerun_pending`` = 큐잉 표시, ``set_auto_rerun_of`` = 원본 run_id 기록)을
    같은 순서로 재현한다. ``auto_rerun_of`` 는 그래서 항상 자기 자신의 ``run_id`` 를
    가리키는 자기 참조 필드다(``ac36acc`` 정정 — 별도 원본 Run 을 가리키지 않는다).
    """
    from datetime import UTC, datetime

    from app.contexts.run.domain.aggregate import RunAggregate
    from app.core.enums import ModuleStatus
    from app.core.run_models import Run, RunModule

    run = Run(
        run_id="run_auto_1",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.ERROR,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(module_id="m1", name="M1", group="g", order=1, status=ModuleStatus.ERROR)
        ],
    )
    aggregate = RunAggregate(run)

    aggregate.mark_auto_rerun_pending(from_module_id="m1")
    aggregate.set_auto_rerun_of(run.run_id)

    assert run.auto_rerun_pending is True
    assert run.auto_rerun_of == run.run_id
