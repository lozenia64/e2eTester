# 자동 복구 루프 (Self-Recovery Loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모듈 실패 시 브라우저 세션을 적절한 지점까지 되감은 뒤 재시도해, 도구 오류(`ERROR`)로 인한 사람의 재실행 루프를 제거한다.

**Architecture:** 실패 원인을 `FailureSignal` enum 으로 runner 경계에서 분류하고, 순수 결정 함수 `decide_post_step_failure` 가 신호와 이전 시도 이력으로부터 `RecoveryTier`(0/1/2)를 정한다. tier 실행(세션 되감기)은 `ExecutionGateway.recover_session` 포트 뒤로 숨긴다. 복구 사실은 `RunModuleRecovered` 이벤트와 `recovered` 필드로 항상 가시화한다.

**Tech Stack:** Python 3.13, FastAPI, Playwright, pytest (`asyncio_mode="auto"`), pydantic v2, ruff, pyright, import-linter

**Spec:** `docs/superpowers/specs/2026-08-17-self-recovery-loop-design.md`

## Global Constraints

- **UI·로그·README 문자열은 한국어** (`AGENTS.md`)
- **`ANOMALY`(`FailureSignal.SITE`)는 어떤 경우에도 자동 재시도하지 않는다** — 설계 §3.5. `retryable_on` 설정보다 도메인 규칙이 우선한다.
- **도메인(`app/contexts/run/domain/`)은 Playwright 를 import 하지 않는다** — import-linter 계약. 예외 타입 검사는 `app/runner/` 안에만 존재한다.
- **모든 신규 이벤트·레코드 필드는 기본값을 갖는다** — 기존 `domain_events` 스트림 재생 하위호환 필수.
- **tier 0 의 동작은 현행과 완전히 동일해야 한다** — 기존 재시도 테스트가 무수정으로 통과해야 한다.
- **`app/automation/` 밖에서 automation 코드를 수정하지 않는다** (`AGENTS.md`)
- 검증 명령: `python3 -m pytest <path> -v`, 최종 `python3 scripts/ci/run_all_gates.py --profile full`
- 커밋 메시지는 한국어 본문, 말미에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

---

## File Structure

| 파일 | 책임 | 상태 |
| --- | --- | --- |
| `app/core/enums.py` | `FailureSignal`, `RecoveryTier` 정의 (도메인·runner 공용 어휘) | 수정 |
| `app/runner/failure_signal.py` | 예외 객체 → `FailureSignal` 분류 (Playwright 의존을 여기에 가둠) | **신규** |
| `app/runner/workflow_engine.py` | except 절에서 분류 호출, 모듈 진입 URL 캡처 | 수정 |
| `app/execution/results.py` | `StepExecutionResult.failure_signal` 운반 | 수정 |
| `app/execution/protocol.py` | 워커 HTTP 응답에 `failure_signal` 운반 | 수정 |
| `app/execution/gateway.py` | `recover_session` 포트 (기본 no-op) | 수정 |
| `app/execution/simulated_gateway.py` | 테스트용 tier 실행 기록 | 수정 |
| `app/execution/worker_gateway.py` | `recover_session` HTTP 호출 | 수정 |
| `worker/session_server.py` | tier 1/2 실제 세션 되감기 | 수정 |
| `worker/http_server.py` | `/recover` 엔드포인트 | 수정 |
| `app/contexts/run/domain/state_machine.py` | `RetryModule.tier`, 신호→tier 매핑, SITE 하드 차단, 등급 상승 | 수정 |
| `app/contexts/run/domain/events.py` | `RunModuleRecovered` | 수정 |
| `app/contexts/run/domain/aggregate.py` | 복구 이력 기록 | 수정 |
| `app/core/run_models.py` | `RunModule.recovered` 외 3필드 | 수정 |
| `app/contexts/run/contracts/records.py` | `RunModuleRecord` 동일 필드 | 수정 |
| `app/contexts/run/infrastructure/codec.py` | 신규 이벤트 인코딩 | 수정 |
| `app/contexts/run/application/service.py` | 인터프리터 — tier 실행 배선, 자동 재실행 게이트 | 수정 |
| `app/core/settings.py` | 자동 재실행·예산 설정 | 수정 |
| `docs/specs/run/06-self-recovery-loop.md` | 행동 명세 `SPEC-RUN-006` | **신규** |

---

## Task 1: 실패 신호 분류 (`FailureSignal`)

**Files:**
- Modify: `app/core/enums.py`
- Create: `app/runner/failure_signal.py`
- Test: `tests/test_failure_signal.py`

**Interfaces:**
- Consumes: 없음 (최초 태스크)
- Produces:
  - `app.core.enums.FailureSignal` — `StrEnum`, 멤버 `TIMEOUT`/`SELECTOR_MISS`/`NAVIGATION`/`SESSION_LOST`/`DIALOG`/`SITE`/`UNKNOWN`
  - `app.runner.failure_signal.classify_failure(exc: BaseException) -> FailureSignal`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_failure_signal.py` 를 새로 만든다.

```python
"""예외 객체 → FailureSignal 분류(순수 함수) 단위 테스트."""

from __future__ import annotations

import pytest

from app.core.enums import FailureSignal
from app.runner.failure_signal import classify_failure


def test_runtime_error_is_site_signal():
    """RuntimeError 는 page object 가 의도적으로 던지는 사이트 이상 신호다."""
    assert classify_failure(RuntimeError("계약목록을 찾지 못했습니다.")) is FailureSignal.SITE


def test_timeout_error_is_timeout_signal():
    class TimeoutError_(Exception):
        pass

    TimeoutError_.__name__ = "TimeoutError"
    assert classify_failure(TimeoutError_("Timeout 30000ms exceeded")) is FailureSignal.TIMEOUT


def test_target_closed_is_session_lost():
    class TargetClosedError(Exception):
        pass

    assert classify_failure(TargetClosedError("Target page closed")) is FailureSignal.SESSION_LOST


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('waiting for selector "#btn" failed', FailureSignal.SELECTOR_MISS),
        ("net::ERR_CONNECTION_RESET at https://example.com", FailureSignal.NAVIGATION),
        ('navigation to "https://x" is interrupted', FailureSignal.NAVIGATION),
        ("Browser has been closed", FailureSignal.SESSION_LOST),
    ],
)
def test_message_based_classification(message: str, expected: FailureSignal):
    assert classify_failure(Exception(message)) is expected


def test_unrecognised_exception_is_unknown():
    assert classify_failure(ValueError("무언가 잘못됨")) is FailureSignal.UNKNOWN


def test_classification_never_raises():
    """분류 실패가 점검 자체를 망가뜨려서는 안 된다."""

    class Nasty(Exception):
        def __str__(self) -> str:
            raise ValueError("str() 폭발")

    assert classify_failure(Nasty()) is FailureSignal.UNKNOWN
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_failure_signal.py -v`
Expected: FAIL — `ImportError: cannot import name 'FailureSignal' from 'app.core.enums'`

- [ ] **Step 3: `FailureSignal` enum 추가**

`app/core/enums.py` 파일 끝에 추가한다.

```python
class FailureSignal(StrEnum):
    """모듈 실패의 성격. 복구 등급(RecoveryTier) 선택의 유일한 입력이다.

    분류는 실행 평면(``app/runner/failure_signal.py``)에서만 수행하고, 도메인은 이 enum 만
    관찰한다. 도메인이 예외 메시지 문자열을 들여다보는 일(``StepOutcome`` 도입으로 걷어낸
    안티패턴)이 재발하지 않도록 하는 경계다.
    """

    TIMEOUT = "TIMEOUT"  # 대기 시간 초과
    SELECTOR_MISS = "SELECTOR_MISS"  # 요소를 찾지 못함
    NAVIGATION = "NAVIGATION"  # 페이지 이동·로드 실패
    SESSION_LOST = "SESSION_LOST"  # 세션·컨텍스트 소실, 로그인 만료
    DIALOG = "DIALOG"  # 예기치 않은 다이얼로그·팝업
    SITE = "SITE"  # 사이트 이상(page object 의 의도적 RuntimeError) — 자동 복구 대상 아님
    UNKNOWN = "UNKNOWN"  # 미분류
```

- [ ] **Step 4: `classify_failure` 구현**

`app/runner/failure_signal.py` 를 새로 만든다.

```python
"""예외 객체 → ``FailureSignal`` 분류(실행 평면 전용).

Playwright 예외의 세부 판별에는 타입명·메시지 검사가 일부 불가피하다. 그 검사를 **이 모듈
안에만 가두는 것**이 이 파일의 존재 이유다. 도메인(``app/contexts/run/domain/``)은 결과
enum 만 보고, 문자열을 절대 보지 않는다.
"""

from __future__ import annotations

from app.core.enums import FailureSignal

# 예외 클래스 이름 → 신호. Playwright 를 import 하지 않고 이름으로 판별해,
# 이 모듈이 Playwright 설치 여부와 무관하게 동작하게 한다(API 프로세스에는 Playwright 가 없다).
_TYPE_NAME_SIGNALS: dict[str, FailureSignal] = {
    "TimeoutError": FailureSignal.TIMEOUT,
    "TargetClosedError": FailureSignal.SESSION_LOST,
}

# 메시지 부분 문자열 → 신호. 위에서부터 먼저 일치하는 것을 쓴다(순서가 의미를 가진다).
_MESSAGE_SIGNALS: tuple[tuple[str, FailureSignal], ...] = (
    ("net::", FailureSignal.NAVIGATION),
    ("navigation", FailureSignal.NAVIGATION),
    ("err_", FailureSignal.NAVIGATION),
    ("target page, context or browser has been closed", FailureSignal.SESSION_LOST),
    ("browser has been closed", FailureSignal.SESSION_LOST),
    ("execution context was destroyed", FailureSignal.SESSION_LOST),
    ("waiting for selector", FailureSignal.SELECTOR_MISS),
    ("waiting for locator", FailureSignal.SELECTOR_MISS),
    ("resolved to 0 elements", FailureSignal.SELECTOR_MISS),
    ("no node found for selector", FailureSignal.SELECTOR_MISS),
    ("timeout", FailureSignal.TIMEOUT),
    ("dialog", FailureSignal.DIALOG),
)


def classify_failure(exc: BaseException) -> FailureSignal:
    """예외를 복구 등급 결정에 쓸 신호로 분류한다. **절대 예외를 던지지 않는다.**"""
    # RuntimeError 는 page object 가 "사이트가 이상하다"를 알리려고 던지는 신호다
    # (workflow_engine 이 이미 ANOMALY 로 가르는 기준과 동일하게 유지한다).
    if type(exc) is RuntimeError:
        return FailureSignal.SITE

    signal = _TYPE_NAME_SIGNALS.get(type(exc).__name__)
    if signal is not None:
        return signal

    try:
        message = str(exc).lower()
    except Exception:  # 분류 실패가 점검 결과를 더 망치지 않게 격리한다.
        return FailureSignal.UNKNOWN

    for needle, mapped in _MESSAGE_SIGNALS:
        if needle in message:
            return mapped
    return FailureSignal.UNKNOWN
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_failure_signal.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 린트·포맷**

