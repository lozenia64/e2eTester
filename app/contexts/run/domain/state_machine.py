"""Run 실행 루프의 **결정 규칙(명시적 전이표)** 을 소유하는 순수 도메인 컴포넌트.

과거에는 "다음에 무엇을 할지"라는 결정이 ``RunService._execute_run_inner`` 의 긴 절차적
for 루프 안에 if/return 분기로 흩어져 있었다(취소 관측·선행 차단·OTP 일시정지·결과 기록이
I/O 와 뒤섞여, 상태머신이 코드 형태로만 존재했다). 이 모듈은 그 **결정(decision)** 을
**효과(effect)** 와 분리해, ``(상태·신호) → 명령`` 으로 매핑하는 명시적 표로 끌어낸다.

- 결정(이 파일): 순수 함수. ``await`` 없음, 저장소/게이트웨이/이벤트 import 없음 → 브라우저·DB
  없이 단독 단위 테스트(``tests/test_run_state_machine.py``).
- 효과(``RunService``): 결정을 받아 ``save_run``·WS 이벤트·게이트웨이 호출 같은 I/O 만 수행한다.

전이표(요약):

  모듈 진입(decide_module_entry):
    cancel_requested                      → CancelRemaining
    not dependencies_satisfied            → BlockModule
    그 외                                  → ExecuteModule

  단계 종료 후(decide_post_step):
    status == WAITING_INPUT 이고
        not module_requires_user_input    → RejectUnexpectedInput  (정책 위반)
        cancel_requested                  → CancelRemaining
        그 외                              → PauseForInput
    그 외(정상/실패 종료)                   → CompleteStep

  단계 실패 후(decide_post_step_failure):
    cancel_requested                      → CancelRemaining
    SITE 신호 또는 ANOMALY 상태           → CompleteStep (사이트 이상 — 매니페스트 무관 비재시도)
    retryable 이고 attempt < max_attempts → RetryModule
    그 외                                  → CompleteStep

  부분 재실행(decide_partial_rerun):
    invalid module / not allowed          → RejectInvalidResumePoint
    그 외                                  → ResumeFromModule

  Run 수준 자동 재실행(decide_auto_rerun):
    run_status != ERROR                   → SkipAutoRerun (ANOMALY 는 사이트 이상 — 절대 재실행 안 함)
    triggered_by != "schedule"            → SkipAutoRerun (수동 실행은 판단을 뺏지 않음)
    is_auto_rerun                         → SkipAutoRerun (자동 재실행의 연쇄 차단)
    budget_remaining <= 0                 → SkipAutoRerun
    그 외                                  → TriggerAutoRerun
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import FailureSignal, ModuleStatus, RecoveryTier, RunStatus

# --- 모듈 진입 결정 ----------------------------------------------------------


@dataclass(frozen=True)
class CancelRemaining:
    """취소 의도가 관측됨 → 남은 모듈을 CANCELLED 로 봉인하고 Run 을 종료한다."""


@dataclass(frozen=True)
class BlockModule:
    """선행 모듈이 PASSED 가 아님 → 이 모듈을 BLOCKED 처리하고 다음으로 넘어간다."""


@dataclass(frozen=True)
class ExecuteModule:
    """정상 진행 → 큐잉·실행 단계로 들어간다."""


ModuleEntryDecision = CancelRemaining | BlockModule | ExecuteModule


# --- 단계 종료 후 결정 -------------------------------------------------------


@dataclass(frozen=True)
class PauseForInput:
    """단계가 사람 입력을 요구하고 정책상 허용됨 → Run 을 WAITING_INPUT 으로 일시정지한다."""


@dataclass(frozen=True)
class CompleteStep:
    """단계 결과(정상/실패)를 모듈에 기록하고 종료한다."""


@dataclass(frozen=True)
class RejectUnexpectedInput:
    """입력을 선언하지 않은(``requires_user_input=False``) 모듈이 입력을 요구함.

    매니페스트가 일시정지를 허가하지 않았으므로 도메인 정책 위반이다 → ERROR 로 종료한다
    (과거에는 무한 일시정지로 빠질 수 있었다).
    """


PostStepDecision = CancelRemaining | PauseForInput | CompleteStep | RejectUnexpectedInput


# --- 단계 실패 후 결정(재시도 정책) ------------------------------------------


@dataclass(frozen=True)
class RetryModule:
    """정책상 재시도 가능 → 백오프 후 같은 모듈을 다시 실행한다.

    ``tier`` 는 재시도 **전에** 세션을 어디까지 되감을지를 지시한다. 되감기 실행은
    인터프리터(``RunService``)가 ``ExecutionGateway.recover_session`` 으로 위임한다.
    """

    backoff_ms: int
    tier: RecoveryTier = RecoveryTier.RETRY_IN_PLACE


PostStepFailureDecision = CancelRemaining | PauseForInput | CompleteStep | RetryModule

# 신호 → 기본 복구 등급(설계 §3.2). SITE 는 복구 대상이 아니므로 표에 없다.
_SIGNAL_BASE_TIER: dict[FailureSignal, RecoveryTier] = {
    FailureSignal.TIMEOUT: RecoveryTier.RETRY_IN_PLACE,
    FailureSignal.SELECTOR_MISS: RecoveryTier.RETRY_IN_PLACE,
    FailureSignal.UNKNOWN: RecoveryTier.RETRY_IN_PLACE,
    FailureSignal.DIALOG: RecoveryTier.RESET_TO_MODULE_ENTRY,
    FailureSignal.NAVIGATION: RecoveryTier.RESET_TO_MODULE_ENTRY,
    FailureSignal.SESSION_LOST: RecoveryTier.REPLAY_FROM_LOGIN,
}


def _escalated_tier(
    failure_signal: FailureSignal, attempted_tiers: tuple[RecoveryTier, ...]
) -> RecoveryTier:
    """같은 등급으로 이미 실패했으면 한 단계 올린다(최대 REPLAY_FROM_LOGIN).

    반복되는 타임아웃은 대개 페이지가 이미 잘못된 상태라는 뜻이므로, 같은 되감기를
    반복하는 대신 되감기 범위를 넓힌다.
    """
    tier = _SIGNAL_BASE_TIER.get(failure_signal, RecoveryTier.RETRY_IN_PLACE)
    while tier in attempted_tiers and tier < RecoveryTier.REPLAY_FROM_LOGIN:
        tier = RecoveryTier(tier + 1)
    return tier


# --- 부분 재실행 결정 --------------------------------------------------------


@dataclass(frozen=True)
class ResumeFromModule:
    """지정 모듈부터 Run 을 재개한다."""

    from_index: int


@dataclass(frozen=True)
class RejectInvalidResumePoint:
    """부분 재실행이 허용되지 않거나 모듈이 유효하지 않다."""


PartialRerunDecision = ResumeFromModule | RejectInvalidResumePoint


# --- 세션 재수화 결정(Phase C — 체크포인트 재개) ----------------------------


@dataclass(frozen=True)
class ResumeFromCheckpoint:
    """저장된 세션 상태(storage_state)가 유효 → 체크포인트 다음 모듈부터 재개한다."""

    from_index: int


@dataclass(frozen=True)
class ReplayFromLogin:
    """세션 상태가 무효(로그인 만료 등) → 인증 체인을 다시 태우기 위해 로그인 모듈부터 재실행한다."""

    from_index: int


RehydrationDecision = ResumeFromCheckpoint | ReplayFromLogin


# --- Run 수준 자동 재실행 결정 -----------------------------------------------


@dataclass(frozen=True)
class TriggerAutoRerun:
    """도구 오류로 끝난 예약 Run 을 1회 자동 재실행한다."""


@dataclass(frozen=True)
class SkipAutoRerun:
    """자동 재실행 조건에 해당하지 않는다."""


AutoRerunDecision = TriggerAutoRerun | SkipAutoRerun


class RunStateMachine:
    """Run 실행의 결정 규칙(전이표). 상태(불리언/상태값)만 받아 명령을 돌려주는 순수 함수 모음.

    상태 *변경* 은 ``RunAggregate`` 가, 결정의 *실행*(I/O) 은 ``RunService`` 가 책임진다. 이
    컴포넌트는 오직 "무엇을 할지"만 결정한다.
    """

    @staticmethod
    def decide_module_entry(
        *, cancel_requested: bool, dependencies_satisfied: bool
    ) -> ModuleEntryDecision:
        if cancel_requested:
            return CancelRemaining()
        if not dependencies_satisfied:
            return BlockModule()
        return ExecuteModule()

    @staticmethod
    def decide_post_step(
        *,
        step_status: ModuleStatus,
        cancel_requested: bool,
        module_requires_user_input: bool,
    ) -> PostStepDecision:
        if step_status is ModuleStatus.WAITING_INPUT:
            if not module_requires_user_input:
                return RejectUnexpectedInput()
            if cancel_requested:
                return CancelRemaining()
            return PauseForInput()
        return CompleteStep()

    @staticmethod
    def decide_post_step_failure(
        *,
        step_status: ModuleStatus,
        cancel_requested: bool,
        current_attempt: int,
        max_attempts: int,
        retryable_on: frozenset[ModuleStatus],
        backoff_ms: int,
        failure_signal: FailureSignal = FailureSignal.UNKNOWN,
        attempted_tiers: tuple[RecoveryTier, ...] = (),
        tier2_used: int = 0,
        tier2_budget: int = 2,
    ) -> PostStepFailureDecision:
        if cancel_requested:
            return CancelRemaining()
        if step_status is ModuleStatus.WAITING_INPUT:
            return CompleteStep()
        if step_status is ModuleStatus.PASSED:
            return CompleteStep()
        # 설계 §3.5 안전 규칙(NFR-001) — 사이트 이상은 매니페스트의 retryable_on 설정과
        # **무관하게** 자동 재시도하지 않는다. 사이트 이상을 재시도로 덮으면 이 도구의 존재
        # 이유가 무너진다.
        #
        # 신호(SITE)와 상태(ANOMALY) 둘 다로 막는다: 실행 평면의 두 판정 기준이 미세하게
        # 다르기 때문이다. ``workflow_engine`` 은 ``except RuntimeError`` 로 ANOMALY 를
        # 가르므로 하위 클래스(예: ``NotImplementedError``)도 ANOMALY 가 되지만,
        # ``classify_failure`` 는 ``type(exc) is RuntimeError`` 라는 정확 타입 검사라 그때는
        # ``SITE`` 가 아닌 ``UNKNOWN`` 이 나온다. 신호만 보면 그 틈으로 사이트 이상이 tier 0
        # 재시도에 걸린다. ``ANOMALY`` 는 이 시스템이 사이트 이상에 붙이는 상태 그 자체이므로
        # (``app/core/status_labels.py``) 상태로도 함께 막아야 불변이 실제로 성립한다.
        if failure_signal is FailureSignal.SITE or step_status is ModuleStatus.ANOMALY:
            return CompleteStep()
        if step_status in retryable_on and current_attempt < max_attempts:
            tier = _escalated_tier(failure_signal, attempted_tiers)
            # 로그인 재주행은 비싸므로 Run 당 예산을 넘기면 한 단계 낮춘다(설계 §3.6).
            if tier is RecoveryTier.REPLAY_FROM_LOGIN and tier2_used >= tier2_budget:
                tier = RecoveryTier.RESET_TO_MODULE_ENTRY
            return RetryModule(backoff_ms=backoff_ms, tier=tier)
        return CompleteStep()

    @staticmethod
    def decide_partial_rerun(
        *,
        from_module_id: str,
        module_ids_in_order: list[str],
        partial_rerun_allowed: bool,
    ) -> PartialRerunDecision:
        if from_module_id not in module_ids_in_order:
            return RejectInvalidResumePoint()
        if not partial_rerun_allowed:
            return RejectInvalidResumePoint()
        return ResumeFromModule(from_index=module_ids_in_order.index(from_module_id))

    @staticmethod
    def decide_rehydration(
        *,
        checkpoint_module_index: int,
        storage_state_valid: bool,
        login_module_index: int | None,
    ) -> RehydrationDecision:
        """워커가 세션 체크포인트로 Run 을 이어받을 때 어디서 재개할지 결정한다(순수 규칙).

        - 저장된 세션 상태가 유효하면 마지막 완료 모듈 **다음**부터 재개(``ResumeFromCheckpoint``).
        - 무효(로그인 만료 등)면 인증 세션을 다시 세우기 위해 로그인(인증) 모듈부터 재실행
          (``ReplayFromLogin``). 로그인 모듈 정보가 없으면 처음(0)부터 재실행한다.

        Phase C: ``WAITING_INPUT`` 은 라이브 브라우저가 아니라 내구성 시그널이므로, 재개 워커는
        체크포인트에서 상태를 복원하되 복원 상태가 무효면 로그인부터 재진입할 수 있어야 한다.
        """
        if storage_state_valid:
            return ResumeFromCheckpoint(from_index=checkpoint_module_index + 1)
        return ReplayFromLogin(
            from_index=login_module_index if login_module_index is not None else 0
        )

    @staticmethod
    def decide_auto_rerun(
        *,
        run_status: RunStatus,
        triggered_by: str,
        is_auto_rerun: bool,
        budget_remaining: int,
    ) -> AutoRerunDecision:
        """Run 종료 후 자동 재실행 여부(설계 §3.6).

        ``ANOMALY`` 는 사이트 이상이므로 **절대** 자동 재실행하지 않는다. 수동 실행은
        사람이 보고 있으므로 판단을 뺏지 않는다. 자동 재실행이 다시 자동 재실행을
        낳는 연쇄도 차단한다.
        """
        if run_status is not RunStatus.ERROR:
            return SkipAutoRerun()
        if triggered_by != "schedule":
            return SkipAutoRerun()
        if is_auto_rerun:
            return SkipAutoRerun()
        if budget_remaining <= 0:
            return SkipAutoRerun()
        return TriggerAutoRerun()
