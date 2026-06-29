from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import SuiteStatus
from app.core.models import SuiteRun, SuiteStep
from app.core.status_labels import SUITE_ANOMALY_STATUSES, SUITE_ERROR_STATUSES

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
        self.suite = suite

    # --- 조회(규칙/판정) --------------------------------------------------

    def is_terminal(self) -> bool:
        return self.suite.status in _SUITE_TERMINAL

    def is_step_terminal(self, step: SuiteStep) -> bool:
        return step.status in _STEP_TERMINAL

    def find_step(self, run_id: str) -> tuple[int, SuiteStep | None]:
        """하위 Run id 로 그 스텝을 찾는다. 없으면 ``(-1, None)``."""
        for index, step in enumerate(self.suite.steps):
            if step.run_id == run_id:
                return index, step
        return -1, None

    def next_pending_index(self) -> int | None:
        """다음으로 실행할 PENDING 스텝의 인덱스(없으면 None)."""
        for index, step in enumerate(self.suite.steps):
            if step.status == SuiteStatus.PENDING:
                return index
        return None

    def compute_final_status(self) -> SuiteStatus:
        """Suite 종료 상태 판정 규칙: ERROR > ANOMALY > PASSED."""
        if any(step.status in SUITE_ERROR_STATUSES for step in self.suite.steps):
            return SuiteStatus.ERROR
        if any(step.status in SUITE_ANOMALY_STATUSES for step in self.suite.steps):
            return SuiteStatus.ANOMALY
        return SuiteStatus.PASSED

    # --- 명령(순수 상태 전이) ---------------------------------------------

    def begin(self) -> None:
        """Suite 실행 시작: RUNNING + started_at."""
        self.suite.status = SuiteStatus.RUNNING
        self.suite.started_at = datetime.now(UTC)

    def start_step(self, index: int) -> SuiteStep:
        """다음 스텝을 RUNNING 으로 전이하고 현재 스텝 포인터를 옮긴다(아직 Run 미연결)."""
        step = self.suite.steps[index]
        self.suite.current_step_index = index
        step.status = SuiteStatus.RUNNING
        self.suite.active_run_id = None
        return step

    def link_run(self, step: SuiteStep, run_id: str) -> None:
        """시작된 하위 Run 을 스텝/Suite 에 연결한다."""
        step.run_id = run_id
        self.suite.active_run_id = run_id

    def mark_step_error(self, step: SuiteStep) -> None:
        """스텝 진입(하위 Run 시작) 자체가 실패함 → 스텝을 ERROR 로 종료한다."""
        step.status = SuiteStatus.ERROR

    def record_step_result(self, step: SuiteStep, status: SuiteStatus) -> None:
        """하위 Run 종료 결과를 스텝에 반영하고 활성/입력대기 포인터를 정리한다."""
        step.status = status
        self.suite.active_run_id = None
        self.suite.awaiting_input_run_id = None
        self.suite.awaiting_input_prompt = None

    def mark_waiting_input(self, run_id: str, prompt: str | None) -> None:
        """하위 Run 이 OTP 대기로 일시정지함 → Suite 도 입력 대기로 미러링한다."""
        self.suite.status = SuiteStatus.WAITING_INPUT
        self.suite.awaiting_input_run_id = run_id
        self.suite.awaiting_input_prompt = prompt

    def mark_resumed(self) -> None:
        """하위 Run 이 입력 접수 후 재개됨 → Suite 를 RUNNING 으로 되돌린다."""
        self.suite.status = SuiteStatus.RUNNING
        self.suite.awaiting_input_run_id = None
        self.suite.awaiting_input_prompt = None

    def finalize(self, status: SuiteStatus, *, cancel_remaining: bool = False) -> None:
        """Suite 를 종료 상태로 봉인한다(영속·이벤트 발행은 호출자 책임).

        ``cancel_remaining`` 이면 아직 끝나지 않은 스텝을 모두 CANCELLED 로 봉인한다.
        """
        if cancel_remaining:
            for step in self.suite.steps:
                if step.status not in _STEP_TERMINAL:
                    step.status = SuiteStatus.CANCELLED
        self.suite.status = status
        self.suite.ended_at = datetime.now(UTC)
        self.suite.active_run_id = None
        self.suite.awaiting_input_run_id = None
        self.suite.awaiting_input_prompt = None

    def seal_interrupted(self) -> bool:
        """재기동으로 이어받을 수 없는 진행 중 Suite 를 CANCELLED 로 봉인한다.

        실제로 봉인했으면 True. 이미 종료 상태면 아무것도 하지 않고 False.
        """
        if self.suite.status not in _SUITE_ACTIVE:
            return False
        self.suite.status = SuiteStatus.CANCELLED
        self.suite.ended_at = self.suite.ended_at or datetime.now(UTC)
        self.suite.active_run_id = None
        self.suite.awaiting_input_run_id = None
        self.suite.awaiting_input_prompt = None
        for step in self.suite.steps:
            if step.status in _SUITE_ACTIVE:
                step.status = SuiteStatus.CANCELLED
        return True