Run: `python3 -m ruff format app/core/enums.py app/runner/failure_signal.py tests/test_failure_signal.py && python3 -m ruff check app/core/enums.py app/runner/failure_signal.py tests/test_failure_signal.py`
Expected: 통과

- [ ] **Step 7: 커밋**

```bash
git add app/core/enums.py app/runner/failure_signal.py tests/test_failure_signal.py
git commit -m "feat(run): 실패 신호 분류(FailureSignal) 추가

예외 객체를 복구 등급 결정용 신호로 분류한다. Playwright 예외의 타입명·메시지
검사는 app/runner/ 안에만 가두고 도메인은 enum 만 관찰한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: 복구 등급 결정 (순수 도메인)

이 태스크가 끝나도 **런타임 동작은 변하지 않는다.** 호출부가 아직 실제 신호를 넘기지 않으므로 모든 결정이 기본값(`UNKNOWN` → tier 0 = 현행)으로 떨어진다.

**Files:**
- Modify: `app/core/enums.py`
- Modify: `app/contexts/run/domain/state_machine.py:88-96` (`RetryModule`), `:172-189` (`decide_post_step_failure`)
- Modify: `app/contexts/run/application/service.py:679-687` (호출부 — 컴파일 유지)
- Test: `tests/test_run_state_machine.py`

**Interfaces:**
- Consumes: `app.core.enums.FailureSignal` (Task 1)
- Produces:
  - `app.core.enums.RecoveryTier` — `IntEnum`, `RETRY_IN_PLACE=0` / `RESET_TO_MODULE_ENTRY=1` / `REPLAY_FROM_LOGIN=2`
  - `RetryModule(backoff_ms: int, tier: RecoveryTier)` — `state_machine` 의 결정 타입
  - `RunStateMachine.decide_post_step_failure(..., failure_signal=FailureSignal.UNKNOWN, attempted_tiers=())`

> **이름 충돌 주의:** `app/contexts/run/domain/commands.py:68` 에도 `RetryModule` 이 있다(커맨드, 필드 `module_id`). **이 태스크는 `state_machine.py` 의 결정 타입만 건드린다.** `service.py` 는 `state_machine` 쪽을 import 한다(`service.py:28`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_state_machine.py` 파일 끝에 추가한다.

```python
# --- 복구 등급(RecoveryTier) 결정 --------------------------------------------

from app.core.enums import FailureSignal, RecoveryTier  # noqa: E402


def _failure_decision(**overrides):
    kwargs = {
        "step_status": ModuleStatus.ERROR,
        "cancel_requested": False,
        "current_attempt": 1,
        "max_attempts": 3,
        "retryable_on": frozenset({ModuleStatus.ERROR}),
        "backoff_ms": 500,
    }
    kwargs.update(overrides)
    return RunStateMachine.decide_post_step_failure(**kwargs)


@pytest.mark.parametrize(
    ("signal", "expected_tier"),
    [
        (FailureSignal.TIMEOUT, RecoveryTier.RETRY_IN_PLACE),
        (FailureSignal.SELECTOR_MISS, RecoveryTier.RETRY_IN_PLACE),
        (FailureSignal.UNKNOWN, RecoveryTier.RETRY_IN_PLACE),
        (FailureSignal.DIALOG, RecoveryTier.RESET_TO_MODULE_ENTRY),
        (FailureSignal.NAVIGATION, RecoveryTier.RESET_TO_MODULE_ENTRY),
        (FailureSignal.SESSION_LOST, RecoveryTier.REPLAY_FROM_LOGIN),
    ],
)
def test_signal_maps_to_base_tier(signal, expected_tier):
    decision = _failure_decision(failure_signal=signal)
    assert isinstance(decision, RetryModule)
    assert decision.tier is expected_tier


def test_tier_escalates_when_same_tier_already_attempted():
    """같은 등급으로 이미 실패했으면 한 단계 올린다."""
    decision = _failure_decision(
        failure_signal=FailureSignal.TIMEOUT,
        attempted_tiers=(RecoveryTier.RETRY_IN_PLACE,),
    )
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.RESET_TO_MODULE_ENTRY


def test_tier_escalation_stops_at_replay_from_login():
    decision = _failure_decision(
        failure_signal=FailureSignal.TIMEOUT,
        attempted_tiers=(
            RecoveryTier.RETRY_IN_PLACE,
            RecoveryTier.RESET_TO_MODULE_ENTRY,
            RecoveryTier.REPLAY_FROM_LOGIN,
        ),
    )
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.REPLAY_FROM_LOGIN


def test_site_signal_never_retries_even_when_policy_allows():
    """설계 §3.5 안전 규칙 — 매니페스트가 ANOMALY 재시도를 켜도 도메인이 거부한다."""
    decision = _failure_decision(
        step_status=ModuleStatus.ANOMALY,
        failure_signal=FailureSignal.SITE,
        retryable_on=frozenset({ModuleStatus.ERROR, ModuleStatus.ANOMALY}),
    )
    assert isinstance(decision, CompleteStep)


def test_default_signal_preserves_legacy_tier_zero_behaviour():
    """호출부가 신호를 넘기지 않으면 현행 동작(tier 0)과 동일하다."""
    decision = _failure_decision()
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.RETRY_IN_PLACE
    assert decision.backoff_ms == 500
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_run_state_machine.py -v -k "tier or site_signal or legacy_tier"`
Expected: FAIL — `ImportError: cannot import name 'RecoveryTier'`

- [ ] **Step 3: `RecoveryTier` enum 추가**

`app/core/enums.py` 파일 끝에 추가한다. 상단 import 도 함께 고친다.

```python
from enum import IntEnum, StrEnum
```

```python
class RecoveryTier(IntEnum):
    """모듈 재시도 전에 **세션을 어디까지 되감을지**. 값의 크기가 곧 비용·파괴력이다.

    ``IntEnum`` 인 이유: 등급 상승(escalation)을 산술로 표현하기 위함이다.
    """

    RETRY_IN_PLACE = 0  # 되감기 없음 — backoff 후 같은 페이지에서 재시도(현행 동작)
    RESET_TO_MODULE_ENTRY = 1  # 다이얼로그 정리 후 모듈 진입 URL 로 재이동
    REPLAY_FROM_LOGIN = 2  # 세션 폐기·재개설 후 로그인 모듈부터 주행
```

- [ ] **Step 4: 결정 함수 확장**

`app/contexts/run/domain/state_machine.py` 를 수정한다.

먼저 import 에 추가:

```python
from app.core.enums import FailureSignal, ModuleStatus, RecoveryTier
```

`RetryModule` 결정 타입(`:91-95`)에 `tier` 를 추가한다:

```python
@dataclass(frozen=True)
class RetryModule:
    """정책상 재시도 가능 → 백오프 후 같은 모듈을 다시 실행한다.

    ``tier`` 는 재시도 **전에** 세션을 어디까지 되감을지를 지시한다. 되감기 실행은
    인터프리터(``RunService``)가 ``ExecutionGateway.recover_session`` 으로 위임한다.
    """

    backoff_ms: int
    tier: RecoveryTier = RecoveryTier.RETRY_IN_PLACE
```

`PostStepFailureDecision` 정의 바로 위(모듈 수준)에 매핑 테이블과 헬퍼를 추가한다:

```python
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
```

`decide_post_step_failure` 를 교체한다:

```python
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
    ) -> PostStepFailureDecision:
        if cancel_requested:
            return CancelRemaining()
        if step_status is ModuleStatus.WAITING_INPUT:
            return CompleteStep()
        if step_status is ModuleStatus.PASSED:
            return CompleteStep()
        # 설계 §3.5 안전 규칙 — 사이트 이상은 매니페스트의 retryable_on 설정과 **무관하게**
        # 자동 재시도하지 않는다. 사이트 이상을 재시도로 덮으면 이 도구의 존재 이유가 무너진다.
        if failure_signal is FailureSignal.SITE:
            return CompleteStep()
        if step_status in retryable_on and current_attempt < max_attempts:
            return RetryModule(
                backoff_ms=backoff_ms,
                tier=_escalated_tier(failure_signal, attempted_tiers),
            )
        return CompleteStep()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_run_state_machine.py -v`
Expected: PASS — 신규 테스트 + **기존 테스트 전부** 통과 (기본값 덕분에 회귀 없음)

- [ ] **Step 6: 전체 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — 이 태스크는 런타임 동작을 바꾸지 않으므로 실패가 있으면 안 된다.

- [ ] **Step 7: 커밋**

```bash
git add app/core/enums.py app/contexts/run/domain/state_machine.py tests/test_run_state_machine.py
git commit -m "feat(run): 복구 등급(RecoveryTier) 결정 규칙 추가

decide_post_step_failure 가 실패 신호와 이전 시도 이력으로 되감기 범위를
정한다. 신호를 넘기지 않으면 tier 0 = 현행 동작이라 회귀가 없다.

ANOMALY(SITE) 는 retryable_on 설정과 무관하게 재시도를 거부한다(설계 §3.5).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: 실패 신호 배선 (runner → 게이트웨이 → 도메인)

이 태스크 뒤에는 도메인이 **실제 신호**를 본다. 아직 tier 1/2 실행 수단이 없으므로 인터프리터는 tier 를 로그로만 남긴다(다음 태스크에서 실행).

**Files:**
- Modify: `app/execution/results.py:20-30`
- Modify: `app/execution/protocol.py:41-50` (`RunStepResponse`)
- Modify: `app/runner/workflow_engine.py:194-205`
- Modify: `app/execution/worker_gateway.py` (응답 → `StepExecutionResult` 매핑부)
- Test: `tests/test_step_context.py`, `tests/test_worker_gateway_errors.py`

**Interfaces:**
- Consumes: `classify_failure` (Task 1), `FailureSignal` (Task 1)
- Produces: `StepExecutionResult.failure_signal: FailureSignal` (기본 `UNKNOWN`), `RunStepResponse.failure_signal: FailureSignal`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_failure_signal.py` 끝에 추가한다.

