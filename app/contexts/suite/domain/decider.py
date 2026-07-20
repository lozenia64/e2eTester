"""Suite Decider — 이벤트를 진실의 원천으로 만드는 순수 decide/evolve(Run 과 동형).

Suite 이벤트는 발행 시점의 **전체 상태**를 ``suite_summary`` 로 동봉하므로(fat event,
``SuiteAggregate._emit``), ``evolve`` 는 마지막 이벤트의 요약으로 스냅샷을 통째로 재구성한다
(모듈 단위 부분 갱신이 없는, 스텝-요약이 곧 전체 상태인 구조). ``decide`` 는 불변 상태의
일회용 복제본에 애그리거트를 씌워 전이를 수행하고 산출 이벤트만 돌려준다(순수).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contexts.suite.domain.events import SuiteEventRecord, SuiteSummaryWire
from app.core.enums import SuiteStatus
from app.domain.snapshots import SuiteSnapshot, SuiteStepSnapshot

_TERMINAL = {
    SuiteStatus.PASSED,
    SuiteStatus.ANOMALY,
    SuiteStatus.ERROR,
    SuiteStatus.FAILED,
    SuiteStatus.CANCELLED,
}


def is_terminal(state: SuiteSnapshot) -> bool:
    return state.status in _TERMINAL


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _snapshot_from_summary(suite_id: str, summary: SuiteSummaryWire) -> SuiteSnapshot:
    return SuiteSnapshot(
        suite_id=suite_id,
        status=SuiteStatus(summary["status"]),
        steps=tuple(
            SuiteStepSnapshot(
                system_code=step["system_code"],
                system_name=step["system_name"],
                order=step["order"],
                run_id=step.get("run_id"),
                status=SuiteStatus(step["status"]),
                module_total=step.get("module_total", 0),
            )
            for step in summary.get("steps", [])
        ),
        current_step_index=summary.get("current_step_index", 0),
        requested_at=_parse_dt(summary["requested_at"]) or datetime(1970, 1, 1, tzinfo=UTC),
        started_at=_parse_dt(summary.get("started_at")),
        ended_at=_parse_dt(summary.get("ended_at")),
        active_run_id=summary.get("active_run_id"),
        awaiting_input_run_id=summary.get("awaiting_input_run_id"),
        awaiting_input_prompt=summary.get("awaiting_input_prompt"),
        browser_mode=summary.get("browser_mode", "headed"),
        selected_system_codes=tuple(summary.get("selected_system_codes", [])),
        created_by_user_id=summary.get("created_by_user_id"),
        created_by_user_name=summary.get("created_by_user_name"),
        triggered_by=summary.get("triggered_by", "manual"),
        schedule_id=summary.get("schedule_id"),
    )


def evolve(
    state: SuiteSnapshot | None, record: SuiteEventRecord, *, suite_id: str
) -> SuiteSnapshot | None:
    """이벤트 한 건을 접어 새 Suite 상태를 만든다(순수).

    모든 Suite 이벤트가 ``suite_summary`` 로 전체 상태를 실어 나르므로, 최신 이벤트의 요약으로
    스냅샷을 통째로 재구성한다.
    """
    return _snapshot_from_summary(suite_id, record.suite_summary)


def rebuild_state(events: list[SuiteEventRecord], *, suite_id: str) -> SuiteSnapshot | None:
    """Suite 이벤트 스트림 전체를 접어 권위 있는 상태를 재구성한다(없으면 None)."""
    state: SuiteSnapshot | None = None
    for record in events:
        state = evolve(state, record, suite_id=suite_id)
    return state


def decide(command, state: SuiteSnapshot):
    """커맨드 + 현재 상태 → 결과 이벤트 목록(순수). Run ``decide`` 와 동형.

    상태 변이·이벤트 발행 규칙은 ``SuiteAggregate`` 에 응축돼 있으므로, 불변 상태의 일회용
    복제본(``state.to_suite()``)에 애그리거트를 씌워 전이를 수행하고 산출 이벤트만 돌려준다 —
    입력 ``state`` 는 건드리지 않는다(순수).
    """
    from app.contexts.suite.domain import commands as c
    from app.contexts.suite.domain.aggregate import SuiteAggregate

    suite = state.to_suite()
    aggregate = SuiteAggregate(suite)

    if isinstance(command, c.BeginSuite):
        aggregate.begin()
    elif isinstance(command, c.StartStep):
        aggregate.start_step(command.index)
    elif isinstance(command, c.LinkRun):
        aggregate.link_run(suite.steps[command.step_index], command.run_id)
    elif isinstance(command, c.MarkStepError):
        aggregate.mark_step_error(
            suite.steps[command.step_index], step_index=command.step_index, error=command.error
        )
    elif isinstance(command, c.RecordStepResult):
        aggregate.record_step_result(
            suite.steps[command.step_index], command.status, step_index=command.step_index
        )
    elif isinstance(command, c.MarkWaitingInput):
        aggregate.mark_waiting_input(command.run_id, command.prompt)
    elif isinstance(command, c.MarkResumed):
        aggregate.mark_resumed()
    elif isinstance(command, c.FinalizeSuite):
        aggregate.finalize(command.status, cancel_remaining=command.cancel_remaining)
    elif isinstance(command, c.SealInterrupted):
        aggregate.seal_interrupted()
    else:  # pragma: no cover - 방어적
        raise TypeError(f"알 수 없는 Suite 커맨드: {type(command).__name__}")

    return aggregate.pull_events()
