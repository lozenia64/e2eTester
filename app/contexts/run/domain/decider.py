"""Run Decider — 이벤트를 **진실의 원천**으로 만드는 순수 fold(evolve).

개선안 #2의 핵심: Run 상태는 blob 이 아니라 **도메인 이벤트 스트림에서 유도**된다.
``evolve(state, event) -> state`` 는 한 이벤트를 접어 새 상태를 만들고, ``rebuild_state(events)``
는 스트림 전체를 접어 권위 있는 ``RunSnapshot`` 을 재구성한다. blob(``aggregate_snapshots``)은
이 fold 의 파생 캐시일 뿐이며, ``tests/test_run_decider.py`` 가 "라이브 애그리거트 스냅샷 ==
이벤트 폴드"를 증명해 evolve 완전성(모든 상태 전이가 이벤트로 복원 가능)을 보장한다.

이 모듈은 순수하다 — ``await`` 없음, 저장소/게이트웨이/이벤트버스 import 없음(시계도 안 봄).
상태 타입은 이미 존재하는 불변 ``RunSnapshot``/``ModuleSnapshot`` 을 그대로 쓴다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import FailureAnalysis, RunComparison
from app.domain.events import DomainEvent
from app.domain.snapshots import ModuleSnapshot, RunSnapshot

# 종료(더 이상 전이하지 않는) Run 상태들.
_TERMINAL = {
    RunStatus.PASSED,
    RunStatus.ANOMALY,
    RunStatus.ERROR,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


def is_terminal(state: RunSnapshot) -> bool:
    return state.status in _TERMINAL


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _module_from_wire(wire: dict) -> ModuleSnapshot:
    """이벤트에 실린 모듈 와이어 dict(``RunModule`` 직렬화, 로그 제외) → 불변 모듈 스냅샷."""
    analysis = wire.get("failure_analysis")
    return ModuleSnapshot(
        module_id=wire["module_id"],
        name=wire["name"],
        group=wire["group"],
        order=wire["order"],
        status=ModuleStatus(wire["status"]),
        depends_on=tuple(wire.get("depends_on", [])),
        started_at=_parse_dt(wire.get("started_at")),
        ended_at=_parse_dt(wire.get("ended_at")),
        duration_ms=wire.get("duration_ms"),
        retry_count=wire.get("retry_count", 0),
        attempt=wire.get("attempt", 1),
        max_attempts=wire.get("max_attempts", 1),
        message=wire.get("message", ""),
        artifact_count=wire.get("artifact_count", 0),
        artifacts=tuple(wire.get("artifacts", [])),
        logs=(),  # 로그는 별도 집합체 소유 — 이벤트/상태에 담지 않는다.
        current_url=wire.get("current_url"),
        dialog_messages=tuple(wire.get("dialog_messages", [])),
        failure_analysis=None if analysis is None else FailureAnalysis(**analysis),
    )


def _apply_run_summary(state: RunSnapshot, summary: dict) -> RunSnapshot:
    """모든 상태 전이 이벤트에 동봉된 run_summary 로 런레벨 필드를 갱신한다."""
    comparison = summary.get("comparison")
    return replace(
        state,
        system_code=summary.get("system_code", state.system_code),
        system_name=summary.get("system_name", state.system_name),
        status=RunStatus(summary["status"]) if "status" in summary else state.status,
        requested_at=_parse_dt(summary.get("requested_at")) or state.requested_at,
        started_at=_parse_dt(summary.get("started_at")),
        ended_at=_parse_dt(summary.get("ended_at")),
        awaiting_input_module_id=summary.get("awaiting_input_module_id"),
        awaiting_input_prompt=summary.get("awaiting_input_prompt"),
        triggered_by=summary.get("triggered_by", state.triggered_by),
        schedule_id=summary.get("schedule_id"),
        suite_id=summary.get("suite_id"),
        selected_module_ids=tuple(summary.get("selected_module_ids", state.selected_module_ids)),
        created_by_user_id=summary.get("created_by_user_id"),
        created_by_user_name=summary.get("created_by_user_name"),
        comparison=None if comparison is None else RunComparison(**comparison),
    )


def _replace_module(state: RunSnapshot, wire: dict) -> RunSnapshot:
    updated = _module_from_wire(wire)
    modules = tuple(
        updated if module.module_id == updated.module_id else module for module in state.modules
    )
    return replace(state, modules=modules)


_EMPTY = RunSnapshot(
    run_id="",
    system_code="",
    system_name="",
    status=RunStatus.PENDING,
    requested_at=datetime(1970, 1, 1, tzinfo=UTC),
    started_at=None,
    ended_at=None,
    modules=(),
    selected_module_ids=(),
    awaiting_input_module_id=None,
    awaiting_input_prompt=None,
    triggered_by="manual",
    schedule_id=None,
    suite_id=None,
    comparison=None,
    created_by_user_id=None,
    created_by_user_name=None,
)


def evolve(state: RunSnapshot | None, event: DomainEvent) -> RunSnapshot:
    """이벤트 한 건을 접어 새 Run 상태를 만든다(순수).

    규약:
    - ``RunCreated`` : 빈 상태에서 초기화(런레벨은 run_summary, 모듈은 all_modules).
    - ``all_modules`` 를 실은 벌크 전이(SealedInterrupted/PartialRerun): 모듈 전체 교체.
    - ``modules``(RunModulesCancelled): 나열된 모듈만 교체.
    - ``module``(단일 모듈 전이): 그 모듈만 교체.
    - 모든 이벤트: run_summary 가 있으면 런레벨 필드 갱신(status/시각/awaiting/comparison 포함).
    """
    base = state if state is not None else _EMPTY
    payload = event.payload

    # RunImported(레거시 마이그레이션 genesis)는 RunCreated 와 동일하게 빈 상태에서 최종 상태를
    # 초기화한다 — run_summary 로 런레벨, all_modules 로 모듈 전체를 세운다.
    if event.event_type in ("RunCreated", "RunImported"):
        base = replace(_EMPTY, run_id=event.aggregate_id)
        summary = payload.get("run_summary")
        if summary is not None:
            base = _apply_run_summary(base, summary)
        base = replace(
            base, modules=tuple(_module_from_wire(m) for m in payload.get("all_modules", []))
        )
        return base

    if not base.run_id:
        base = replace(base, run_id=event.aggregate_id)

    summary = payload.get("run_summary")
    if summary is not None:
        base = _apply_run_summary(base, summary)

    if "all_modules" in payload and payload["all_modules"]:
        base = replace(base, modules=tuple(_module_from_wire(m) for m in payload["all_modules"]))
    elif payload.get("modules"):
        for wire in payload["modules"]:
            base = _replace_module(base, wire)
    elif payload.get("module"):
        base = _replace_module(base, payload["module"])

    return base


def rebuild_state(events: list[DomainEvent]) -> RunSnapshot | None:
    """Run 이벤트 스트림 전체를 접어 권위 있는 상태를 재구성한다(없으면 None)."""
    state: RunSnapshot | None = None
    for event in events:
        state = evolve(state, event)
    return state


def decide(command, state: RunSnapshot):
    """커맨드 + 현재 상태 → 결과 이벤트 목록(순수).

    Decider 패턴의 ``decide``: 의도(커맨드)를 받아 상태 전이 이벤트를 산출한다. 상태 변이·이벤트
    발행 규칙은 이미 ``RunAggregate`` 에 응축돼 있으므로, 여기서는 불변 상태의 **일회용 복제본**
    (``state.to_run()``)에 애그리거트를 씌워 해당 전이를 수행하고 산출 이벤트만 돌려준다 —
    입력 ``state`` 는 건드리지 않는다(순수). 이렇게 하면 ``decide`` 가 만드는 이벤트가 기존
    쓰기 경로의 이벤트와 **정확히 동일**함이 구조적으로 보장되고(요약·모듈 와이어 동봉 포함),
    ``evolve`` 로 그 이벤트를 접으면 다시 같은 상태가 나온다(fold 왕복 = 진실).

    인터프리터(``RunService``, WP-B4)는 ``state=load(); events=decide(cmd, state);
    append(events)`` 패턴으로 이 함수를 호출한다.
    """
    # 순환 import 회피(run_aggregate → 이 모듈을 import 하지 않지만, 계층 명확화를 위해 지연).
    from app.contexts.run.domain import commands as c
    from app.contexts.run.domain.aggregate import RunAggregate

    aggregate = RunAggregate(state.to_run())

    if isinstance(command, c.BeginRun):
        aggregate.begin()
    elif isinstance(command, c.BlockModule):
        aggregate.block_for_dependencies(aggregate.module(command.module_id))
    elif isinstance(command, c.QueueModule):
        aggregate.mark_queued(aggregate.module(command.module_id))
    elif isinstance(command, c.StartModule):
        aggregate.mark_running(aggregate.module(command.module_id))
    elif isinstance(command, c.RecordStepResult):
        module = aggregate.module(command.module_id)
        aggregate.record_result(
            module,
            status=command.status,
            message=command.message,
            artifacts=list(command.artifacts),
            current_url=command.current_url,
            dialog_messages=list(command.dialog_messages),
        )
        aggregate.finish_timing(module)
    elif isinstance(command, c.FailModule):
        aggregate.fail_module(aggregate.module(command.module_id), command.message)
    elif isinstance(command, c.MarkModuleFatal):
        aggregate.mark_fatal(aggregate.module(command.module_id), command.message)
    elif isinstance(command, c.RetryModule):
        aggregate.record_retry(aggregate.module(command.module_id))
    elif isinstance(command, c.PauseForInput):
        aggregate.mark_waiting_input(
            aggregate.module(command.module_id), command.message, list(command.artifacts)
        )
    elif isinstance(command, c.ResumeAfterInput):
        aggregate.resume_after_input(aggregate.module(command.module_id))
    elif isinstance(command, c.CancelModules):
        ordered = [aggregate.module(mid) for mid in command.module_ids]
        aggregate.cancel_modules(ordered)
    elif isinstance(command, c.PreparePartialRerun):
        aggregate.prepare_partial_rerun(
            command.from_index, list(aggregate.persistable_state().modules)
        )
    elif isinstance(command, c.AttachComparison):
        aggregate.attach_comparison(command.comparison)
    elif isinstance(command, c.AttachFailureAnalysis):
        aggregate.attach_failure_analysis(aggregate.module(command.module_id), command.analysis)
    elif isinstance(command, c.FinalizeRun):
        aggregate.finalize(command.forced_status)
    elif isinstance(command, c.SealInterrupted):
        aggregate.seal_interrupted()
    else:  # pragma: no cover - 방어적: 알 수 없는 커맨드
        raise TypeError(f"알 수 없는 Run 커맨드: {type(command).__name__}")

    return aggregate.pull_events()