```python
# --- 결과 DTO 운반 -----------------------------------------------------------


def test_step_execution_result_defaults_to_unknown_signal():
    """기존 생성자 호출부가 무수정으로 동작해야 한다(하위호환)."""
    from app.execution.results import StepExecutionResult

    result = StepExecutionResult(
        status="ERROR",
        message="x",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    assert result.failure_signal is FailureSignal.UNKNOWN


def test_step_execution_result_failure_helper_marks_site_signal():
    """StepExecutionResult.failure() 는 ANOMALY 를 만드는 헬퍼이므로 SITE 다."""
    from app.execution.results import StepExecutionResult

    result = StepExecutionResult.failure(
        message="사이트 이상",
        current_url=None,
        dialog_messages=[],
        last_error="boom",
    )
    assert result.failure_signal is FailureSignal.SITE
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_failure_signal.py -v -k "step_execution_result"`
Expected: FAIL — `AttributeError: 'StepExecutionResult' object has no attribute 'failure_signal'`

- [ ] **Step 3: 결과 DTO 에 필드 추가**

`app/execution/results.py` — import 와 필드를 추가한다.

```python
from app.core.enums import FailureSignal, ModuleStatus
```

`StepExecutionResult` 의 `healing_events` 위에 추가:

```python
    # 복구 등급 결정의 유일한 입력(설계 §3.1). 기본값이 있으므로 기존 호출부는 무수정 동작한다.
    failure_signal: FailureSignal = FailureSignal.UNKNOWN
```

`failure` 클래스메서드는 `ANOMALY` 를 만드는 헬퍼이므로 `SITE` 를 함께 채운다:

```python
        return cls(
            status=ModuleStatus.ANOMALY,
            message=message,
            artifacts=[],
            current_url=current_url,
            dialog_messages=dialog_messages,
            last_error=last_error,
            screenshot_path=screenshot_path,
            failure_signal=FailureSignal.SITE,
        )
```

- [ ] **Step 4: 워커 HTTP 프로토콜에 필드 추가**

`app/execution/protocol.py` — import 와 `RunStepResponse` 필드를 추가한다.

```python
from app.core.enums import FailureSignal, ModuleStatus
```

`RunStepResponse` 의 `logs` 위에 추가:

```python
    failure_signal: FailureSignal = FailureSignal.UNKNOWN
```

- [ ] **Step 5: `workflow_engine` 에서 분류**

`app/runner/workflow_engine.py` — import 에 추가:

```python
from app.core.enums import FailureSignal, ModuleStatus
from app.runner.failure_signal import classify_failure
```

`execute_step` 의 지역 변수 초기화(`last_error: str | None = None` 바로 아래)에 추가:

```python
        failure_signal = FailureSignal.UNKNOWN
```

두 except 절을 수정한다:

```python
                    except RuntimeError as exc:
                        status = ModuleStatus.ANOMALY
                        message = str(exc)
                        last_error = str(exc)
                        failure_signal = classify_failure(exc)
                        sink(f"[error] {exc}")
                        capture_page_html_diagnostic_safe(real_page, artifact_dir, sink)
                    except Exception as exc:
                        status = ModuleStatus.ERROR
                        message = str(exc)
                        last_error = str(exc)
                        failure_signal = classify_failure(exc)
                        sink(f"[error] {exc}")
```

마지막 `return StepExecutionResult(...)` 에 인자를 추가한다:

```python
            healing_events=healing_attempts,
            failure_signal=failure_signal,
        )
```

- [ ] **Step 6: 워커 게이트웨이 매핑**

`app/execution/worker_gateway.py` 에서 `RunStepResponse` → `StepExecutionResult` 로 변환하는 지점을 찾는다.

Run: `python3 -m grep -n "StepExecutionResult(" app/execution/worker_gateway.py` (또는 편집기 검색)

해당 생성자 호출에 아래 인자를 추가한다:

```python
failure_signal = (payload.failure_signal,)
```

같은 파일에서 워커 측이 `RunStepResponse` 를 만드는 곳(`worker/http_server.py`)에도 대칭으로 추가한다:

```python
failure_signal = (result.failure_signal,)
```

- [ ] **Step 7: 인터프리터가 신호를 도메인에 전달**

`app/contexts/run/application/service.py:679-687` 의 호출을 수정한다.

```python
                        post = RunStateMachine.decide_post_step_failure(
                            step_status=execution_result.status,
                            cancel_requested=cancel_requested,
                            current_attempt=module.attempt,
                            max_attempts=module.max_attempts,
                            retryable_on=module_policy.retryable_on,
                            backoff_ms=module_policy.retry_backoff_ms,
                            failure_signal=execution_result.failure_signal,
                            attempted_tiers=tuple(attempted_tiers),
                        )
```

같은 `while True:` 루프에 진입하기 **직전**(`while True:` 바로 위)에 지역 변수를 선언한다:

```python
                # 이 모듈에서 이미 시도한 복구 등급(등급 상승 판정 입력).
                attempted_tiers: list[RecoveryTier] = []
```

그리고 `RetryModule` 처리 블록(`service.py:710`)에 기록을 추가한다 — **아직 되감기는 실행하지 않는다.**

```python
                    if isinstance(post, RetryModule):
                        attempted_tiers.append(post.tier)
                        aggregate.record_retry(module)
                        await self._persist(run, aggregate)
                        await asyncio.sleep(post.backoff_ms / 1000)
                        await self._transition_to_running(run, module)
                        continue
```

import 에 `RecoveryTier` 를 추가한다:

```python
from app.core.enums import ModuleStatus, RecoveryTier, RunStatus
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_failure_signal.py tests/test_worker_gateway_errors.py tests/test_session_server.py -v`
Expected: PASS

- [ ] **Step 9: 전체 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — tier 1/2 가 아직 실행되지 않으므로 동작은 여전히 현행과 같다.

- [ ] **Step 10: 커밋**

```bash
git add app/execution/results.py app/execution/protocol.py app/runner/workflow_engine.py app/execution/worker_gateway.py worker/http_server.py app/contexts/run/application/service.py tests/test_failure_signal.py
git commit -m "feat(run): 실패 신호를 실행 경계에서 도메인까지 배선

workflow_engine 의 except 절이 예외를 분류하고, StepExecutionResult 와 워커
HTTP 응답이 신호를 운반해 decide_post_step_failure 가 실제 신호를 본다.
되감기 실행은 아직 없으므로 런타임 동작은 불변이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: 모듈 진입 URL 캡처 + `recover_session` 포트

**Files:**
- Modify: `app/execution/gateway.py` (포트에 `recover_session` 기본 구현 추가)
- Modify: `app/execution/simulated_gateway.py`
- Modify: `app/contexts/run/application/service.py`
- Test: `tests/test_run_checkpoint_integration.py` (신규 테스트는 `tests/test_recovery_tier_execution.py` 로 분리)

**Interfaces:**
- Consumes: `RecoveryTier` (Task 2), `ExecutionHandle` (기존)
- Produces:
  - `ExecutionGateway.recover_session(handle: ExecutionHandle, tier: RecoveryTier, entry_url: str | None) -> bool` — 되감기 성공 여부. 기본 구현은 `False`(미지원).
  - `SimulatedExecutionGateway.recovery_calls: list[tuple[RecoveryTier, str | None]]` — 테스트 관찰용

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_recovery_tier_execution.py` 를 새로 만든다.

```python
"""복구 등급 실행(되감기) 배선 테스트."""

from __future__ import annotations

from app.core.enums import RecoveryTier
from app.execution.gateway import ExecutionGateway, ExecutionHandle


class _MinimalGateway(ExecutionGateway):
    """recover_session 을 구현하지 않은 어댑터 — 기본 구현이 False 여야 한다."""

    def supports(self, execution_mode: str) -> bool:
        return True

    async def open_session(self, execution_mode, input_data, run_id, module_id, storage_state=None):
        raise NotImplementedError

    async def run_step(self, handle, run_id, module, on_log):
        raise NotImplementedError

    async def submit_input(self, handle, value):
        raise NotImplementedError

    async def close_session(self, handle):
        raise NotImplementedError

    async def resume_from_step(self, handle, module_index, workflow_step):
        raise NotImplementedError


async def test_recover_session_defaults_to_unsupported():
    """되감기를 지원하지 않는 어댑터는 조용히 False 를 돌려준다(기존 어댑터 무변경)."""
    gateway = _MinimalGateway()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    supported = await gateway.recover_session(
        handle, RecoveryTier.RESET_TO_MODULE_ENTRY, "https://example.com/entry"
    )

    assert supported is False


async def test_simulated_gateway_records_recovery_calls():
    from app.execution.simulated_gateway import SimulatedExecutionGateway

    gateway = SimulatedExecutionGateway()
    handle = ExecutionHandle(execution_mode="simulated", session_id="s1")

    await gateway.recover_session(handle, RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert gateway.recovery_calls == [(RecoveryTier.REPLAY_FROM_LOGIN, None)]


async def test_tier_zero_never_calls_recover_session():
    """tier 0 은 현행 동작 — 되감기 호출이 없어야 한다."""
    from app.execution.simulated_gateway import SimulatedExecutionGateway

    gateway = SimulatedExecutionGateway()
    assert gateway.recovery_calls == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_recovery_tier_execution.py -v`
Expected: FAIL — `AttributeError: '_MinimalGateway' object has no attribute 'recover_session'`

- [ ] **Step 3: 포트에 기본 구현 추가**

`app/execution/gateway.py` — import 에 추가:

```python
from app.core.enums import RecoveryTier
```

`capture_storage_state` 아래에 추가한다 (**추상 메서드가 아니다** — 기존 어댑터를 깨지 않기 위함):

```python
    async def recover_session(
        self,
        handle: ExecutionHandle,
        tier: RecoveryTier,
        entry_url: str | None,
    ) -> bool:
        """재시도 **전에** 세션을 ``tier`` 만큼 되감는다. 되감았으면 True.

        - ``RESET_TO_MODULE_ENTRY``: 열린 다이얼로그를 정리하고 ``entry_url`` 로 재이동한다.
        - ``REPLAY_FROM_LOGIN``: 세션을 폐기·재개설한다.

        되감기를 지원하지 않는 어댑터는 기본 ``False`` 를 돌려주고, 인터프리터는 그 경우
        tier 0(제자리 재시도)과 동일하게 진행한다. ``RETRY_IN_PLACE`` 는 되감기가 없으므로
        인터프리터가 아예 호출하지 않는다.
        """
        return False
```

- [ ] **Step 4: 시뮬레이션 게이트웨이에 관찰 지점 추가**

`app/execution/simulated_gateway.py` — import 와 필드·메서드를 추가한다.

```python
from app.core.enums import RecoveryTier
```

`__init__` 에 추가:

```python
        # 테스트 관찰용 — 어떤 등급으로 몇 번 되감았는지.
        self.recovery_calls: list[tuple[RecoveryTier, str | None]] = []
```

클래스에 메서드를 추가:

