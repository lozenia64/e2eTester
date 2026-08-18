"""RunAggregate 순수 단위 테스트.

브라우저·DB·이벤트 루프 없이 도메인 상태 전이 규칙만 검증한다(이 계층이 I/O 와
분리됐다는 증거). `python3 -m pytest tests/` 로 실행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contexts.run.domain.aggregate import RunAggregate
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule


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
    assert any(type(event.event).__name__ == "RunStarted" for event in events)


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


def test_finalize_clears_auto_rerun_pending():
    """R4 — 새 종료마다 낡은 대기 표식을 지운다(그러지 않으면 재실행이 다시 실패해도
    완료/운영자 알림이 영원히 억제된다)."""
    module = _module("a", 0, status=ModuleStatus.ERROR)
    run = _run([module], status=RunStatus.RUNNING)
    run.auto_rerun_pending = True
    RunAggregate(run).finalize(None)
    assert run.auto_rerun_pending is False


def test_finalize_is_idempotent_no_duplicate_run_finished():
    module = _module("a", 0, status=ModuleStatus.ANOMALY)
    run = _run([module], status=RunStatus.RUNNING)
    aggregate = RunAggregate(run)
    aggregate.finalize(None)
    first_events = aggregate.pull_events()
    aggregate.finalize(None)
    second_events = aggregate.pull_events()
    assert run.status == RunStatus.ANOMALY
    assert sum(type(event.event).__name__ == "RunFinished" for event in first_events) == 1
    assert second_events == []


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
    assert any(type(event.event).__name__ == "RunModuleRetried" for event in events)


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
    assert any(type(event.event).__name__ == "RunPartialRerunStarted" for event in events)


def test_prepare_partial_rerun_clears_auto_rerun_pending():
    """R4 — 재실행이 실제로 다시 돌기 시작하면 대기 플래그를 내린다.

    내리지 않으면 이 재실행이 다시 실패로 끝나도 완료 메일이 영원히 억제된다(진짜 최종
    결과가 통보되지 않는 사일런트 실패 — 설계상 절대 있어서는 안 됨).
    """
    modules = [_module("a", 0, status=ModuleStatus.ERROR)]
    run = _run(modules, status=RunStatus.ERROR)
    run.auto_rerun_pending = True
    aggregate = RunAggregate(run)

    aggregate.prepare_partial_rerun(0, modules)

    assert run.auto_rerun_pending is False


def test_mark_auto_rerun_pending_sets_flag_and_emits_audit_event():
    run = _run([_module("a", 0, status=ModuleStatus.ERROR)], status=RunStatus.ERROR)
    aggregate = RunAggregate(run)

    aggregate.mark_auto_rerun_pending(from_module_id="a")

    assert run.auto_rerun_pending is True
    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0].event
    assert type(event).__name__ == "RunAutoRerunTriggered"
    assert event.original_run_id == run.run_id
    assert event.from_module_id == "a"


def test_finalize_and_mark_auto_rerun_pending_produce_one_atomic_batch():
    """R4 — 종료와 대기 표식은 한 배치(=한 트랜잭션)로 영속돼야 한다.

    ``finalize()`` 가 표식을 지운 **뒤** ``mark_auto_rerun_pending`` 이 다시 세우는 순서가
    지켜져야 하고(반대면 표식이 지워진 채 남는다), 두 이벤트가 같은 ``pull_events`` 배치에
    들어와야 릴레이가 ``RunFinished`` 를 보는 순간 이미 ``pending=True`` 를 하이드레이션한다.
    """
    run = _run([_module("a", 0, status=ModuleStatus.ERROR)], status=RunStatus.RUNNING)
    aggregate = RunAggregate(run)

    aggregate.finalize(None)
    aggregate.mark_auto_rerun_pending(from_module_id="a")

    assert run.status == RunStatus.ERROR
    assert run.auto_rerun_pending is True
    batch = [type(event.event).__name__ for event in aggregate.pull_events()]
    assert batch == ["RunFinished", "RunAutoRerunTriggered"]


def test_reannounce_finished_reemits_run_finished_and_clears_flag():
    """R4 보상 — 이미 종료된 Run 은 상태를 건드리지 않고 종료만 다시 알린다.

    아웃박스는 발행한 행을 재처리하지 않으므로, 대기 표식만 되돌려서는 새 알림 디스패치가
    생기지 않는다 — 새 ``RunFinished`` 를 한 건 더 내야 릴레이가 다시 하이드레이션한다.
    """
    run = _run([_module("a", 0, status=ModuleStatus.ERROR)], status=RunStatus.ERROR)
    run.auto_rerun_pending = True
    ended_at = run.ended_at
    aggregate = RunAggregate(run)

    status = aggregate.reannounce_finished(fallback_status=RunStatus.ERROR)

    assert status == RunStatus.ERROR
    assert run.auto_rerun_pending is False
    assert run.ended_at == ended_at  # 이미 종료된 Run 의 종료 시각은 다시 쓰지 않는다.
    assert [type(event.event).__name__ for event in aggregate.pull_events()] == ["RunFinished"]


def test_reannounce_finished_reseals_run_that_was_rewound_for_rerun():
    """부분 재실행 준비까지 성공하고 큐잉에서 실패하면, 되감긴 Run 을 다시 봉인해야 한다.

    그 Run 을 실행할 워커가 없으므로 진행 중으로 남겨두면 아무도 알림을 내지 않는다
    (알림 구독자는 비종료 상태를 그냥 건너뛴다).
    """
    modules = [_module("a", 0, status=ModuleStatus.ERROR)]
    run = _run(modules, status=RunStatus.ERROR)
    aggregate = RunAggregate(run)
    aggregate.prepare_partial_rerun(0, modules)
    aggregate.pull_events()
    assert run.status == RunStatus.RUNNING

    status = aggregate.reannounce_finished(fallback_status=RunStatus.ERROR)

    assert status == RunStatus.ERROR
    assert run.status == RunStatus.ERROR
    assert run.ended_at is not None
    assert run.auto_rerun_pending is False
    assert [type(event.event).__name__ for event in aggregate.pull_events()] == ["RunFinished"]


# --- 복구 가시성 -------------------------------------------------------------


def test_record_retry_accumulates_tier_and_signal_history():
    from app.core.enums import FailureSignal, RecoveryTier

    module = _module("a", 0, status=ModuleStatus.RUNNING)
    module.max_attempts = 3
    aggregate = RunAggregate(_run([module]))

    aggregate.record_retry(
        module, tier=RecoveryTier.RETRY_IN_PLACE, failure_signal=FailureSignal.TIMEOUT
    )
    aggregate.record_retry(
        module, tier=RecoveryTier.RESET_TO_MODULE_ENTRY, failure_signal=FailureSignal.DIALOG
    )

    assert module.recovery_tiers == [0, 1]
    assert module.failure_signals == ["TIMEOUT", "DIALOG"]
    assert module.recovered is False  # 아직 통과하지 않았다


def test_record_recovered_marks_module_and_emits_event():
    from app.contexts.run.domain.events import RunModuleRecovered
    from app.core.enums import FailureSignal, RecoveryTier

    module = _module("a", 0, status=ModuleStatus.RUNNING)
    module.max_attempts = 3
    aggregate = RunAggregate(_run([module]))
    aggregate.record_retry(
        module, tier=RecoveryTier.RETRY_IN_PLACE, failure_signal=FailureSignal.TIMEOUT
    )

    aggregate.record_recovered(module)

    assert module.recovered is True
    emitted = [r.event for r in aggregate.pull_events()]
    assert any(isinstance(e, RunModuleRecovered) for e in emitted)


def test_module_without_retry_is_not_marked_recovered():
    module = _module("a", 0, status=ModuleStatus.PASSED)
    aggregate = RunAggregate(_run([module]))

    aggregate.record_recovered(module)

    assert module.recovered is False
