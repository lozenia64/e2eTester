"""RunAggregate 순수 단위 테스트.

브라우저·DB·이벤트 루프 없이 도메인 상태 전이 규칙만 검증한다(이 계층이 I/O 와
분리됐다는 증거). `python3 -m pytest tests/` 로 실행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.domain.run_aggregate import RunAggregate


def _module(
    module_id: str, order: int, *, depends_on=None, status=ModuleStatus.PENDING
) -> RunModule:
    return RunModule(
        module_id=module_id,
        name=module_id,
        group="g",
        order=order,
        depends_on=depends_on or [],
        status=status,
    )


def _run(modules: list[RunModule], status: RunStatus = RunStatus.PENDING) -> Run:
    return Run(
        run_id="run_test",
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=datetime.now(UTC),
        modules=modules,
        selected_module_ids=[m.module_id for m in modules],
    )


def test_begin_sets_running_and_started_at():
    run = _run([_module("a", 0)])
    aggregate = RunAggregate(run)
    aggregate.begin()
    assert aggregate.to_snapshot().status == RunStatus.RUNNING
    assert aggregate.to_snapshot().started_at is not None
    events = aggregate.pull_events()
    assert any(event.event_type == "RunStarted" for event in events)


def test_dependencies_satisfied_requires_all_passed():
    login = _module("login", 0, status=ModuleStatus.PASSED)
    contract = _module("contract", 1, depends_on=["login"])
    agg = RunAggregate(_run([login, contract]))
    assert agg.dependencies_satisfied(contract) is True

    login.status = ModuleStatus.ANOMALY
    assert agg.dependencies_satisfied(contract) is False


def test_block_for_dependencies_marks_blocked():
    contract = _module("contract", 1, depends_on=["login"])
    RunAggregate(_run([contract])).block_for_dependencies(contract)
    assert contract.status == ModuleStatus.BLOCKED
    assert "선행" in contract.message


def test_compute_final_status_rules():
    passed = _run([_module("a", 0, status=ModuleStatus.PASSED)])
    assert RunAggregate(passed).compute_final_status(None) == RunStatus.PASSED

    anomaly = _run([_module("a", 0, status=ModuleStatus.ANOMALY)])
    assert RunAggregate(anomaly).compute_final_status(None) == RunStatus.ANOMALY

    legacy_anomaly = _run([_module("a", 0, status=ModuleStatus.FAILED)])
    assert RunAggregate(legacy_anomaly).compute_final_status(None) == RunStatus.ANOMALY

    error = _run([_module("a", 0, status=ModuleStatus.ERROR)])
    assert RunAggregate(error).compute_final_status(None) == RunStatus.ERROR

    mixed = _run(
        [
            _module("a", 0, status=ModuleStatus.ANOMALY),
            _module("b", 1, status=ModuleStatus.ERROR),
        ]
    )
    assert RunAggregate(mixed).compute_final_status(None) == RunStatus.ERROR

    # 강제 상태(취소 등)는 outcome 과 무관하게 우선한다.
    assert RunAggregate(error).compute_final_status(RunStatus.CANCELLED) == RunStatus.CANCELLED


def test_fail_module_marks_error():
    module = _module("a", 0, status=ModuleStatus.RUNNING)
    RunAggregate(_run([module])).fail_module(module, "gateway error")
    assert module.status == ModuleStatus.ERROR


def test_record_result_copies_fields_but_not_logs():
    module = _module("a", 0, status=ModuleStatus.RUNNING)
    RunAggregate(_run([module])).record_result(
        module,
        status=ModuleStatus.PASSED,
        message="ok",
        artifacts=["x.png", "y.log"],
        current_url="https://example.com",
        dialog_messages=["alert"],
    )
    assert module.status == ModuleStatus.PASSED
    assert module.artifact_count == 2
    assert module.current_url == "https://example.com"
    assert module.dialog_messages == ["alert"]
    assert module.logs == []  # 로그는 별도 스토어 소유


def test_finish_timing_computes_duration():
    module = _module("a", 0)
    agg = RunAggregate(_run([module]))
    agg.mark_running(module)
    agg.finish_timing(module)
    assert module.ended_at is not None
    assert module.duration_ms is not None and module.duration_ms >= 0


def test_cancel_modules_skips_terminal_and_returns_changed():
    done = _module("done", 0, status=ModuleStatus.PASSED)
    running = _module("running", 1, status=ModuleStatus.RUNNING)
    pending = _module("pending", 2, status=ModuleStatus.PENDING)
    changed = RunAggregate(_run([done, running, pending])).cancel_modules([done, running, pending])
    assert {m.module_id for m in changed} == {"running", "pending"}
    assert done.status == ModuleStatus.PASSED  # 이미 종료 → 보존
    assert running.status == ModuleStatus.CANCELLED
    assert pending.status == ModuleStatus.CANCELLED


def test_mark_waiting_input_pauses_run():
    module = _module("login", 0, status=ModuleStatus.RUNNING)
    run = _run([module], status=RunStatus.RUNNING)
    RunAggregate(run).mark_waiting_input(module, "OTP 요청됨", artifacts=["a.png"])
    assert module.status == ModuleStatus.WAITING_INPUT
    assert run.status == RunStatus.WAITING_INPUT
    assert run.awaiting_input_module_id == "login"
    assert run.awaiting_input_prompt


def test_resume_after_input_requeues():
    module = _module("login", 0, status=ModuleStatus.WAITING_INPUT)
    run = _run([module], status=RunStatus.WAITING_INPUT)
    run.awaiting_input_module_id = "login"
    RunAggregate(run).resume_after_input(module)
    assert run.status == RunStatus.RUNNING
    assert run.awaiting_input_module_id is None
    assert module.status == ModuleStatus.QUEUED


def test_finalize_seals_run():
    module = _module("a", 0, status=ModuleStatus.PASSED)
    run = _run([module], status=RunStatus.RUNNING)
    run.awaiting_input_prompt = "..."
    status = RunAggregate(run).finalize(None)
    assert status == RunStatus.PASSED
    assert run.status == RunStatus.PASSED
    assert run.ended_at is not None
    assert run.awaiting_input_module_id is None
    assert run.awaiting_input_prompt is None


def test_select_failure_target_prefers_current_then_first_unrun():
    a = _module("a", 0, status=ModuleStatus.PASSED)
    b = _module("b", 1, status=ModuleStatus.RUNNING)
    c = _module("c", 2, status=ModuleStatus.PENDING)
    agg = RunAggregate(_run([a, b, c]))
    assert agg.select_failure_target(b, [a, b, c]) is b
    # 진행 중 모듈이 없으면(예: current 가 이미 종료) 첫 미실행 모듈
    assert agg.select_failure_target(a, [a, b, c]) is b


def test_seal_interrupted_only_for_active_runs():
    active = _run(
        [_module("a", 0, status=ModuleStatus.RUNNING)],
        status=RunStatus.RUNNING,
    )
    assert RunAggregate(active).seal_interrupted() is True
    assert active.status == RunStatus.CANCELLED
    assert active.modules[0].status == ModuleStatus.CANCELLED

    done = _run([_module("a", 0, status=ModuleStatus.PASSED)], status=RunStatus.PASSED)
    assert RunAggregate(done).seal_interrupted() is False
    assert done.status == RunStatus.PASSED


def test_note_module_message_updates_message_via_aggregate():
    module = _module("a", 0, status=ModuleStatus.RUNNING)
    RunAggregate(_run([module])).note_module_message(module, "마지막 로그 줄")
    assert module.message == "마지막 로그 줄"


def test_attach_failure_analysis_via_aggregate():
    from app.core.run_models import FailureAnalysis

    module = _module("a", 0, status=ModuleStatus.ERROR)
    analysis = FailureAnalysis(
        category="c",
        probable_cause="p",
        retryable=False,
        user_summary="u",
        developer_details="d",
        recommended_action="r",
    )
    RunAggregate(_run([module])).attach_failure_analysis(module, analysis)
    assert module.failure_analysis is analysis


def test_attach_comparison_via_aggregate():
    from app.core.run_models import RunComparison

    run = _run([_module("a", 0, status=ModuleStatus.PASSED)])
    comparison = RunComparison(
        has_baseline=True,
        baseline_run_id="run_prev",
        newly_failed=[],
        recovered=["a"],
        still_failing=[],
    )
    RunAggregate(run).attach_comparison(comparison)
    assert run.comparison is comparison


def test_hydrate_logs_fills_each_module_and_defaults_missing_to_empty():
    first = _module("a", 0, status=ModuleStatus.PASSED)
    second = _module("b", 1, status=ModuleStatus.PASSED)
    run = _run([first, second])
    RunAggregate(run).hydrate_logs({"a": ["line-1", "line-2"]})
    assert first.logs == ["line-1", "line-2"]
    assert second.logs == []


def test_record_retry_increments_attempt_and_requeues():
    module = _module("a", 0, status=ModuleStatus.RUNNING)
    module.max_attempts = 3
    aggregate = RunAggregate(_run([module]))
    aggregate.record_retry(module)
    assert module.attempt == 2
    assert module.retry_count == 1
    assert module.status == ModuleStatus.QUEUED
    events = aggregate.pull_events()
    assert any(event.event_type == "RunModuleRetried" for event in events)


def test_prepare_partial_rerun_resets_modules_from_index():
    modules = [
        _module("a", 0, status=ModuleStatus.PASSED),
        _module("b", 1, status=ModuleStatus.ERROR),
        _module("c", 2, status=ModuleStatus.PENDING),
    ]
    run = _run(modules, status=RunStatus.ERROR)
    run.ended_at = datetime.now(UTC)
    aggregate = RunAggregate(run)
    aggregate.prepare_partial_rerun(1, modules)
    assert run.status == RunStatus.RUNNING
    assert run.ended_at is None
    assert modules[0].status == ModuleStatus.PASSED
    assert modules[1].status == ModuleStatus.PENDING
    assert modules[2].status == ModuleStatus.PENDING
    events = aggregate.pull_events()
    assert any(event.event_type == "RunPartialRerunStarted" for event in events)
