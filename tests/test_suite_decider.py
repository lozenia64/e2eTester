"""Suite Decider(decide/evolve/fold) — 이벤트가 진실의 원천임을 증명한다(Run 과 동형).

핵심 불변식: **라이브 애그리거트 스냅샷 == 이벤트 스트림 폴드**. Suite 이벤트는 전체 상태를
``suite_summary`` 로 동봉하므로, ``rebuild_state`` 가 스트림만으로 동일한 ``SuiteSnapshot`` 을
재구성한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contexts.suite.domain import commands as c
from app.contexts.suite.domain.aggregate import SuiteAggregate
from app.contexts.suite.domain.decider import decide, evolve, is_terminal, rebuild_state
from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteRun, SuiteStep


def _step(system_code: str, order: int, status: SuiteStatus = SuiteStatus.PENDING) -> SuiteStep:
    return SuiteStep(
        system_code=system_code, system_name=system_code.upper(), order=order, status=status
    )


def _suite(suite_id: str = "suite_dec") -> SuiteRun:
    return SuiteRun(
        suite_id=suite_id,
        status=SuiteStatus.PENDING,
        steps=[_step("hom", 0), _step("mhm", 1)],
        requested_at=datetime(2026, 7, 12, 3, 0, tzinfo=UTC),
        selected_system_codes=["hom", "mhm"],
    )


def _initial_state(suite_id: str = "suite_dec") -> object:
    aggregate = SuiteAggregate.for_new_suite(_suite(suite_id))
    return rebuild_state(aggregate.pull_events(), suite_id=suite_id)


def _apply(state, suite_id: str, *events):
    for event in events:
        state = evolve(state, event, suite_id=suite_id)
    return state


def _event_type_name(event) -> str:
    return type(event.event).__name__


def test_empty_stream_folds_to_none():
    assert rebuild_state([], suite_id="suite_dec") is None


def test_suite_created_initializes_snapshot():
    state = _initial_state("suite_init")
    assert state.suite_id == "suite_init"
    assert state.status == SuiteStatus.PENDING
    assert {s.system_code for s in state.steps} == {"hom", "mhm"}


def test_decide_begin_and_start_step():
    state = _initial_state()
    events = decide(c.BeginSuite(), state)
    assert [_event_type_name(e) for e in events] == ["SuiteStarted"]
    state = _apply(state, "suite_dec", *events)
    assert state.status == SuiteStatus.RUNNING

    events = decide(c.StartStep(0), state)
    assert [_event_type_name(e) for e in events] == ["SuiteStepStarted"]
    state = _apply(state, "suite_dec", *events)
    assert state.current_step_index == 0
    assert state.steps[0].status == SuiteStatus.RUNNING


def test_decide_link_and_record_step_result():
    state = _apply(_initial_state(), "suite_dec", *decide(c.BeginSuite(), _initial_state()))
    state = _apply(state, "suite_dec", *decide(c.StartStep(0), state))
    state = _apply(state, "suite_dec", *decide(c.LinkRun(0, "run_hom"), state))
    assert state.active_run_id == "run_hom"
    assert state.steps[0].run_id == "run_hom"

    events = decide(c.RecordStepResult(0, SuiteStatus.PASSED), state)
    assert [_event_type_name(e) for e in events] == ["SuiteStepFinished"]
    state = _apply(state, "suite_dec", *events)
    assert state.steps[0].status == SuiteStatus.PASSED
    assert state.active_run_id is None


def test_decide_waiting_input_and_resume():
    state = _apply(_initial_state(), "suite_dec", *decide(c.BeginSuite(), _initial_state()))
    state = _apply(state, "suite_dec", *decide(c.StartStep(0), state))
    state = _apply(state, "suite_dec", *decide(c.LinkRun(0, "run_hom"), state))

    state = _apply(state, "suite_dec", *decide(c.MarkWaitingInput("run_hom", "OTP 입력"), state))
    assert state.status == SuiteStatus.WAITING_INPUT
    assert state.awaiting_input_run_id == "run_hom"

    state = _apply(state, "suite_dec", *decide(c.MarkResumed(), state))
    assert state.status == SuiteStatus.RUNNING
    assert state.awaiting_input_run_id is None


def test_decide_finalize_cancel_remaining():
    state = _apply(_initial_state(), "suite_dec", *decide(c.BeginSuite(), _initial_state()))
    state = _apply(state, "suite_dec", *decide(c.StartStep(0), state))
    state = _apply(state, "suite_dec", *decide(c.RecordStepResult(0, SuiteStatus.ERROR), state))

    events = decide(c.FinalizeSuite(SuiteStatus.ERROR, cancel_remaining=True), state)
    assert [_event_type_name(e) for e in events] == ["SuiteFinished"]
    state = _apply(state, "suite_dec", *events)
    assert state.status == SuiteStatus.ERROR
    assert is_terminal(state)
    assert state.steps[1].status == SuiteStatus.CANCELLED  # 남은 스텝 봉인


def test_decide_does_not_mutate_input_state():
    state = _initial_state()
    before = state.status
    decide(c.BeginSuite(), state)
    assert state.status == before  # frozen 스냅샷 미변경


def test_fold_equals_live_aggregate_full_suite():
    """decide 로 구동한 이벤트 폴드 == 애그리거트 직접 구동 결과."""
    # 애그리거트 직접 구동: 시작 → 스텝0 PASSED → 스텝1 ANOMALY → 종료.
    aggregate = SuiteAggregate.for_new_suite(_suite("suite_x"))
    events = aggregate.pull_events()
    aggregate.begin()
    for index, status in ((0, SuiteStatus.PASSED), (1, SuiteStatus.ANOMALY)):
        step = aggregate.start_step(index)
        aggregate.link_run(step, f"run_{index}")
        aggregate.record_step_result(step, status, step_index=index)
    aggregate.finalize(aggregate.compute_final_status())
    events += aggregate.pull_events()

    live = aggregate.to_snapshot()
    folded = rebuild_state(events, suite_id="suite_x")
    assert folded == live
    assert folded.status == SuiteStatus.ANOMALY