```python
    async def recover_session(
        self,
        handle: ExecutionHandle,
        tier: RecoveryTier,
        entry_url: str | None,
    ) -> bool:
        self.recovery_calls.append((tier, entry_url))
        return True
```

- [ ] **Step 5: 모듈 진입 URL 캡처**

`app/contexts/run/application/service.py` — `while True:` 루프 직전, `attempted_tiers` 선언 옆에 추가한다.

```python
                # tier 1 되감기 지점. 매니페스트에 진입 URL 필드가 없으므로(설계 §3.3)
                # 모듈 첫 실행 시점의 페이지 URL 을 런타임에서 잡아 둔다.
                module_entry_url: str | None = None
```

그리고 `while True:` 안, `execution_result` 를 받은 **직후**에 첫 시도의 URL 을 보존한다:

```python
                    if module_entry_url is None:
                        module_entry_url = execution_result.current_url
```

> `current_url` 은 모듈 **종료** 시점의 URL 이므로 완벽한 진입 지점은 아니다. 그러나 첫 시도에서 실패한 모듈의 종료 URL 은 대개 해당 모듈이 머물던 화면이며, 되감기의 목표는 "정확한 진입점 복원"이 아니라 "오염된 상태 탈출"이다. 캡처가 `None` 이면 Step 6 이 tier 0 으로 폴백한다.

- [ ] **Step 6: 인터프리터가 tier 를 실행**

`service.py` 의 `RetryModule` 처리 블록을 교체한다.

```python
if isinstance(post, RetryModule):
    attempted_tiers.append(post.tier)
    if post.tier is not RecoveryTier.RETRY_IN_PLACE:
        await self._recover_session_for_retry(run, module, handle, post.tier, module_entry_url)
    aggregate.record_retry(module)
    await self._persist(run, aggregate)
    await asyncio.sleep(post.backoff_ms / 1000)
    await self._transition_to_running(run, module)
    continue
```

`RunService` 클래스에 헬퍼를 추가한다.

```python
    async def _recover_session_for_retry(
        self,
        run: Run,
        module: RunModule,
        handle: ExecutionHandle,
        tier: RecoveryTier,
        entry_url: str | None,
    ) -> None:
        """재시도 전 세션 되감기. 실패해도 재시도 자체는 진행한다(tier 0 폴백)."""
        # 되감을 곳을 모른 채 세션을 버리는 것이 더 위험하므로 tier 0 으로 폴백한다(설계 §3.3).
        if tier is RecoveryTier.RESET_TO_MODULE_ENTRY and entry_url is None:
            logger.info(
                "모듈 진입 URL 미확보 — 제자리 재시도로 폴백",
                log_event="run.recovery.fallback",
                run_id=run.run_id,
                module_id=module.module_id,
            )
            return
        try:
            recovered = await self._gateway.recover_session(handle, tier, entry_url)
        except Exception:
            logger.exception(
                "세션 되감기 실패 — 제자리 재시도로 진행",
                log_event="run.recovery.failed",
                run_id=run.run_id,
                module_id=module.module_id,
            )
            return
        logger.info(
            "세션 되감기",
            log_event="run.recovery.applied" if recovered else "run.recovery.unsupported",
            run_id=run.run_id,
            module_id=module.module_id,
            recovery_tier=int(tier),
        )
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_recovery_tier_execution.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: 전체 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 9: 커밋**

```bash
git add app/execution/gateway.py app/execution/simulated_gateway.py app/contexts/run/application/service.py tests/test_recovery_tier_execution.py
git commit -m "feat(run): recover_session 포트와 모듈 진입 URL 캡처 추가

tier 1/2 결정을 인터프리터가 게이트웨이 되감기로 위임한다. 포트 기본 구현은
False(미지원)이므로 기존 어댑터는 무변경이며, 되감기 실패·URL 미확보 시
tier 0 으로 폴백해 재시도 자체는 계속된다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: 워커 측 되감기 실제 구현

**Files:**
- Modify: `worker/session_server.py`
- Modify: `worker/http_server.py`
- Modify: `app/execution/protocol.py`
- Modify: `app/execution/worker_gateway.py`
- Test: `tests/test_session_server.py`

**Interfaces:**
- Consumes: `RecoveryTier` (Task 2), `ExecutionGateway.recover_session` (Task 4)
- Produces:
  - `SessionServer.recover(session_id: str, tier: RecoveryTier, entry_url: str | None) -> bool`
  - HTTP `POST /sessions/{session_id}/recover`, body `RecoverSessionRequest`, response `RecoverSessionResponse`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_session_server.py` 끝에 추가한다.

먼저 기존 페이크를 확장한다. `tests/test_session_server.py:33` 의 `_FakePage` 와 `:38` 의 `_FakeRuntime` 을 아래로 교체한다 (기존 필드는 모두 보존한다).

```python
class _FakePage:
    def __init__(self) -> None:
        self.context = _FakeContext()
        self.goto_calls: list[str] = []
        self.load_states: list[str] = []

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_calls.append(url)

    def wait_for_load_state(self, state: str = "load", **_kwargs) -> None:
        self.load_states.append(state)


class _FakeRuntime:
    def __init__(self) -> None:
        self.build_thread = threading.get_ident()
        self.closed = False
        self.otp: str | None = None
        self.page = _FakePage()
        self.dialog_messages: list[str] = []
```

그리고 파일 끝에 테스트를 추가한다. **기존 `server` 픽스처(`:90`)를 그대로 쓴다.**

```python
# --- 복구 등급 되감기 --------------------------------------------------------


async def test_recover_tier_one_navigates_to_entry_url(server):
    """tier 1 은 다이얼로그 기록을 끊고 진입 URL 로 재이동한다."""
    from app.core.enums import RecoveryTier

    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    runtime = srv._require_session(session_id).runtime  # noqa: SLF001
    runtime.dialog_messages.append("이전 모듈의 팝업")

    recovered = await srv.recover(
        session_id, RecoveryTier.RESET_TO_MODULE_ENTRY, "https://example.com/entry"
    )

    assert recovered is True
    assert runtime.page.goto_calls == ["https://example.com/entry"]
    assert runtime.dialog_messages == []


async def test_recover_tier_one_without_entry_url_is_noop(server):
    from app.core.enums import RecoveryTier

    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")
    runtime = srv._require_session(session_id).runtime  # noqa: SLF001

    recovered = await srv.recover(session_id, RecoveryTier.RESET_TO_MODULE_ENTRY, None)

    assert recovered is False
    assert runtime.page.goto_calls == []


