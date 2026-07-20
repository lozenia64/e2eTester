from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.contexts.suite.domain.events import (
    SuiteCreated,
    SuiteEvent,
    SuiteEventRecord,
    SuiteFinished,
    SuiteResumed,
    SuiteStarted,
    SuiteStepFinished,
    SuiteStepRunLinked,
    SuiteStepStarted,
    SuiteWaitingInput,
)
from app.core.enums import SuiteStatus
from app.core.status_labels import SUITE_ANOMALY_STATUSES, SUITE_ERROR_STATUSES
from app.core.suite_models import SuiteRun, SuiteStep
from app.domain.snapshots import SuiteSnapshot
from app.domain.summary_fields import suite_summary_fields

# 더 이상 전이시키지 않는(이미 끝난) 상태들.

_SUITE_TERMINAL = {
    SuiteStatus.PASSED,
    SuiteStatus.ANOMALY,
    SuiteStatus.ERROR,
    SuiteStatus.FAILED,
    SuiteStatus.CANCELLED,
}

_STEP_TERMINAL = {
    SuiteStatus.PASSED,
    SuiteStatus.ANOMALY,
    SuiteStatus.ERROR,
    SuiteStatus.FAILED,
    SuiteStatus.CANCELLED,
    SuiteStatus.SKIPPED,
}

# 재기동 봉인 대상이 되는 "아직 진행 중" 상태들.

_SUITE_ACTIVE = {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}


