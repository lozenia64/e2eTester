from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run, RunModule
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES
from app.domain import events as domain_events
from app.domain.events import DomainEvent
from app.domain.snapshots import RunSnapshot
from app.domain.summary_fields import run_summary_fields

# 요약 동봉을 생략하는 이벤트: 로그 스트리밍 핫패스(라인마다 요약 재계산은 낭비이고,
# 로그는 요약 인덱스의 어떤 컬럼도 바꾸지 않는다).
_NO_SUMMARY_EVENT_TYPES = {"ModuleLogAppended"}

# 더 이상 전이시키지 않는(이미 끝난) 모듈 상태들.
_MODULE_TERMINAL = {
    ModuleStatus.PASSED,
    ModuleStatus.ANOMALY,
    ModuleStatus.ERROR,
    ModuleStatus.FAILED,
    ModuleStatus.SKIPPED,
    ModuleStatus.BLOCKED,
    ModuleStatus.CANCELLED,
}
# 재기동 봉인 대상이 되는 "아직 진행 중" 상태들.
_RUN_ACTIVE = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
_MODULE_ACTIVE = {
    ModuleStatus.PENDING,
    ModuleStatus.QUEUED,
    ModuleStatus.RUNNING,
    ModuleStatus.WAITING_INPUT,
}