async def test_recover_tier_two_rebuilds_runtime(server):
    """tier 2 는 런타임을 폐기하고 같은 session_id 로 다시 만든다."""
    from app.core.enums import RecoveryTier

    srv, fake = server
    session_id = await srv.open_session("fake", {"id": "u1"}, "run1", "m1")
    first_runtime = srv._require_session(session_id).runtime  # noqa: SLF001

    recovered = await srv.recover(session_id, RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert recovered is True
    assert fake.closed is True  # 옛 런타임은 닫혔다
    assert srv._require_session(session_id).runtime is not first_runtime  # noqa: SLF001
    assert srv.get_session_run_id(session_id) == "run1"  # 세션 식별자는 유지된다


async def test_recover_unknown_session_returns_false(server):
    from app.core.enums import RecoveryTier

    srv, _fake = server

    recovered = await srv.recover("없는세션", RecoveryTier.REPLAY_FROM_LOGIN, None)

    assert recovered is False


async def test_recover_tier_zero_is_rejected(server):
    """tier 0 은 되감기가 없으므로 워커까지 오면 안 된다."""
    from app.core.enums import RecoveryTier

    srv, _fake = server
    session_id = await srv.open_session("fake", {}, "run1", "m1")

    assert await srv.recover(session_id, RecoveryTier.RETRY_IN_PLACE, None) is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_session_server.py -v -k recover`
Expected: FAIL — `AttributeError: 'SessionServer' object has no attribute 'recover'`

- [ ] **Step 3: `SessionServer.recover` 구현**

`worker/session_server.py` — import 에 추가:

```python
from app.core.enums import RecoveryTier
```

`capture_storage_state` 아래에 메서드를 추가한다.

```python
async def recover(
    self,
    session_id: str,
    tier: RecoveryTier,
    entry_url: str | None,
) -> bool:
    """재시도 전에 세션을 ``tier`` 만큼 되감는다. 되감았으면 True.

    되감기 실패는 예외로 전파하지 않는다 — 호출자는 실패 시 제자리 재시도로 진행한다.
    """
    try:
        session = self._require_session(session_id)
    except Exception:
        return False

    if tier is RecoveryTier.RESET_TO_MODULE_ENTRY:
        if entry_url is None:
            return False
        return await self._reset_to_entry(session, entry_url)
    if tier is RecoveryTier.REPLAY_FROM_LOGIN:
        return await self._reopen_session(session)
    return False


async def _reset_to_entry(self, session: _Session, entry_url: str) -> bool:
    """열린 다이얼로그 기록을 끊고 진입 URL 로 재이동한다."""

    def _navigate() -> bool:
        page = session.runtime.page
        # 되감기 이후의 스텝이 과거 다이얼로그를 자기 것으로 오해하지 않도록 경계를 끊는다.
        dialogs = getattr(session.runtime, "dialog_messages", None)
        if dialogs is not None:
            dialogs.clear()
        page.goto(entry_url)
        page.wait_for_load_state("domcontentloaded")
        return True

    try:
        # session.executor 는 **ThreadPoolExecutor**(세션 전용 단일 스레드 풀)다.
        # Playwright sync 객체의 스레드 어피니티 때문에 반드시 이 풀에서 실행해야 한다.
        return await self._run_on_session_thread(session.executor, _navigate)
    except Exception:
        return False


async def _reopen_session(self, session: _Session) -> bool:
    """런타임을 폐기하고 같은 session_id 로 다시 만든다(로그인부터 재주행하기 위함)."""
    workflow_executor = self._executors[session.execution_mode]

    def _rebuild():
        workflow_executor.close_runtime(session.runtime)
        return workflow_executor.build_runtime(
            session.input_data, session.run_id, session.module_id
        )

    try:
        session.runtime = await self._run_on_session_thread(session.executor, _rebuild)
    except Exception:
        return False
    return True
```

**`_Session` 확장이 필요하다.** 현재 `_Session`(`worker/session_server.py:26`)은 `execution_mode`·`runtime`·`executor`(스레드 풀)·`run_id` 만 보관하며, `build_runtime(input_data, run_id, module_id)` 재호출에 필요한 **`input_data` 와 `module_id` 가 없다.** 두 필드를 추가한다.

```python
@dataclass
class _Session:
    """워커 내부 라이브 세션(Playwright 런타임 + 단일 스레드 풀)."""

    execution_mode: str
    runtime: Any
    executor: ThreadPoolExecutor
    run_id: str
    # tier 2 되감기(런타임 재생성)에 필요한 최초 개설 인자.
    input_data: dict[str, str]
    module_id: str
    resume_module_index: int | None = None
    resume_workflow_step: str | None = None
```

`open_session`(`:61`)에서 `_Session(...)` 을 만들 때 두 필드를 함께 채운다.

- [ ] **Step 4: HTTP 엔드포인트 추가**

`app/execution/protocol.py` 에 추가한다.

```python
class RecoverSessionRequest(BaseModel):
    tier: int
    entry_url: str | None = None


class RecoverSessionResponse(BaseModel):
    recovered: bool
```

`worker/http_server.py` 에 라우트를 추가한다 (기존 라우트 등록 패턴을 따를 것).

```python
@app.post("/sessions/{session_id}/recover", response_model=RecoverSessionResponse)
async def recover_session(session_id: str, request: RecoverSessionRequest):
    recovered = await server.recover(session_id, RecoveryTier(request.tier), request.entry_url)
    return RecoverSessionResponse(recovered=recovered)
```

- [ ] **Step 5: `WorkerExecutionGateway.recover_session` 구현**

`app/execution/worker_gateway.py` 에 추가한다 (기존 HTTP 호출 헬퍼 패턴을 따를 것).

```python
async def recover_session(
    self,
    handle: ExecutionHandle,
    tier: RecoveryTier,
    entry_url: str | None,
) -> bool:
    payload = RecoverSessionRequest(tier=int(tier), entry_url=entry_url)
    response = await self._post(f"/sessions/{handle.session_id}/recover", payload.model_dump())
    return RecoverSessionResponse.model_validate(response).recovered
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_session_server.py -v`
Expected: PASS

- [ ] **Step 7: 전체 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 8: 커밋**

```bash
git add worker/session_server.py worker/http_server.py app/execution/protocol.py app/execution/worker_gateway.py tests/test_session_server.py
git commit -m "feat(worker): tier 1/2 세션 되감기 구현

tier 1 은 다이얼로그 기록을 끊고 진입 URL 로 재이동하며, tier 2 는 브라우저를
폐기·재개설한다. 되감기 실패는 예외로 전파하지 않고 False 로 보고해 호출자가
제자리 재시도로 진행하게 한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: 복구 가시성 (설계 목표 3 — 필수 동반 배포)

> **이 태스크는 Task 4·5 와 반드시 함께 배포되어야 한다.** 자동 복구가 무엇을 덮었는지 볼 수 없으면 담당자는 자동화를 신뢰할 수 없다(설계 §3.4).

**Files:**
- Modify: `app/core/run_models.py:23-44` (`RunModule`)
- Modify: `app/contexts/run/contracts/records.py:13-33` (`RunModuleRecord`)
- Modify: `app/contexts/run/domain/events.py`
- Modify: `app/contexts/run/domain/aggregate.py:312-330`
- Modify: `app/contexts/run/infrastructure/codec.py`
- Modify: `app/contexts/run/application/service.py`
- Test: `tests/test_run_aggregate.py`, `tests/test_run_event_codec.py`

**Interfaces:**
- Consumes: `RecoveryTier` (Task 2), `FailureSignal` (Task 1)
- Produces:
  - `RunModule.recovered: bool`, `RunModule.recovery_tiers: list[int]`, `RunModule.failure_signals: list[str]`
  - `RunModuleRecovered(module_id: str, attempts: int, tiers: list[int], module: RunModuleRecord | None = None)`
  - `RunAggregate.record_retry(module, tier=None, failure_signal=None)`, `RunAggregate.record_recovered(module)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_aggregate.py` 끝에 추가한다.

```python
# --- 복구 가시성 -------------------------------------------------------------


def test_record_retry_accumulates_tier_and_signal_history():
    from app.core.enums import FailureSignal, RecoveryTier

    aggregate, module = _aggregate_with_single_module()

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

    aggregate, module = _aggregate_with_single_module()
    aggregate.record_retry(
        module, tier=RecoveryTier.RETRY_IN_PLACE, failure_signal=FailureSignal.TIMEOUT
    )

    aggregate.record_recovered(module)

    assert module.recovered is True
    emitted = [r.event for r in aggregate.drain_events()]
    assert any(isinstance(e, RunModuleRecovered) for e in emitted)


def test_module_without_retry_is_not_marked_recovered():
    aggregate, module = _aggregate_with_single_module()

    aggregate.record_recovered(module)

    assert module.recovered is False
```

> **구현자 주의:** `_aggregate_with_single_module()` 헬퍼와 `drain_events()` 의 실제 이름은 `tests/test_run_aggregate.py` 와 `app/contexts/run/domain/aggregate.py` 를 읽고 **기존 패턴에 맞춰** 사용하라. 이 파일에는 이미 애그리거트를 만드는 헬퍼가 있다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_run_aggregate.py -v -k "recover"`
Expected: FAIL — `TypeError: record_retry() got an unexpected keyword argument 'tier'`

- [ ] **Step 3: 모델 필드 추가**

`app/core/run_models.py` 의 `RunModule` — `failure_analysis` 위에 추가한다.

```python
    # 자동 복구 가시성(설계 §3.4). "통과했다"와 "불안정하다"는 직교하는 축이므로,
    # 상태(PASSED/ANOMALY/ERROR)를 건드리지 않고 별도 필드로 표현한다.
    recovered: bool = False
    recovery_tiers: list[int] = Field(default_factory=list)
    failure_signals: list[str] = Field(default_factory=list)
```

`app/contexts/run/contracts/records.py` 의 `RunModuleRecord` 에도 **동일한 3필드**를 같은 위치에 추가한다 (`from_domain` 은 `model_dump` 기반이라 자동 반영된다).

- [ ] **Step 4: 이벤트 추가**

`app/contexts/run/domain/events.py` — `RunModuleRetried` 아래에 추가한다.

```python
@dataclass(frozen=True)
class RunModuleRecovered:
    """재시도를 거쳐 최종 통과한 모듈. 자동 복구가 무엇을 덮었는지 남기는 감사 기록이다."""

    module_id: str
    attempts: int
    tiers: list[int] = field(default_factory=list)
    module: RunModuleRecord | None = None
```

같은 파일의 `RunEvent` 유니온에 `RunModuleRecovered` 를 추가한다.

- [ ] **Step 5: 애그리거트 수정**

`app/contexts/run/domain/aggregate.py` — `record_retry` 를 교체하고 `record_recovered` 를 추가한다.

```python
def record_retry(
    self,
    module: RunModule,
    tier: RecoveryTier | None = None,
    failure_signal: FailureSignal | None = None,
) -> None:
    """정책상 재시도 — attempt 를 올리고 모듈을 다시 큐잉한다."""
    module.attempt += 1
    module.retry_count += 1
    module.status = ModuleStatus.QUEUED
    module.message = f"재시도 {module.attempt}/{module.max_attempts}"
    module.started_at = None
    module.ended_at = None
    module.duration_ms = None
    module.failure_analysis = None
    if tier is not None:
        module.recovery_tiers.append(int(tier))
    if failure_signal is not None:
        module.failure_signals.append(str(failure_signal))
    self._emit(
        RunModuleRetried(
            module_id=module.module_id,
            attempt=module.attempt,
            module=self._module_wire(module),
        )
    )


def record_recovered(self, module: RunModule) -> None:
    """재시도를 거쳐 통과한 모듈에 복구 표식을 남긴다. 재시도가 없었으면 no-op."""
    if module.retry_count == 0:
        return
    module.recovered = True
    self._emit(
        RunModuleRecovered(
            module_id=module.module_id,
            attempts=module.attempt,
            tiers=list(module.recovery_tiers),
            module=self._module_wire(module),
        )
    )
```

import 에 `FailureSignal`, `RecoveryTier`, `RunModuleRecovered` 를 추가한다.

- [ ] **Step 6: 코덱 확장**

`app/contexts/run/infrastructure/codec.py`:

1. import 에 `RunModuleRecovered` 추가
2. `_TYPES` 딕셔너리에 `"RunModuleRecovered": RunModuleRecovered,` 추가
3. `_event_to_payload` 의 `RunModuleRetried` 분기 **아래**에 추가:

```python
    if isinstance(event, RunModuleRecovered):
        return {
            "module_id": event.module_id,
            "attempts": event.attempts,
            "tiers": list(event.tiers),
            "module": _module_to_wire(event.module),
        }
```

4. 디코드 측 `elif cls is RunModuleRetried:` 분기에 `RunModuleRecovered` 를 함께 넣는다:

```python
    elif cls in {RunModuleRetried, RunModuleRecovered}:
        kwargs["module"] = _wire_to_module(kwargs.get("module"))
```

- [ ] **Step 7: 코덱 테스트 갱신**

`tests/test_run_event_codec.py` 는 **17개 이벤트의 payload 키 집합을 불변으로 고정**한다. 두 가지를 반영한다.

1. `RunModuleRecovered` 케이스 추가 (기존 케이스 작성 방식을 그대로 따를 것)
2. `_module_to_wire` 가 `RunModuleRecord.model_dump(mode="json")` 이므로, **module 을 담는 모든 이벤트의 module wire 키 집합에 신규 3필드가 추가된다.** 해당 기대값을 갱신한다.

추가로 하위호환 테스트를 넣는다.

```python
def test_legacy_module_wire_without_recovery_fields_decodes():
    """신규 필드가 없는 과거 이벤트 payload 도 기본값으로 복원되어야 한다."""
    from app.contexts.run.infrastructure.codec import _wire_to_module

    legacy = {
        "module_id": "m1",
        "name": "모듈",
        "group": "g",
        "order": 1,
        "status": "PASSED",
    }

    record = _wire_to_module(legacy)

    assert record is not None
    assert record.recovered is False
    assert record.recovery_tiers == []
    assert record.failure_signals == []
```

- [ ] **Step 8: 인터프리터 배선**

`app/contexts/run/application/service.py` — `RetryModule` 블록의 `record_retry` 호출에 인자를 추가한다.

```python
                        aggregate.record_retry(
                            module,
                            tier=post.tier,
                            failure_signal=execution_result.failure_signal,
                        )
```

그리고 `CompleteStep` 처리 직후(`self._record_module_result(...)` 아래, `aggregate.finish_timing(module)` 위)에 복구 기록을 추가한다.

```python
                    self._record_module_result(aggregate, module, execution_result)
                    if execution_result.status is ModuleStatus.PASSED:
                        aggregate.record_recovered(module)
                    aggregate.finish_timing(module)
```

- [ ] **Step 9: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_run_aggregate.py tests/test_run_event_codec.py tests/test_snapshot_rebuild.py tests/test_projection_handlers.py -v`
Expected: PASS

- [ ] **Step 10: 전체 회귀 + 스냅샷·프로젝션 게이트**

Run: `python3 -m pytest tests/ -q && python3 scripts/ci/run_all_gates.py --gate snapshot_validate && python3 scripts/ci/run_all_gates.py --gate projection_validate`
Expected: 모두 PASS

- [ ] **Step 11: 커밋**

```bash
git add app/core/run_models.py app/contexts/run/contracts/records.py app/contexts/run/domain/events.py app/contexts/run/domain/aggregate.py app/contexts/run/infrastructure/codec.py app/contexts/run/application/service.py tests/test_run_aggregate.py tests/test_run_event_codec.py
git commit -m "feat(run): 자동 복구 가시성(recovered/tier/signal 이력) 추가

재시도를 거쳐 통과한 모듈에 recovered 표식과 RunModuleRecovered 이벤트를
남긴다. 상태 3분류(PASSED/ANOMALY/ERROR)는 건드리지 않는다 — 통과와 불안정은
직교하는 축이다.

신규 필드는 모두 기본값을 가져 기존 이벤트 스트림 재생과 호환된다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: 복구 표식 UI 노출

**Files:**
- Modify: `app/web/templates/run.html`
- Modify: `app/web/static/app.css`
- Modify: `app/web/templates/dashboard/partials/zone_b_matrix.html`
- Modify: `app/notifications/run_completion_email.py`
- Test: `tests/test_run_detail_recovery_badge.py` (**신규**)

**Interfaces:**
- Consumes: `RunModule.recovered`, `RunModule.recovery_tiers`, `RunModule.retry_count` (Task 6)
- Produces: 없음 (표현 계층 종단)

> **뷰 계층은 손댈 필요가 없다.** `RunView.modules` 는 `list[RunModule]` 로 도메인 엔티티를 그대로 재사용한다(`app/contexts/run/views/view.py:34`). 따라서 Task 6 에서 `RunModule` 에 추가한 세 필드가 **자동으로** 템플릿까지 흐른다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_detail_recovery_badge.py` 를 새로 만든다.

```python
"""Run 상세 화면의 자동 복구 배지 렌더링 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_dashboard
from app.api.dependencies import get_run_queries
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.views.view import RunView
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import RunModule


def _run_view(*, recovered: bool) -> RunView:
    """모듈 1개만 담은 Run 상세 뷰."""
    return RunView(
        run_id="run1",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PASSED,
        status_label="정상",
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="m1",
                name="로그인",
                group="인증",
                order=1,
                status=ModuleStatus.PASSED,
                retry_count=2 if recovered else 0,
                attempt=3 if recovered else 1,
                max_attempts=3,
                recovered=recovered,
                recovery_tiers=[0, 1] if recovered else [],
                failure_signals=["TIMEOUT", "DIALOG"] if recovered else [],
            )
        ],
    )


class _StubRunQueries:
    def __init__(self, run: RunView) -> None:
        self._run = run

    async def get_run_detail(self, run_id: str) -> RunView:
        if run_id != self._run.run_id:
            raise KeyError(run_id)
        return self._run


def _build_client(run: RunView) -> TestClient:
    app = FastAPI()
    app.include_router(routes_dashboard.router)
    app.dependency_overrides[get_run_queries] = lambda: _StubRunQueries(run)
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="u1", username="tester", role="admin"
    )
    return TestClient(app)


@pytest.fixture
def recovered_client() -> TestClient:
    with _build_client(_run_view(recovered=True)) as client:
        yield client


@pytest.fixture
def clean_client() -> TestClient:
    with _build_client(_run_view(recovered=False)) as client:
        yield client


def test_run_detail_shows_recovered_badge(recovered_client: TestClient) -> None:
    html = recovered_client.get("/runs/run1").text

    assert "자동 복구됨" in html
    assert "badge--recovered" in html


def test_run_detail_omits_badge_for_clean_module(clean_client: TestClient) -> None:
    html = clean_client.get("/runs/run1").text

    assert "자동 복구됨" not in html
```

> **구현자 주의:** `User` 생성자의 실제 필수 필드는 `app/contexts/identity/models.py` 를 읽고 맞춰라. `run.html` 이 `base.html` 을 상속하며 요구하는 추가 컨텍스트(내비게이션 배지 등)가 있으면 렌더가 실패한다 — 그 경우 `tests/test_dashboard_fragments_http.py:98` 의 `_build_app` 이 어떤 라우터·의존성을 함께 등록하는지 참고해 최소 조합을 맞춰라.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py -v -k recovered`
Expected: FAIL — `assert "자동 복구됨" in response.text`

- [ ] **Step 3: Run 상세 템플릿에 배지 추가**

`app/web/templates/run.html` 의 모듈 행 렌더링 블록에 추가한다.

```html
{% if module.recovered %}
<span class="badge badge--recovered"
      title="재시도 {{ module.retry_count }}회 후 통과 (복구 등급 {{ module.recovery_tiers | join(' → ') }})">
  자동 복구됨 ({{ module.retry_count }}회 재시도)
</span>
{% endif %}
```

- [ ] **Step 4: 배지 스타일 추가**

`app/web/static/app.css` 에 추가한다. **기존 배지 토큰·색 변수를 재사용**하고 새 색을 발명하지 말 것.

```css
/* 자동 복구 배지 — 통과했지만 불안정했음을 알린다(주의 계열, 실패 계열 아님). */
.badge--recovered {
  background: var(--color-warn-surface);
  color: var(--color-warn-text);
  border: 1px solid var(--color-warn-border);
}
```

- [ ] **Step 5: 일간 현황에 불안정 표식**

`app/web/templates/dashboard/partials/zone_b_matrix.html` 의 시스템·모듈 셀에 추가한다.

```html
{% if cell.recovered %}<span class="cell-flag cell-flag--unstable" title="자동 복구 발생">⟳</span>{% endif %}
```

`app/orchestrator/queries` 의 일간 대시보드 쿼리가 `recovered` 를 셀에 채우도록 수정한다 (해당 빌더는 `app/contexts/insights/application/daily_dashboard.py`).

- [ ] **Step 6: 완료 이메일에 복구 요약**

`app/notifications/run_completion_email.py` 의 본문 구성부에 추가한다.

```python
    recovered_modules = [m for m in run.modules if m.recovered]
    if recovered_modules:
        names = ", ".join(m.name for m in recovered_modules)
        lines.append(f"자동 복구된 모듈: {names}")
```

> **구현자 주의:** 실제 변수명(`lines` 등)은 파일을 읽고 기존 본문 조립 패턴에 맞춰라.

- [ ] **Step 7: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py tests/test_daily_dashboard.py tests/test_email_notification_dedup.py -v`
Expected: PASS

- [ ] **Step 8: 커밋**

```bash
git add app/web/templates app/web/static/app.css app/contexts/insights/application/daily_dashboard.py app/notifications/run_completion_email.py tests/test_dashboard_fragments_http.py
git commit -m "feat(dashboard): 자동 복구 표식 노출

Run 상세에 자동 복구 배지, 일간 현황에 불안정 표식, 완료 이메일에 복구 요약을
추가한다. 이상징후 인박스에는 넣지 않는다 — 인박스는 사람의 조치가 필요한
건만 담는다(설계 §3.4).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Run 수준 자동 재실행 게이트

**Files:**
- Modify: `app/core/settings.py`
- Modify: `app/core/run_models.py` (`Run.auto_rerun_of`)
- Modify: `app/contexts/run/contracts/records.py` (`RunRecord.auto_rerun_of`)
- Modify: `app/contexts/run/domain/state_machine.py`
- Modify: `app/contexts/run/application/service.py`
- Test: `tests/test_run_state_machine.py`, `tests/test_run_retention.py` → 신규 `tests/test_auto_rerun_gate.py`

**Interfaces:**
- Consumes: `RunStatus` (기존)
- Produces:
  - `RunStateMachine.decide_auto_rerun(*, run_status, triggered_by, is_auto_rerun, budget_remaining) -> AutoRerunDecision`
  - `AutoRerunDecision = TriggerAutoRerun | SkipAutoRerun`
  - `Run.auto_rerun_of: str | None`
  - `E2ESettings.auto_rerun_enabled: bool`, `E2ESettings.run_max_duration_s: int | None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_auto_rerun_gate.py` 를 새로 만든다.

```python
"""Run 수준 자동 재실행 게이트(순수 결정) 테스트."""

from __future__ import annotations

import pytest

from app.contexts.run.domain.state_machine import (
    RunStateMachine,
    SkipAutoRerun,
    TriggerAutoRerun,
)
from app.core.enums import RunStatus


def _decide(**overrides):
    kwargs = {
        "run_status": RunStatus.ERROR,
        "triggered_by": "schedule",
        "is_auto_rerun": False,
        "budget_remaining": 1,
    }
    kwargs.update(overrides)
    return RunStateMachine.decide_auto_rerun(**kwargs)


def test_scheduled_error_run_triggers_auto_rerun():
    assert isinstance(_decide(), TriggerAutoRerun)


@pytest.mark.parametrize("status", [RunStatus.ANOMALY, RunStatus.PASSED, RunStatus.CANCELLED])
def test_non_error_status_never_reruns(status):
    """설계 §3.5·§3.6 — 사이트 이상은 절대 자동 재실행하지 않는다."""
    assert isinstance(_decide(run_status=status), SkipAutoRerun)


def test_manual_run_never_reruns():
    """사람이 보고 있는 실행은 판단을 뺏지 않는다."""
    assert isinstance(_decide(triggered_by="manual"), SkipAutoRerun)


def test_auto_rerun_does_not_chain():
    assert isinstance(_decide(is_auto_rerun=True), SkipAutoRerun)


def test_exhausted_budget_skips():
    assert isinstance(_decide(budget_remaining=0), SkipAutoRerun)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_auto_rerun_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'TriggerAutoRerun'`

- [ ] **Step 3: 결정 타입·함수 추가**

`app/contexts/run/domain/state_machine.py` — 부분 재실행 결정 블록 아래에 추가한다.

```python
# --- Run 수준 자동 재실행 결정 -----------------------------------------------


@dataclass(frozen=True)
class TriggerAutoRerun:
    """도구 오류로 끝난 예약 Run 을 1회 자동 재실행한다."""


@dataclass(frozen=True)
class SkipAutoRerun:
    """자동 재실행 조건에 해당하지 않는다."""


AutoRerunDecision = TriggerAutoRerun | SkipAutoRerun
```

`RunStateMachine` 에 메서드를 추가한다.

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_auto_rerun_gate.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 설정·모델 필드 추가**

`app/core/settings.py` 의 `E2ESettings` 에 추가한다.

```python
    # 예약 Run 이 도구 오류(ERROR)로 끝났을 때 1회 자동 재실행할지(설계 §3.6).
    auto_rerun_enabled: bool = False
    # Run 총 실행 시간 상한(초). None 이면 무제한 — 기본값이 기존 동작을 유지한다.
    run_max_duration_s: int | None = None
```

`app/core/run_models.py` 의 `Run` 과 `app/contexts/run/contracts/records.py` 의 `RunRecord` 에 각각 추가한다.

```python
    # 자동 재실행으로 생성된 Run 이면 원본 Run 의 id. 이력에서 한 쌍으로 보이게 한다.
    auto_rerun_of: str | None = None
```

- [ ] **Step 6: 인터프리터 배선**

`app/contexts/run/application/service.py` — Run 이 최종 상태로 봉인된 직후(`FinalizeRun` 처리 이후) 자동 재실행을 판정한다.

```python
        decision = RunStateMachine.decide_auto_rerun(
            run_status=run.status,
            triggered_by=run.triggered_by,
            is_auto_rerun=run.auto_rerun_of is not None,
            budget_remaining=1 if self._settings.auto_rerun_enabled else 0,
        )
        if isinstance(decision, TriggerAutoRerun):
            await self._enqueue_auto_rerun(run)
```

`_enqueue_auto_rerun` 은 **새 실행 경로를 만들지 않고** 기존 부분 재실행 진입점을 재사용한다.

```python
    async def _enqueue_auto_rerun(self, run: Run) -> None:
        """실패 모듈부터 1회 자동 재실행한다(설계 §3.6). 실패해도 원본 Run 결과는 보존한다."""
        failed = next(
            (m for m in run.modules if m.status in (ModuleStatus.ERROR, ModuleStatus.FAILED)),
            None,
        )
        if failed is None:
            return
        try:
            await self.start_partial_rerun(
                run_id=run.run_id,
                from_module_id=failed.module_id,
                auto_rerun_of=run.run_id,
            )
        except Exception:
            logger.exception(
                "자동 재실행 큐잉 실패",
                log_event="run.auto_rerun.failed",
                run_id=run.run_id,
            )
```

> **구현자 주의:** `start_partial_rerun` 의 실제 이름·시그니처를 `service.py` 에서 확인하고 맞춰라. `auto_rerun_of` 파라미터를 그 메서드에 추가해야 한다.

- [ ] **Step 7: OTP 안전장치 (설계 R3)**

tier 2(로그인 재주행)가 OTP 를 다시 요구해 무인 실행을 멈추는 것을 막는다. `_recover_session_for_retry` 앞에 조건을 추가한다.

```python
        # R3 — 로그인 재주행 경로에 사람 입력이 필요한 모듈이 있는데 OTP 중계가 없으면
        # tier 2 는 무인 실행을 멈추게 한다. 되감지 말고 실패를 확정하는 편이 낫다.
        if tier is RecoveryTier.REPLAY_FROM_LOGIN and self._requires_manual_input(run):
            if not self._settings.otp_relay_token:
                logger.info(
                    "OTP 중계 미설정 — 로그인 재주행 생략",
                    log_event="run.recovery.skipped_otp",
                    run_id=run.run_id,
                )
                return
```

```python
    def _requires_manual_input(self, run: Run) -> bool:
        definitions = self._registry.modules_for(run.system_code)
        return any(d.requires_user_input for d in definitions)
```

> **구현자 주의:** `self._registry` 의 모듈 조회 메서드명과 `self._settings.otp_relay_token` 의 실제 설정 필드명을 `app/registry/loader.py` · `app/core/settings.py` 에서 확인하고 맞춰라.

- [ ] **Step 8: 전체 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — `auto_rerun_enabled` 기본값이 `False` 이므로 기존 동작 불변

- [ ] **Step 9: 커밋**

```bash
git add app/core/settings.py app/core/run_models.py app/contexts/run/contracts/records.py app/contexts/run/domain/state_machine.py app/contexts/run/application/service.py tests/test_auto_rerun_gate.py
git commit -m "feat(run): Run 수준 자동 재실행 게이트 추가

예약 Run 이 도구 오류(ERROR)로 끝난 경우에만 실패 모듈부터 1회 자동 재실행한다.
ANOMALY·수동 실행·자동 재실행 연쇄는 모두 차단한다.

기본값 auto_rerun_enabled=False 로 도입 자체는 동작을 바꾸지 않는다.
OTP 중계 미설정 시 tier 2 를 생략해 무인 실행이 멈추지 않게 한다(설계 R3).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: 복구 예산·시간 상한·알림 중복 방지

설계 §3.6 예산표와 위험 R4·R6 을 집행한다. Task 8 은 게이트만 만들었고 **예산은 아직 강제되지 않는다.**

**Files:**
- Modify: `app/contexts/run/domain/state_machine.py`
- Modify: `app/contexts/run/domain/events.py`
- Modify: `app/contexts/run/infrastructure/codec.py`
- Modify: `app/contexts/run/application/service.py`
- Modify: `app/notifications/run_completion_email.py`
- Test: `tests/test_run_state_machine.py`, `tests/test_auto_rerun_gate.py`, `tests/test_email_notification_dedup.py`

**Interfaces:**
- Consumes: `RecoveryTier` (Task 2), `TriggerAutoRerun` (Task 8), `RunModule.recovery_tiers` (Task 6)
- Produces:
  - `RunStateMachine.decide_post_step_failure(..., tier2_used: int = 0, tier2_budget: int = 2)` — tier 2 예산 초과 시 등급을 낮춘다
  - `RunAutoRerunTriggered(original_run_id: str, from_module_id: str)`
  - `RunService._run_deadline_exceeded(run) -> bool`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_state_machine.py` 의 복구 등급 블록 끝에 추가한다.

```python
def test_tier_two_budget_exhaustion_downgrades_to_tier_one():
    """로그인 재주행은 비싸다 — Run 당 예산을 넘으면 등급을 낮춘다(설계 §3.6)."""
    decision = _failure_decision(
        failure_signal=FailureSignal.SESSION_LOST,
        tier2_used=2,
        tier2_budget=2,
    )
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.RESET_TO_MODULE_ENTRY


def test_tier_two_allowed_while_budget_remains():
    decision = _failure_decision(
        failure_signal=FailureSignal.SESSION_LOST,
        tier2_used=1,
        tier2_budget=2,
    )
    assert isinstance(decision, RetryModule)
    assert decision.tier is RecoveryTier.REPLAY_FROM_LOGIN
```

`tests/test_auto_rerun_gate.py` 끝에 추가한다.

```python
def test_auto_rerun_emits_event_with_original_run_id():
    from app.contexts.run.domain.events import RunAutoRerunTriggered

    event = RunAutoRerunTriggered(original_run_id="run1", from_module_id="m2")

    assert event.original_run_id == "run1"
    assert event.from_module_id == "m2"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_run_state_machine.py tests/test_auto_rerun_gate.py -v -k "tier_two_budget or tier_two_allowed or emits_event"`
Expected: FAIL — `TypeError: decide_post_step_failure() got an unexpected keyword argument 'tier2_used'`

- [ ] **Step 3: tier 2 예산을 결정 함수에 반영**

`app/contexts/run/domain/state_machine.py` — `decide_post_step_failure` 시그니처에 두 인자를 추가한다.

```python
tier2_used: int = (0,)
tier2_budget: int = (2,)
```

`_escalated_tier` 호출을 예산 반영 버전으로 바꾼다.

```python
            tier = _escalated_tier(failure_signal, attempted_tiers)
            # 로그인 재주행은 비싸므로 Run 당 예산을 넘기면 한 단계 낮춘다(설계 §3.6).
            if tier is RecoveryTier.REPLAY_FROM_LOGIN and tier2_used >= tier2_budget:
                tier = RecoveryTier.RESET_TO_MODULE_ENTRY
            return RetryModule(backoff_ms=backoff_ms, tier=tier)
```

- [ ] **Step 4: 이벤트 추가**

`app/contexts/run/domain/events.py` 에 추가하고 `RunEvent` 유니온에 넣는다.

```python
@dataclass(frozen=True)
class RunAutoRerunTriggered:
    """도구 오류로 끝난 예약 Run 이 자동 재실행을 발동시켰다(감사 기록)."""

    original_run_id: str
    from_module_id: str
```

`app/contexts/run/infrastructure/codec.py` 의 `_TYPES` 에 `"RunAutoRerunTriggered": RunAutoRerunTriggered,` 를 추가하고, `_event_to_payload` 에 분기를 추가한다.

```python
    if isinstance(event, RunAutoRerunTriggered):
        return {
            "original_run_id": event.original_run_id,
            "from_module_id": event.from_module_id,
        }
```

`tests/test_run_event_codec.py` 에 이 이벤트의 왕복 케이스를 추가한다 (기존 케이스 작성 방식을 따를 것).

- [ ] **Step 5: 인터프리터에 예산·시간 상한 배선**

`app/contexts/run/application/service.py` — `decide_post_step_failure` 호출에 예산을 넘긴다.

```python
                            tier2_used=sum(
                                1
                                for t in attempted_tiers
                                if t is RecoveryTier.REPLAY_FROM_LOGIN
                            ),
                            tier2_budget=self._settings.recovery_tier2_budget,
                        )