class SuiteAggregate:
    """Suite 사가의 **상태 변이와 불변식** 을 소유하는 도메인 애그리거트.



    ``RunAggregate`` 와 **동형(isomorphic)** 이다. ``SuiteRun`` Pydantic 모델(영속/직렬화 가능한

    상태)을 감싸고, 합법한 상태 전이만 수행하는 순수 메서드를 노출한다. 이 클래스의 어떤

    메서드도 ``await`` 하지 않고, 저장소·이벤트 버스·``RunService`` 를 import 하지 않는다

    (시계만 참조). 따라서 과거 ``SuiteService`` 곳곳에 ``suite.status = ...`` / ``step.status =

    ...`` 로 흩어져 있던 "스텝 결과 기록 / 종료 상태 판정 / 취소 마킹 / 재기동 봉인" 규칙을,

    I/O 없이 단독으로 단위 테스트할 수 있는 한곳으로 모은다.



    사가(``SuiteService``)는 *순서*(스텝 시작 → RunFinished 대기 → 다음 스텝)와 *부작용*

    (save_suite·WebSocket 이벤트·하위 Run 명령)만 책임지고, 각 단계의 *변경* 은 이 애그리거트에

    위임한다.

    """

    def __init__(self, suite: SuiteRun) -> None:

        self._state = suite

        self._pending_events: list[SuiteEventRecord] = []

    def to_snapshot(self) -> SuiteSnapshot:
        """현재 Suite 상태의 불변 읽기 스냅샷."""

        return SuiteSnapshot.from_suite(self._state)

    def persistable_state(self) -> SuiteRun:
        """영속·이벤트 발행용 쓰기 모델(저장소 계층 전용)."""

        return self._state

    def pull_events(self) -> list[SuiteEventRecord]:
        """누적된 도메인 이벤트를 꺼내고 내부 버퍼를 비운다(영속/outbox 기록 직전)."""

        pulled = list(self._pending_events)

        self._pending_events.clear()

        return pulled

    @classmethod
    def for_new_suite(cls, suite: SuiteRun) -> SuiteAggregate:
        """신규 Suite 생성 시 ``SuiteCreated`` 이벤트를 함께 산출한다."""

        aggregate = cls(suite)

        aggregate._emit(SuiteCreated(triggered_by=suite.triggered_by))

        return aggregate

    def _emit(self, event: SuiteEvent) -> None:
        """이벤트를 버퍼에 쌓는다 — 변이 **후** 호출되므로 요약은 사후 상태를 반영한다.

        Suite 요약 인덱스 프로젝션이 blob 을 재수화하지 않도록 모든 이벤트에
        ``suite_summary`` 섹션을 동봉한다(fat event; ``RunAggregate._emit`` 와 동형).
        """
        self._pending_events.append(
            SuiteEventRecord(
                event=event,
                suite_summary=suite_summary_fields(self._state),
                event_id=uuid4().hex,
                occurred_at=datetime.now(UTC),
            )
        )

    # --- 조회(규칙/판정) --------------------------------------------------

    def is_terminal(self) -> bool:

        return self._state.status in _SUITE_TERMINAL

    def is_step_terminal(self, step: SuiteStep) -> bool:

        return step.status in _STEP_TERMINAL

    def find_step(self, run_id: str) -> tuple[int, SuiteStep | None]:
        """하위 Run id 로 그 스텝을 찾는다. 없으면 ``(-1, None)``."""

        for index, step in enumerate(self._state.steps):
            if step.run_id == run_id:
                return index, step

        return -1, None

    def next_pending_index(self) -> int | None:
        """다음으로 실행할 PENDING 스텝의 인덱스(없으면 None)."""

        for index, step in enumerate(self._state.steps):
            if step.status == SuiteStatus.PENDING:
                return index

        return None

    def compute_final_status(self) -> SuiteStatus:
        """Suite 종료 상태 판정 규칙: ERROR > ANOMALY > PASSED."""

        if any(step.status in SUITE_ERROR_STATUSES for step in self._state.steps):
            return SuiteStatus.ERROR

        if any(step.status in SUITE_ANOMALY_STATUSES for step in self._state.steps):
            return SuiteStatus.ANOMALY

        return SuiteStatus.PASSED

    # --- 명령(순수 상태 전이) ---------------------------------------------

    def begin(self) -> None:
        """Suite 실행 시작: RUNNING + started_at."""

        self._state.status = SuiteStatus.RUNNING

        self._state.started_at = datetime.now(UTC)

        self._emit(SuiteStarted())

    def start_step(self, index: int) -> SuiteStep:
        """다음 스텝을 RUNNING 으로 전이하고 현재 스텝 포인터를 옮긴다(아직 Run 미연결)."""

        step = self._state.steps[index]

        self._state.current_step_index = index

        step.status = SuiteStatus.RUNNING

        self._state.active_run_id = None

        self._emit(SuiteStepStarted(index))

        return step

    def link_run(self, step: SuiteStep, run_id: str) -> None:
        """시작된 하위 Run 을 스텝/Suite 에 연결한다."""

        step.run_id = run_id

        self._state.active_run_id = run_id

        self._emit(
            SuiteStepRunLinked(
                step_index=self._state.current_step_index,
                run_id=run_id,
            )
        )

    def mark_step_error(self, step: SuiteStep, *, step_index: int, error: str) -> None:
        """스텝 진입(하위 Run 시작) 자체가 실패함 → 스텝을 ERROR 로 종료한다."""

        step.status = SuiteStatus.ERROR

        self._emit(SuiteStepFinished(step_index=step_index, error=error))

    def record_step_result(self, step: SuiteStep, status: SuiteStatus, *, step_index: int) -> None:
        """하위 Run 종료 결과를 스텝에 반영하고 활성/입력대기 포인터를 정리한다."""

        step.status = status

        self._state.active_run_id = None

        self._state.awaiting_input_run_id = None

        self._state.awaiting_input_prompt = None

        self._emit(SuiteStepFinished(step_index=step_index))

    def mark_waiting_input(self, run_id: str, prompt: str | None) -> None:
        """하위 Run 이 OTP 대기로 일시정지함 → Suite 도 입력 대기로 미러링한다."""

        self._state.status = SuiteStatus.WAITING_INPUT

        self._state.awaiting_input_run_id = run_id

        self._state.awaiting_input_prompt = prompt

        self._emit(SuiteWaitingInput(run_id=run_id))

    def mark_resumed(self) -> None:
        """하위 Run 이 입력 접수 후 재개됨 → Suite 를 RUNNING 으로 되돌린다."""

        self._state.status = SuiteStatus.RUNNING

        self._state.awaiting_input_run_id = None

        self._state.awaiting_input_prompt = None

        self._emit(SuiteResumed())

    def finalize(self, status: SuiteStatus, *, cancel_remaining: bool = False) -> None:
        """Suite 를 종료 상태로 봉인한다(영속·이벤트 발행은 호출자 책임).

        ``cancel_remaining`` 이면 아직 끝나지 않은 스텝을 모두 CANCELLED 로 봉인한다.
        """
        if self._state.status in _SUITE_TERMINAL:
            return
        if cancel_remaining:
            for step in self._state.steps:
                if step.status not in _STEP_TERMINAL:
                    step.status = SuiteStatus.CANCELLED

        self._state.status = status

        self._state.ended_at = datetime.now(UTC)

        self._state.active_run_id = None

        self._state.awaiting_input_run_id = None

        self._state.awaiting_input_prompt = None

        self._emit(SuiteFinished(status=status))

    def seal_interrupted(self) -> bool:
        """재기동으로 이어받을 수 없는 진행 중 Suite 를 CANCELLED 로 봉인한다.



        실제로 봉인했으면 True. 이미 종료 상태면 아무것도 하지 않고 False.

        """

        if self._state.status not in _SUITE_ACTIVE:
            return False

        self._state.status = SuiteStatus.CANCELLED

        self._state.ended_at = self._state.ended_at or datetime.now(UTC)

        self._state.active_run_id = None

        self._state.awaiting_input_run_id = None

        self._state.awaiting_input_prompt = None

        for step in self._state.steps:
            if step.status in _SUITE_ACTIVE:
                step.status = SuiteStatus.CANCELLED

        self._emit(SuiteFinished(status=SuiteStatus.CANCELLED))

        return True
