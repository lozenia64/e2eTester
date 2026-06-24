from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run, RunModule
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES

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
        self.run = run
        self._modules_by_id = {module.module_id: module for module in run.modules}

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
        return any(module.status in MODULE_ERROR_STATUSES for module in self.run.modules)

    def has_module_anomaly(self) -> bool:
        return any(module.status in MODULE_ANOMALY_STATUSES for module in self.run.modules)

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
        self.run.status = RunStatus.RUNNING
        self.run.started_at = datetime.now(UTC)

    def block_for_dependencies(self, module: RunModule) -> None:
        module.status = ModuleStatus.BLOCKED
        module.message = "선행 모듈 실패로 인해 실행되지 않음"

    def mark_queued(self, module: RunModule) -> None:
        module.status = ModuleStatus.QUEUED
        module.message = "실행 대기열에 등록됨"
        module.failure_analysis = None

    def mark_running(self, module: RunModule) -> None:
        module.status = ModuleStatus.RUNNING
        module.started_at = datetime.now(UTC)
        module.message = "실행 준비 중"
        module.failure_analysis = None

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

    def finish_timing(self, module: RunModule) -> None:
        """모듈 종료 시각·소요시간 확정(정상 종료 경로)."""
        module.ended_at = datetime.now(UTC)
        module.duration_ms = self._duration_ms(module)

    def fail_module(self, module: RunModule, message: str) -> None:
        """단계 진입 전/도중 e2eTester(플랫폼) 오류로 모듈을 종료한다."""
        module.status = ModuleStatus.ERROR
        module.message = message
        module.ended_at = datetime.now(UTC)
        module.duration_ms = self._duration_ms(module)

    def mark_fatal(self, module: RunModule, message: str) -> None:
        """예상치 못한 실행 오류를 특정 모듈에 귀속해 ERROR 처리한다."""
        if module.started_at is None:
            module.started_at = datetime.now(UTC)
        module.status = ModuleStatus.ERROR
        module.message = message
        module.ended_at = datetime.now(UTC)
        module.duration_ms = self._duration_ms(module)

    def mark_waiting_input(self, module: RunModule, message: str, artifacts: list[str]) -> None:
        """OTP 등 사용자 입력 대기로 Run 을 일시정지한다(모듈 종료가 아님)."""
        module.status = ModuleStatus.WAITING_INPUT
        module.message = f"{message}. 웹 화면에서 OTP를 입력해 제출하세요."
        module.artifacts = artifacts
        module.artifact_count = len(artifacts)
        module.failure_analysis = None
        self.run.status = RunStatus.WAITING_INPUT
        self.run.awaiting_input_module_id = module.module_id
        self.run.awaiting_input_prompt = "휴대폰으로 받은 OTP를 입력하세요."

    def resume_after_input(self, module: RunModule) -> None:
        """입력(OTP)이 접수되어 재개 대기 상태로 되돌린다."""
        self.run.status = RunStatus.RUNNING
        self.run.awaiting_input_module_id = None
        self.run.awaiting_input_prompt = None
        module.status = ModuleStatus.QUEUED
        module.message = "OTP 입력이 접수되어 재개 대기 중"

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
        return changed

    def finalize(self, forced_status: RunStatus | None) -> RunStatus:
        """Run 을 종료 상태로 봉인한다(비교 계산·영속·이벤트는 호출자 책임). 결과 상태 반환."""
        self.run.ended_at = datetime.now(UTC)
        self.run.awaiting_input_module_id = None
        self.run.awaiting_input_prompt = None
        self.run.status = self.compute_final_status(forced_status)
        return self.run.status

    def seal_interrupted(self) -> bool:
        """재기동으로 이어받을 수 없는 진행 중 Run 을 CANCELLED 로 봉인한다.

        실제로 봉인했으면 True. 이미 종료 상태면 아무것도 하지 않고 False.
        """
        if self.run.status not in _RUN_ACTIVE:
            return False
        self.run.status = RunStatus.CANCELLED
        self.run.ended_at = self.run.ended_at or datetime.now(UTC)
        self.run.awaiting_input_module_id = None
        self.run.awaiting_input_prompt = None
        for module in self.run.modules:
            if module.status in _MODULE_ACTIVE:
                module.status = ModuleStatus.CANCELLED
                module.message = "서버 재시작으로 중단됨"
        return True

    # --- 내부 -------------------------------------------------------------

    @staticmethod
    def _duration_ms(module: RunModule) -> int | None:
        if module.started_at is None or module.ended_at is None:
            return None
        return int((module.ended_at - module.started_at).total_seconds() * 1000)