```

`app/core/settings.py` 에 추가한다.

```python
    # Run 당 로그인 재주행(tier 2) 허용 횟수(설계 §3.6).
    recovery_tier2_budget: int = 2
```

Run 총 실행 시간 상한을 집행한다. `RunService` 에 헬퍼를 추가하고, `while True:` 루프의 재시도 분기 앞에서 검사한다.

```python
    def _run_deadline_exceeded(self, run: Run) -> bool:
        """Run 총 실행 시간 상한 초과 여부. 미설정(None)이면 항상 False(기존 동작)."""
        limit = self._settings.run_max_duration_s
        if limit is None or run.started_at is None:
            return False
        return (datetime.now(UTC) - run.started_at).total_seconds() > limit
```

```python
                    if isinstance(post, RetryModule):
                        if self._run_deadline_exceeded(run):
                            logger.info(
                                "Run 실행 시간 상한 초과 — 재시도 중단",
                                log_event="run.recovery.deadline",
                                run_id=run.run_id,
                            )
                            post = CompleteStep()
                        else:
                            ...  # 기존 재시도 처리(Task 6 Step 8 의 최종 형태)
```

> **구현자 주의:** 위 분기는 기존 `if isinstance(post, RetryModule):` 블록을 감싸는 형태다. `post = CompleteStep()` 으로 바꾼 뒤에는 아래의 `assert isinstance(post, CompleteStep)` 경로로 자연스럽게 떨어져야 한다. 실제 편집 시 제어 흐름을 확인하라.

- [ ] **Step 6: 자동 재실행 알림 중복 방지 (R4)**

`_enqueue_auto_rerun` 에서 이벤트를 발행하고, 완료 이메일이 원본 Run 을 건너뛰게 한다.

`app/notifications/run_completion_email.py` 의 발송 판정에 조건을 추가한다.

```python
    # R4 — 자동 재실행이 예정된 Run 은 알림을 보류한다. 재실행 Run 의 결과가
    # 최종 결과이므로, 원본과 재실행이 각각 메일을 보내면 담당자에게 중복으로 도달한다.
    if run.auto_rerun_pending:
        return
