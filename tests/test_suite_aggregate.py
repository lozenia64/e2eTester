"""SuiteAggregate 순수 단위 테스트.

브라우저·DB·이벤트 루프 없이 Suite 도메인 상태 전이 규칙만 검증한다(``RunAggregate`` 테스트와 동형).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import SuiteStatus
from app.core.models import SuiteRun, SuiteStep
from app.domain.suite_aggregate import SuiteAggregate


def _step(system_code: str, order: int, status: SuiteStatus = SuiteStatus.PENDING) -> SuiteStep:
    return SuiteStep(
        system_code=system_code,
        system_name=system_code.upper(),
        order=order,
        status=status,
    )


def _suite(steps: list[SuiteStep], status: SuiteStatus = SuiteStatus.PENDING) -> SuiteRun:
    return SuiteRun(
        suite_id="suite_test",
        status=status,
        steps=steps,
        requested_at=datetime.now(UTC),
        selected_system_codes=[s.system_code for s in steps],
    )


# --- 조회 -------------------------------------------------------------------


def test_next_pending_index_skips_non_pending():
    suite = _suite(
        [
            _step("hom", 0, SuiteStatus.PASSED),
            _step("mhm", 1, SuiteStatus.SKIPPED),
            _step("fp", 2, SuiteStatus.PENDING),
        ]
    )
    assert SuiteAggregate(suite).next_pending_index() == 2


def test_next_pending_index_none_when_all_resolved():
    suite = _suite([_step("hom", 0, SuiteStatus.PASSED), _step("mhm", 1, SuiteStatus.SKIPPED)])
    assert SuiteAggregate(suite).next_pending_index() is None


def test_compute_final_status_priority_error_over_anomaly_over_passed():
    error = _suite(
        [
            _step("hom", 0, SuiteStatus.PASSED),
            _step("mhm", 1, SuiteStatus.ANOMALY),
            _step("fp", 2, SuiteStatus.ERROR),
        ]
    )
    assert SuiteAggregate(error).compute_final_status() == SuiteStatus.ERROR

    anomaly = _suite([_step("hom", 0, SuiteStatus.PASSED), _step("mhm", 1, SuiteStatus.ANOMALY)])
    assert SuiteAggregate(anomaly).compute_final_status() == SuiteStatus.ANOMALY

    passed = _suite([_step("hom", 0, SuiteStatus.PASSED), _step("mhm", 1, SuiteStatus.SKIPPED)])
    assert SuiteAggregate(passed).compute_final_status() == SuiteStatus.PASSED


def test_find_step_by_run_id():
    step = _step("hom", 0, SuiteStatus.RUNNING)
    step.run_id = "run_abc"
    suite = _suite([step, _step("mhm", 1)])
    index, found = SuiteAggregate(suite).find_step("run_abc")
    assert index == 0 and found is step
    assert SuiteAggregate(suite).find_step("nope") == (-1, None)


# --- 명령(상태 전이) --------------------------------------------------------


def test_begin_marks_running_with_started_at():
    suite = _suite([_step("hom", 0)])
    SuiteAggregate(suite).begin()
    assert suite.status == SuiteStatus.RUNNING
    assert suite.started_at is not None


def test_start_step_and_link_run():
    suite = _suite([_step("hom", 0), _step("mhm", 1)])
    aggregate = SuiteAggregate(suite)
    step = aggregate.start_step(0)
    assert step.status == SuiteStatus.RUNNING
    assert suite.current_step_index == 0
    assert suite.active_run_id is None
    aggregate.link_run(step, "run_1")
    assert step.run_id == "run_1"
    assert suite.active_run_id == "run_1"


def test_record_step_result_clears_active_pointers():
    step = _step("hom", 0, SuiteStatus.RUNNING)
    step.run_id = "run_1"
    suite = _suite([step], status=SuiteStatus.RUNNING)
    suite.active_run_id = "run_1"
    suite.awaiting_input_run_id = "run_1"
    suite.awaiting_input_prompt = "OTP"
    SuiteAggregate(suite).record_step_result(step, SuiteStatus.PASSED, step_index=0)
    assert step.status == SuiteStatus.PASSED
    assert suite.active_run_id is None
    assert suite.awaiting_input_run_id is None
    assert suite.awaiting_input_prompt is None


def test_waiting_input_then_resumed_round_trip():
    suite = _suite([_step("hom", 0, SuiteStatus.RUNNING)], status=SuiteStatus.RUNNING)
    aggregate = SuiteAggregate(suite)
    aggregate.mark_waiting_input("run_1", "OTP 입력")
    assert suite.status == SuiteStatus.WAITING_INPUT
    assert suite.awaiting_input_run_id == "run_1"
    assert suite.awaiting_input_prompt == "OTP 입력"
    aggregate.mark_resumed()
    assert suite.status == SuiteStatus.RUNNING
    assert suite.awaiting_input_run_id is None
    assert suite.awaiting_input_prompt is None


def test_finalize_cancel_remaining_seals_unfinished_steps():
    suite = _suite(
        [
            _step("hom", 0, SuiteStatus.PASSED),
            _step("mhm", 1, SuiteStatus.RUNNING),
            _step("fp", 2, SuiteStatus.PENDING),
            _step("hrp", 3, SuiteStatus.SKIPPED),
        ],
        status=SuiteStatus.RUNNING,
    )
    SuiteAggregate(suite).finalize(SuiteStatus.CANCELLED, cancel_remaining=True)
    assert suite.status == SuiteStatus.CANCELLED
    assert suite.ended_at is not None
    statuses = [step.status for step in suite.steps]
    # PASSED·SKIPPED 는 그대로, 진행 중이던 RUNNING·PENDING 만 CANCELLED 로 봉인.
    assert statuses == [
        SuiteStatus.PASSED,
        SuiteStatus.CANCELLED,
        SuiteStatus.CANCELLED,
        SuiteStatus.SKIPPED,
    ]


def test_finalize_without_cancel_remaining_keeps_step_statuses():
    suite = _suite(
        [_step("hom", 0, SuiteStatus.PASSED), _step("mhm", 1, SuiteStatus.ANOMALY)],
        status=SuiteStatus.RUNNING,
    )
    SuiteAggregate(suite).finalize(SuiteStatus.ANOMALY)
    assert suite.status == SuiteStatus.ANOMALY
    assert [step.status for step in suite.steps] == [SuiteStatus.PASSED, SuiteStatus.ANOMALY]


def test_seal_interrupted_seals_active_suite_and_steps():
    suite = _suite(
        [_step("hom", 0, SuiteStatus.RUNNING), _step("mhm", 1, SuiteStatus.PASSED)],
        status=SuiteStatus.RUNNING,
    )
    assert SuiteAggregate(suite).seal_interrupted() is True
    assert suite.status == SuiteStatus.CANCELLED
    assert suite.steps[0].status == SuiteStatus.CANCELLED
    assert suite.steps[1].status == SuiteStatus.PASSED


def test_seal_interrupted_noop_on_terminal_suite():
    suite = _suite([_step("hom", 0, SuiteStatus.PASSED)], status=SuiteStatus.PASSED)
    assert SuiteAggregate(suite).seal_interrupted() is False
    assert suite.status == SuiteStatus.PASSED