class RunAggregate:
    """Run 상태머신의 **규칙과 불변식**을 소유하는 도메인 애그리거트.

    ``Run`` Pydantic 모델(영속/직렬화 가능한 상태)을 감싸고, 합법한 상태 전이만 수행하는
    순수 메서드를 노출한다. 이 클래스의 어떤 메서드도 ``await`` 하지 않고, 저장소·게이트웨이·
    이벤트 버스를 import 하지 않는다(시계만 참조). 따라서 오케스트레이터(``RunService``)의
    실행 루프에 흩어져 있던 "선행 모듈 차단 / 결과 기록 / 종료 상태 판정 / 취소 마킹" 같은
    규칙을, I/O 없이 단독으로 단위 테스트할 수 있는 한곳으로 모은다.

    오케스트레이터는 *순서*(queued → sleep → running → 게이트웨이 실행 → 결과 기록)와
    *부작용*(save_run·WebSocket 이벤트·게이트웨이 호출)만 책임지고, 각 단계의 *결정·변경*은
    이 애그리거트에 위임한다.
    """

    def __init__(self, run: Run) -> None:
        self._state = run
        self._modules_by_id = {module.module_id: module for module in run.modules}
        self._pending_events: list[DomainEvent] = []

    def to_snapshot(self) -> RunSnapshot:
        """현재 Run 상태의 불변 읽기 스냅샷."""
        return RunSnapshot.from_run(self._state)

    def persistable_state(self) -> Run:
        """영속·이벤트 발행용 쓰기 모델(저장소 계층 전용)."""
        return self._state

    def pull_events(self) -> list[DomainEvent]:
        """누적된 도메인 이벤트를 꺼내고 내부 버퍼를 비운다(영속/outbox 기록 직전)."""
        pulled = list(self._pending_events)
        self._pending_events.clear()
        return pulled

    @classmethod
    def for_new_run(cls, run: Run) -> RunAggregate:
        """신규 Run 생성 시 ``RunCreated`` 이벤트를 함께 산출한다."""
        aggregate = cls(run)
        aggregate._emit(
            domain_events.run_created(
                run.run_id,
                run.system_code,
                run.triggered_by,
            )
        )
        return aggregate

    def _emit(self, event: DomainEvent) -> None:
        """이벤트를 버퍼에 쌓는다 — 변이 **후** 호출되므로 요약은 사후 상태를 반영한다.

        요약 인덱스 프로젝션이 blob 을 재수화하지 않도록, 상태를 바꾸는 모든 이벤트에
        ``run_summary`` 섹션(파생 요약 필드)을 동봉한다(fat event).
        """
        if event.event_type not in _NO_SUMMARY_EVENT_TYPES:
            event = replace(
                event,
                payload={**event.payload, "run_summary": run_summary_fields(self._state)},
            )
        self._pending_events.append(event)

    # --- 조회(규칙/판정) --------------------------------------------------

    def module(self, module_id: str) -> RunModule:
        try:
            return self._modules_by_id[module_id]
        except KeyError as exc:
            raise KeyError(f"Run module not found: {module_id}") from exc

    def dependencies_satisfied(self, module: RunModule) -> bool:
        """선행 모듈이 모두 PASSED 인지(아니면 이 모듈은 차단되어야 한다)."""
        return all(
            self._modules_by_id[dependency].status == ModuleStatus.PASSED
            for dependency in module.depends_on
        )

    def has_module_error(self) -> bool:
        return any(module.status in MODULE_ERROR_STATUSES for module in self._state.modules)

    def has_module_anomaly(self) -> bool:
        return any(module.status in MODULE_ANOMALY_STATUSES for module in self._state.modules)

    def compute_final_status(self, forced_status: RunStatus | None) -> RunStatus:
        """종료 시점의 Run 상태 판정 규칙(강제 상태가 있으면 그것이 우선).

        우선순위: ERROR > ANOMALY > PASSED
        """
        if forced_status is not None:
            return forced_status
        if self.has_module_error():
            return RunStatus.ERROR
        if self.has_module_anomaly():
            return RunStatus.ANOMALY
        return RunStatus.PASSED

    def select_failure_target(
        self,
        current_module: RunModule | None,
        ordered_modules: list[RunModule],
    ) -> RunModule | None:
        """예상치 못한 실행 오류를 귀속시킬 모듈을 고른다.

        진행 중이던 모듈이 있으면 그 모듈에, 없으면 아직 실행되지 않은 첫 모듈에 귀속한다.
        """
        if current_module is not None and current_module.status in {
            ModuleStatus.QUEUED,
            ModuleStatus.RUNNING,
        }:
            return current_module
        for module in ordered_modules:
            if module.status in {ModuleStatus.PENDING, ModuleStatus.QUEUED, ModuleStatus.RUNNING}:
                return module
        return None

    # --- 명령(순수 상태 전이) ---------------------------------------------

    def begin(self) -> None:
        """Run 실행 시작: RUNNING + started_at."""
        self._state.status = RunStatus.RUNNING
        self._state.started_at = datetime.now(UTC)
        self._emit(domain_events.run_started(self._state.run_id))

    def block_for_dependencies(self, module: RunModule) -> None:
        module.status = ModuleStatus.BLOCKED
        module.message = "선행 모듈 실패로 인해 실행되지 않음"
        self._emit(domain_events.run_module_blocked(self._state.run_id, module.module_id))

    def mark_queued(self, module: RunModule) -> None:
        module.status = ModuleStatus.QUEUED
        module.message = "실행 대기열에 등록됨"
        module.failure_analysis = None
        self._emit(domain_events.module_queued(self._state.run_id, module.module_id))

    def mark_running(self, module: RunModule) -> None:
        module.status = ModuleStatus.RUNNING
        module.started_at = datetime.now(UTC)
        module.message = "실행 준비 중"
        module.failure_analysis = None
        self._emit(domain_events.module_started(self._state.run_id, module.module_id))

    def record_result(
        self,
        module: RunModule,
        *,
        status: ModuleStatus,
        message: str,
        artifacts: list[str],
        current_url: str | None,
        dialog_messages: list[str],
    ) -> None:
        """게이트웨이 실행 결과를 모듈에 반영한다(로그는 별도 스토어 소유라 복사하지 않음)."""
        module.status = status
        module.message = message
        module.artifacts = artifacts
        module.artifact_count = len(artifacts)
        module.current_url = current_url
        module.dialog_messages = list(dialog_messages)

    def note_module_message(self, module: RunModule, message: str) -> None:
        """실행 중 모듈의 최신 메시지(마지막 로그 줄)를 갱신한다.

        로그 스트리밍 핫패스에서 호출된다. 로그 본문은 별도 로그 스토어가 소유하지만 "모듈의
        현재 메시지"는 도메인 상태이므로, 직접 ``module.message = ...`` 하지 않고 이 경로로만
        바꿔 **애그리거트가 유일한 변이자**라는 불변을 지킨다.
        """
        module.message = message

    def append_module_log(self, module: RunModule, message: str) -> None:
        """로그 한 줄을 기록하고 ``ModuleLogAppended`` 이벤트를 산출한다."""
        module.message = message
        self._emit(
            domain_events.module_log_appended(
                self._state.run_id,
                module.module_id,
                message,
            )
        )

    def attach_failure_analysis(self, module: RunModule, analysis) -> None:
        """Run 종료 후 AI 실패 분석 결과를 해당 모듈에 부착한다(구독자 → 도메인 변이 경로)."""
        module.failure_analysis = analysis
        self._emit(
            domain_events.module_failure_analysis_attached(
                self._state.run_id,
                module.module_id,
                category=analysis.category if analysis else None,
                user_summary=analysis.user_summary if analysis else None,
            )
        )

    def attach_comparison(self, comparison) -> None:
        """직전 Run 대비 비교 결과를 부착한다(finalize 시점의 도메인 변이 경로)."""
        self._state.comparison = comparison
        baseline_id = comparison.baseline_run_id if comparison.has_baseline else None
        self._emit(
            domain_events.run_comparison_attached(
                self._state.run_id,
                baseline_id,
                newly_failed=comparison.newly_failed,
                recovered=comparison.recovered,
                still_failing=comparison.still_failing,
            )
        )

    def hydrate_logs(self, logs_by_module: dict[str, list[str]]) -> None:
        """로그 스토어의 로그를 각 모듈에 채워 읽기 모델을 조립한다.

        로그 본문은 별도 로그 스토어(집합체)가 소유하지만, 읽기 시 모듈에 채워 넣는 것도
        엔티티 필드 변이이므로 이 경로로만 수행한다(애그리거트 = 유일한 변이자).
        """
        for module in self._state.modules:
            module.logs = logs_by_module.get(module.module_id, [])

    def finish_timing(self, module: RunModule) -> None:
        """모듈 종료 시각·소요시간 확정(정상 종료 경로)."""
        module.ended_at = datetime.now(UTC)
        module.duration_ms = self._duration_ms(module)
        self._emit_module_completed(module)

    def record_retry(self, module: RunModule) -> None:
        """정책상 재시도 — attempt 를 올리고 모듈을 다시 큐잉한다."""
        module.attempt += 1
        module.retry_count += 1
        module.status = ModuleStatus.QUEUED
        module.message = f"재시도 {module.attempt}/{module.max_attempts}"
        module.started_at = None
        module.ended_at = None
        module.duration_ms = None
        module.failure_analysis = None
        self._emit(
            domain_events.run_module_retried(
                self._state.run_id,
                module.module_id,
                module.attempt,
            )
        )

    def prepare_partial_rerun(self, from_index: int, ordered_modules: list[RunModule]) -> None:
        """지정 인덱스부터 모듈 상태를 초기화하고 Run 을 재개한다."""
        self._state.status = RunStatus.RUNNING
        self._state.ended_at = None
        self._state.awaiting_input_module_id = None
        self._state.awaiting_input_prompt = None
        from_module_id = ordered_modules[from_index].module_id
        for module in ordered_modules[from_index:]:
            if module.status is ModuleStatus.SKIPPED:
                continue
            module.status = ModuleStatus.PENDING
            module.attempt = 1
            module.message = "부분 재실행 대기"
            module.started_at = None
            module.ended_at = None
            module.duration_ms = None
            module.artifacts = []
            module.artifact_count = 0
            module.failure_analysis = None
        self._emit(
            domain_events.run_partial_rerun_started(
                self._state.run_id,
                from_module_id,
            )
        )

    def fail_module(self, module: RunModule, message: str) -> None:
        """단계 진입 전/도중 e2eTester(플랫폼) 오류로 모듈을 종료한다."""
        module.status = ModuleStatus.ERROR
        module.message = message
        module.ended_at = datetime.now(UTC)
        module.duration_ms = self._duration_ms(module)
        self._emit_module_completed(module)

    def mark_fatal(self, module: RunModule, message: str) -> None:
        """예상치 못한 실행 오류를 특정 모듈에 귀속해 ERROR 처리한다."""
        if module.started_at is None:
            module.started_at = datetime.now(UTC)
        module.status = ModuleStatus.ERROR
        module.message = message
        module.ended_at = datetime.now(UTC)
        module.duration_ms = self._duration_ms(module)
        self._emit_module_completed(module)

    def mark_waiting_input(self, module: RunModule, message: str, artifacts: list[str]) -> None:
        """OTP 등 사용자 입력 대기로 Run 을 일시정지한다(모듈 종료가 아님)."""
        module.status = ModuleStatus.WAITING_INPUT
        module.message = f"{message}. 웹 화면에서 OTP를 입력해 제출하세요."
        module.artifacts = artifacts
        module.artifact_count = len(artifacts)
        module.failure_analysis = None
        self._state.status = RunStatus.WAITING_INPUT
        self._state.awaiting_input_module_id = module.module_id
        self._state.awaiting_input_prompt = "휴대폰으로 받은 OTP를 입력하세요."
        self._emit(domain_events.run_waiting_input(self._state.run_id, module.module_id))

    def resume_after_input(self, module: RunModule) -> None:
        """입력(OTP)이 접수되어 재개 대기 상태로 되돌린다."""
        self._state.status = RunStatus.RUNNING
        self._state.awaiting_input_module_id = None
        self._state.awaiting_input_prompt = None
        module.status = ModuleStatus.QUEUED
        module.message = "OTP 입력이 접수되어 재개 대기 중"
        self._emit(domain_events.run_resumed(self._state.run_id, module.module_id))

    def cancel_modules(self, modules: list[RunModule]) -> list[RunModule]:
        """아직 끝나지 않은 모듈들을 사용자 취소로 종료한다. 실제 전이된 모듈만 반환."""
        changed: list[RunModule] = []
        for module in modules:
            if module.status in _MODULE_TERMINAL:
                continue
            if module.started_at is not None and module.ended_at is None:
                module.ended_at = datetime.now(UTC)
                module.duration_ms = self._duration_ms(module)
            module.status = ModuleStatus.CANCELLED
            module.message = "사용자 요청으로 취소됨"
            changed.append(module)
        if changed:
            self._emit(
                domain_events.run_modules_cancelled(
                    self._state.run_id,
                    [module.module_id for module in changed],
                )
            )
        return changed

    def finalize(self, forced_status: RunStatus | None) -> RunStatus:
        """Run 을 종료 상태로 봉인한다(비교 계산·영속·이벤트는 호출자 책임). 결과 상태 반환."""
        self._state.ended_at = datetime.now(UTC)
        self._state.awaiting_input_module_id = None
        self._state.awaiting_input_prompt = None
        self._state.status = self.compute_final_status(forced_status)
        self._emit_run_finished()
        return self._state.status

    def seal_interrupted(self) -> bool:
        """재기동으로 이어받을 수 없는 진행 중 Run 을 CANCELLED 로 봉인한다.

        실제로 봉인했으면 True. 이미 종료 상태면 아무것도 하지 않고 False.
        """
        if self._state.status not in _RUN_ACTIVE:
            return False
        self._state.status = RunStatus.CANCELLED
        self._state.ended_at = self._state.ended_at or datetime.now(UTC)
        self._state.awaiting_input_module_id = None
        self._state.awaiting_input_prompt = None
        for module in self._state.modules:
            if module.status in _MODULE_ACTIVE:
                module.status = ModuleStatus.CANCELLED
                module.message = "서버 재시작으로 중단됨"
        self._emit(domain_events.run_sealed_interrupted(self._state.run_id))
        self._emit_run_finished()
        return True

    # --- 내부 -------------------------------------------------------------

    def _emit_module_completed(self, module: RunModule) -> None:
        self._emit(
            domain_events.module_finished(
                self._state.run_id,
                module.module_id,
                module.status,
                system_code=self._state.system_code,
                schedule_id=self._state.schedule_id,
                suite_id=self._state.suite_id,
                module_name=module.name,
                message=module.message,
                started_at=module.started_at,
                ended_at=module.ended_at,
                duration_ms=module.duration_ms,
                created_by_user_id=self._state.created_by_user_id,
                current_url=module.current_url,
                artifacts=module.artifacts,
            )
        )

    def _emit_run_finished(self) -> None:
        self._emit(
            domain_events.run_finished(
                self._state.run_id,
                self._state.status,
                system_code=self._state.system_code,
                schedule_id=self._state.schedule_id,
                suite_id=self._state.suite_id,
                requested_at=self._state.requested_at,
                ended_at=self._state.ended_at,
                created_by_user_id=self._state.created_by_user_id,
            )
        )

    @staticmethod
    def _duration_ms(module: RunModule) -> int | None:
        if module.started_at is None or module.ended_at is None:
            return None
        return int((module.ended_at - module.started_at).total_seconds() * 1000)