```

`app/core/run_models.py` 의 `Run` 과 `RunRecord` 에 필드를 추가한다.

```python
    # 자동 재실행이 큐잉되어 이 Run 의 결과가 최종이 아님을 알린다(알림 보류용).
    auto_rerun_pending: bool = False
```

`_enqueue_auto_rerun` 은 재실행 큐잉 **성공 시에만** 이 플래그를 세운다 — 큐잉이 실패하면 원본 Run 의 알림이 정상 발송되어야 한다.

- [ ] **Step 7: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_run_state_machine.py tests/test_auto_rerun_gate.py tests/test_run_event_codec.py tests/test_email_notification_dedup.py -v`
Expected: PASS

- [ ] **Step 8: 전체 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — `run_max_duration_s=None`, `auto_rerun_enabled=False` 기본값으로 동작 불변

- [ ] **Step 9: 커밋**

```bash
git add app/contexts/run/domain/state_machine.py app/contexts/run/domain/events.py app/contexts/run/infrastructure/codec.py app/contexts/run/application/service.py app/core/settings.py app/core/run_models.py app/contexts/run/contracts/records.py app/notifications/run_completion_email.py tests/
git commit -m "feat(run): 복구 예산·시간 상한·알림 중복 방지 추가

tier 2(로그인 재주행) 예산 초과 시 등급을 낮추고, Run 총 실행 시간 상한을
넘으면 재시도를 중단한다. 자동 재실행이 예정된 Run 은 완료 알림을 보류해
원본과 재실행이 중복 발송되지 않게 한다(설계 R4·R6).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: 행동 명세(`SPEC-RUN-006`) 작성과 문서 정합

**Files:**
- Create: `docs/specs/run/06-self-recovery-loop.md`
- Modify: `docs/specs/README.md`
- Modify: `docs/specs/platform/03-execution-gateway.md`
- Modify: `docs/E2E_ARCHITECTURE.md`
- Modify: `docs/INSTALL.md`
- Modify: `tests/test_run_state_machine.py`, `tests/test_auto_rerun_gate.py` (spec 마커 부착)

**Interfaces:**
- Consumes: Task 1~9 의 모든 산출물
- Produces: `SPEC-RUN-006` + `AC-001`~`AC-007`

- [ ] **Step 1: 행동 명세 작성**

`docs/specs/run/06-self-recovery-loop.md` 를 `docs/specs/_TEMPLATE.md` 형식 그대로 작성한다. 아래 AC 를 반드시 포함한다.

```gherkin
### AC-001: 신호에 따른 복구 등급 선택
Given ERROR 로 끝난 모듈과 재시도 예산 잔여
When 실패 신호가 SESSION_LOST 다
Then 결정은 RetryModule(tier=REPLAY_FROM_LOGIN) 이다

