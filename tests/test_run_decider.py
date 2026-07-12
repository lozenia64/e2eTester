"""Run Decider(evolve/fold) — 이벤트가 진실의 원천임을 증명한다.

핵심 불변식: **라이브 애그리거트 스냅샷 == 이벤트 스트림 폴드**. 애그리거트가 상태를
변이하며 발행한 이벤트만으로 ``rebuild_state`` 가 동일한 ``RunSnapshot`` 을 재구성할 수
있으면, blob 없이도 상태가 이벤트에서 유도된다(개선안 #2의 '이벤트=진실').
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import FailureAnalysis, Run, RunModule
from app.domain.run_aggregate import RunAggregate
from app.domain.run_decider import evolve, is_terminal, rebuild_state


def _run(run_id: str = "run_dec") -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PENDING,
        requested_at=datetime(2026, 7, 12, 3, 0, tzinfo=UTC),
        modules=[
            RunModule(
                module_id="hom.access",
                name="접속",
                group="access",
                order=0,
                status=ModuleStatus.PENDING,
                max_attempts=1,
            ),
            RunModule(
                module_id="hom.login",
                name="로그인",
                group="auth",
                order=1,
                depends_on=["hom.access"],
                status=ModuleStatus.PENDING,
                max_attempts=2,
            ),
        ],
        selected_module_ids=["hom.access", "hom.login"],
        triggered_by="manual",
        created_by_user_id="u1",
        created_by_user_name="홍길동",
    )


def _fold(events) -> object:
    return rebuild_state(events)


def _drive_full_run(status_login: ModuleStatus) -> tuple[RunAggregate, list]:
    """생성→시작→access 통과→login 실행→종료까지 애그리거트를 구동하며 이벤트를 모은다."""
    events = []
    run = _run()
    aggregate = RunAggregate.for_new_run(run)
    events += aggregate.pull_events()

    aggregate.begin()
    for module_id in ("hom.access", "hom.login"):
        module = aggregate.module(module_id)
        aggregate.mark_queued(module)
        aggregate.mark_running(module)
        result_status = ModuleStatus.PASSED if module_id == "hom.access" else status_login
        aggregate.record_result(
            module,
            status=result_status,
            message="완료" if result_status == ModuleStatus.PASSED else "이상",
            artifacts=[f"{run.run_id}/{module_id}/final.png"],
            current_url="https://www.hwgeneralins.com/",
            dialog_messages=["dlg"] if module_id == "hom.login" else [],
        )
        aggregate.finish_timing(module)
    aggregate.finalize(None)
    events += aggregate.pull_events()
    return aggregate, events


def test_evolve_reconstructs_live_snapshot_full_pass():
    aggregate, events = _drive_full_run(ModuleStatus.PASSED)
    live = aggregate.to_snapshot()
    folded = _fold(events)
    assert folded == live
    assert folded.status == RunStatus.PASSED
    assert is_terminal(folded)


def test_evolve_reconstructs_live_snapshot_with_anomaly():
    aggregate, events = _drive_full_run(ModuleStatus.ANOMALY)
    live = aggregate.to_snapshot()
    folded = _fold(events)
    assert folded == live
    assert folded.status == RunStatus.ANOMALY
    # 모듈 진단 컨텍스트도 이벤트에서 복원된다(현재 URL·다이얼로그).
    login = next(m for m in folded.modules if m.module_id == "hom.login")
    assert login.status == ModuleStatus.ANOMALY
    assert login.current_url == "https://www.hwgeneralins.com/"
    assert login.dialog_messages == ("dlg",)


def test_evolve_reconstructs_waiting_input_and_resume():
    run = _run("run_otp")
    aggregate = RunAggregate.for_new_run(run)
    events = list(aggregate.pull_events())
    aggregate.begin()
    module = aggregate.module("hom.access")
    aggregate.mark_queued(module)
    aggregate.mark_running(module)
    aggregate.mark_waiting_input(module, "OTP 필요", ["run_otp/hom.access/final.png"])
    events += aggregate.pull_events()

    folded = _fold(events)
    assert folded == aggregate.to_snapshot()
    assert folded.status == RunStatus.WAITING_INPUT
    assert folded.awaiting_input_module_id == "hom.access"

    aggregate.resume_after_input(module)
    events += aggregate.pull_events()
    folded = _fold(events)
    assert folded == aggregate.to_snapshot()
    assert folded.status == RunStatus.RUNNING
    assert folded.awaiting_input_module_id is None


def test_evolve_reconstructs_seal_interrupted():
    run = _run("run_seal")
    aggregate = RunAggregate.for_new_run(run)
    events = list(aggregate.pull_events())
    aggregate.begin()
    aggregate.mark_running(aggregate.module("hom.access"))
    events += aggregate.pull_events()
    assert aggregate.seal_interrupted() is True
    events += aggregate.pull_events()

    folded = _fold(events)
    assert folded == aggregate.to_snapshot()
    assert folded.status == RunStatus.CANCELLED
    assert all(
        m.status == ModuleStatus.CANCELLED for m in folded.modules if m.module_id == "hom.access"
    )


def test_evolve_reconstructs_comparison_and_failure_analysis():
    aggregate, events = _drive_full_run(ModuleStatus.ANOMALY)
    from app.core.models import RunComparison

    aggregate.attach_comparison(
        RunComparison(has_baseline=True, baseline_run_id="run_prev", newly_failed=["로그인"])
    )
    module = aggregate.module("hom.login")
    aggregate.attach_failure_analysis(
        module,
        FailureAnalysis(
            category="selector_broken",
            probable_cause="셀렉터 변경",
            retryable=False,
            user_summary="로그인 버튼 셀렉터가 깨짐",
            developer_details="",
            recommended_action="셀렉터 갱신",
        ),
    )
    events += aggregate.pull_events()

    folded = _fold(events)
    assert folded == aggregate.to_snapshot()
    assert folded.comparison is not None
    assert folded.comparison.newly_failed == ["로그인"]
    login = next(m for m in folded.modules if m.module_id == "hom.login")
    assert login.failure_analysis is not None
    assert login.failure_analysis.category == "selector_broken"


def test_empty_stream_folds_to_none():
    assert _fold([]) is None


def test_single_run_created_event_initializes_modules():
    run = _run("run_init")
    aggregate = RunAggregate.for_new_run(run)
    created = aggregate.pull_events()
    assert len(created) == 1
    folded = evolve(None, created[0])
    assert folded.run_id == "run_init"
    assert {m.module_id for m in folded.modules} == {"hom.access", "hom.login"}
    assert folded.status == RunStatus.PENDING