### AC-002: 사이트 이상은 자동 재시도하지 않는다
Given 매니페스트가 retryable_on 에 ANOMALY 를 선언했다
When 모듈이 SITE 신호로 실패한다
Then 결정은 CompleteStep 이며 재시도하지 않는다

### AC-003: 등급 상승
Given 같은 모듈이 tier 0 으로 이미 재시도해 실패했다
When TIMEOUT 신호로 다시 실패한다
Then 결정은 RetryModule(tier=RESET_TO_MODULE_ENTRY) 이다

### AC-004: 복구 가시성
Given 모듈이 2회 재시도 후 통과했다
When Run 상세를 조회한다
Then 모듈 상태는 PASSED 이고 recovered=true 이며 "자동 복구됨" 배지가 보인다

### AC-005: 되감기 실패 시 폴백
Given tier 1 결정이 내려졌으나 모듈 진입 URL 이 없다
When 재시도를 진행한다
Then 되감기를 생략하고 제자리 재시도(tier 0)로 진행한다

### AC-006: 자동 재실행 게이트
Given 예약 Run 이 ERROR 로 끝났고 auto_rerun_enabled=true 다
When Run 이 봉인된다
Then 실패 모듈부터 1회 자동 재실행이 큐잉되고 auto_rerun_of 가 원본 run_id 다

### AC-007: tier 2 예산
Given 같은 Run 에서 로그인 재주행을 이미 2회 사용했다
When 모듈이 SESSION_LOST 신호로 다시 실패한다
Then 결정은 RetryModule(tier=RESET_TO_MODULE_ENTRY) 로 낮춰진다
```

- [ ] **Step 2: 인덱스 등록**

`docs/specs/README.md` 의 "Run 오케스트레이션" 표에 행을 추가한다.

```markdown
| SPEC-RUN-006 | [run/06-self-recovery-loop.md](run/06-self-recovery-loop.md) | 실패 신호·복구 등급·자동 재실행 |
```

- [ ] **Step 3: 관련 SSOT 문서 갱신**

- `docs/specs/platform/03-execution-gateway.md`: `recover_session` 포트 메서드를 계약에 추가
- `docs/E2E_ARCHITECTURE.md` §2: 재시도 설명에 복구 등급을 반영
- `docs/INSTALL.md`: `E2E_AUTO_RERUN_ENABLED`, `E2E_RUN_MAX_DURATION_S`, `E2E_RECOVERY_TIER2_BUDGET` env 추가

- [ ] **Step 4: spec 마커 부착**

Task 2·8·9 에서 작성한 테스트에 마커를 단다.

```python
@pytest.mark.spec("SPEC-RUN-006", "AC-002")
def test_site_signal_never_retries_even_when_policy_allows(): ...
```

AC-001·003·004·005·006·007 도 대응 테스트에 각각 부착한다.

- [ ] **Step 5: 추적성·문서 게이트 확인**

Run: `python3 -m pytest tests/test_spec_traceability.py -v && python3 scripts/check_docs_consistency.py`
Expected: PASS

- [ ] **Step 6: 전체 게이트 확인**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 PASS (import_contracts · pyright_decider · projection_validate · snapshot_validate · ruff · pytest · coverage 래칫 포함)

- [ ] **Step 7: 커밋**

```bash
git add docs tests
git commit -m "docs(run): SPEC-RUN-006 자동 복구 루프 행동 명세 추가

AC-001~006 을 정의하고 대응 테스트에 spec 마커를 부착한다. 실행 게이트웨이
계약(SPEC-PLATFORM-003)에 recover_session 을 추가하고 아키텍처·설치 문서를
새 설정값에 맞춘다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: 수동 검증과 커버리지 래칫

**Files:**
- Modify: `pyproject.toml` (`[tool.coverage.report] fail_under`)

**Interfaces:**
- Consumes: Task 1~10 전체
- Produces: 없음 (종단)

- [ ] **Step 1: 커버리지 측정**

Run: `python3 -m pytest tests/ --cov=app --cov=worker --cov-report=term-missing -q`
Expected: 현재 `fail_under = 57` 보다 높은 수치. 신규 순수 함수 비중이 높아 상승이 정상이다.

- [ ] **Step 2: 래칫 상향**

측정된 수치(내림)로 `pyproject.toml:39` 의 `fail_under` 를 올린다. **수치가 57 이하로 나왔다면 올리지 말고 원인을 조사하라** — 신규 코드에 테스트가 빠졌다는 뜻이다.

- [ ] **Step 3: 시뮬레이션 모드 수동 검증**

`docs/INSTALL.md` 의 로컬 실행 절차로 앱을 띄우고, 시뮬레이션 시스템으로 아래를 확인한다.

| 확인 항목 | 기대 |
| --- | --- |
| 모듈이 ERROR 로 실패 후 재시도해 통과 | Run 상세에 "자동 복구됨 (N회 재시도)" 배지 |
| 모듈이 ANOMALY 로 실패 | 재시도 없이 즉시 확정, 배지 없음 |
| 일간 점검 현황 | 복구가 있던 시스템에 불안정 표식 |
| 완료 이메일 | "자동 복구된 모듈: ..." 줄 존재 |

- [ ] **Step 4: 실브라우저 tier 1/2 수동 검증**

`E2E_EXECUTION_MODE=remote` + 워커로 실제 브라우저 Run 을 돌린다. `docs/INSTALL.md` 절차를 따른다.

| 확인 항목 | 기대 |
| --- | --- |
| 모듈 중간에 페이지를 수동으로 다른 URL 로 이동시킨 뒤 실패 유도 | 로그에 `run.recovery.applied`, tier 1 되감기 후 통과 |
| 브라우저 컨텍스트를 강제 종료 | `SESSION_LOST` → tier 2 → 세션 재개설 |
| OTP 필요 시스템에서 `E2E_OTP_RELAY_TOKEN` 미설정 | 로그에 `run.recovery.skipped_otp`, tier 2 생략 |

- [ ] **Step 5: 최종 게이트**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 PASS

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml
git commit -m "chore(ci): 자동 복구 루프 도입 후 커버리지 래칫 상향

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 실행 순서 요약

| # | 태스크 | 배포 시 동작 변화 |
| --- | --- | --- |
| 1 | 실패 신호 분류 | 없음 (새 함수만) |
| 2 | 복구 등급 결정 | 없음 (기본값 = 현행) |
| 3 | 신호 배선 | 없음 (tier 미실행) |
| 4 | `recover_session` 포트 + 진입 URL | **시뮬레이션에서 tier 실행 시작** |
| 5 | 워커 되감기 구현 | **실브라우저 tier 1/2 동작** |
| 6 | 복구 가시성 | **배지·이벤트 노출** (Task 4·5 와 동반 필수) |
| 7 | UI 노출 | 화면·이메일 반영 |
| 8 | 자동 재실행 게이트 | 없음 (기본 비활성) |
| 9 | 예산·시간 상한·알림 중복 방지 | 없음 (기본값이 현행) |
| 10 | 행동 명세·문서 | 없음 |
| 11 | 수동 검증·래칫 | 없음 |

**롤백 지점:** Task 3 까지는 언제든 되돌려도 동작 변화가 없다. Task 4 부터 실제 복구가 시작되므로, 운영 투입은 Task 6(가시성)까지 완료한 뒤에 한다.
