# 자동 복구 루프 (Self-Recovery Loop) — Design

**작성일:** 2026-08-17
**상태:** 초안 (사용자 리뷰 대기)
**후속 행동 명세:** `SPEC-RUN-006` (`docs/specs/run/06-self-recovery-loop.md`)
**대상:** `app/contexts/run/domain/state_machine.py`, `app/contexts/run/domain/aggregate.py`, `app/contexts/run/domain/events.py`, `app/contexts/run/application/service.py`, `app/contexts/run/infrastructure/codec.py`, `app/runner/workflow_engine.py`, `app/execution/results.py`, `app/execution/protocol.py`, `app/domain/execution_policy.py`, `app/core/system_models.py`

---

## 1. 문제

### 1.1 증상

점검 담당자가 이 도구를 쓸 때 **실패 후 재실행 루프**에 시간을 뺏긴다. Run 이 중간에 깨지면 사람이 원인을 보고, 고치고, **처음부터 다시 돌린다.**

### 1.2 재시도는 이미 있다

모듈 단위 재시도 정책은 이미 순수 결정 함수로 구현돼 있다.

`app/contexts/run/domain/state_machine.py:172`

```python
if step_status in retryable_on and current_attempt < max_attempts:
    return RetryModule(backoff_ms=backoff_ms)
return CompleteStep()
```

매니페스트도 모듈별로 정책을 선언한다 (`app/systems/{hom,fp,chbot}/manifest.yaml`). `retryable_on` 기본값은 이미 `[ERROR]` 이므로 — **"도구 실패만 재시도하고 사이트 이상은 재시도하지 않는다"는 규칙은 이미 지켜지고 있다.**

그런데도 증상이 남아 있다. 원인은 재시도의 **유무**가 아니라 재시도의 **형태**다.

### 1.3 근본 원인 — 재시도가 세션 상태를 되감지 않는다

`app/contexts/run/application/service.py:710`

```python
if isinstance(post, RetryModule):
    aggregate.record_retry(module)
    await self._persist(run, aggregate)
    await asyncio.sleep(post.backoff_ms / 1000)
    await self._transition_to_running(run, module)
    continue
```

`continue` 는 같은 `handle`(같은 브라우저 세션·같은 페이지)로 루프 위쪽의 `self._gateway.run_step(...)` 을 다시 부른다. 즉 **재시도는 backoff 만 넣고 완전히 동일한 조건에서 같은 일을 반복한다.**

실패 원인이 일시적 타이밍이면 이걸로 충분하다. 그러나 실무에서 잦은 실패는 그런 종류가 아니다.

| 실패 원인 | 현재 재시도의 결과 |
| --- | --- |
| 일시적 타임아웃·네트워크 지연 | 복구 가능 ✅ |
| 예상 못 한 팝업·다이얼로그가 페이지를 덮음 | 같은 이유로 재실패 ❌ |
| 이전 스텝이 페이지를 다른 URL 로 이탈시킴 | 같은 이유로 재실패 ❌ |
| 세션·로그인 만료 | 같은 이유로 재실패 ❌ |

담당자 눈에 이건 "재시도해도 어차피 안 되는 것"으로 보인다. 그래서 `max_retries` 를 올려도 체감이 없고, 결국 사람이 처음부터 다시 돌린다.

### 1.4 되감기 결정은 이미 있는데 이 경로에 연결돼 있지 않다

`RunStateMachine.decide_rehydration` 은 세션을 어디까지 되감을지 이미 판정한다.

`app/contexts/run/domain/state_machine.py:205`

```python
if storage_state_valid:
    return ResumeFromCheckpoint(from_index=checkpoint_module_index + 1)
return ReplayFromLogin(
    from_index=login_module_index if login_module_index is not None else 0
)
```

그러나 이 함수는 **프로세스 재기동 복구 경로**(`reconcile_interrupted_runs`, `SPEC-RUN-004`)에서만 호출된다. 실패 재시도 경로는 이 판정을 전혀 쓰지 않는다.

> 핵심: 필요한 부품이 두 개 다 있는데 **서로 연결되어 있지 않다.** 재시도(§1.2)는 되감기를 모르고, 되감기(§1.4)는 재시도를 모른다.

### 1.5 실패의 성격이 오케스트레이션까지 올라오지 않는다

되감기 등급을 고르려면 "왜 실패했는가"가 필요하다. 그런데 현재 분류는 **2단계뿐**이다.

`app/runner/workflow_engine.py:194`

```python
except RuntimeError as exc:
    status = ModuleStatus.ANOMALY   # 사이트 이상
    ...
except Exception as exc:
    status = ModuleStatus.ERROR     # 도구 실패
```

`StepExecutionResult` 는 `last_error: str | None` 로 원문 메시지만 넘긴다 (`app/execution/results.py:27`). 도메인이 문자열을 파싱하지 않는 한 타임아웃인지 세션 만료인지 구분할 수 없고, **문자열 sniffing 은 이 코드베이스가 `StepOutcome` 도입으로 명시적으로 걷어낸 안티패턴**이다 (`app/runner/step_outcome.py` 모듈 독스트링).

### 1.6 자동 복구한 사실이 결과에 남지 않는다

`record_retry` 는 `RunModuleRetried` 이벤트를 발행하지만 (`aggregate.py:312`), 재시도 끝에 통과하면 모듈 최종 상태는 그냥 `PASSED` 다. 결과 화면·일간 현황·이메일 어디에도 **"이 모듈은 2번 실패하고 3번째에 통과했다"** 가 드러나지 않는다.

이건 사소한 표시 문제가 아니라 **자동화의 전제조건**이다. 도구가 무엇을 덮었는지 볼 수 없으면 사람은 자동 복구를 신뢰할 수 없고, 신뢰할 수 없는 자동화는 결국 무시된다.

### 1.7 Run 수준 자동 재실행이 없다

부분 재실행 결정(`decide_partial_rerun` → `ResumeFromModule`)은 있으나 **사람이 UI 에서 지점을 골라 눌러야** 발동한다. 새벽 예약 Run 이 도구 오류로 깨지면 아침까지 아무 일도 일어나지 않는다.

---

## 2. 목표 / 비목표

### 목표

1. **도구 실패(`ERROR`)는 사람 개입 없이 복구를 시도한다** — 세션 상태를 적절한 지점까지 되감은 뒤 재시도한다.
2. **사이트 이상(`ANOMALY`)은 절대 자동 복구하지 않는다** — 이 문서 전체에서 가장 강한 규칙. §3.5 참조.
3. **자동 복구한 사실은 반드시 보인다** — 복구가 성공해도 흔적이 남는다. 목표 3 없이 목표 1 만 구현하는 것은 금지한다.
4. **기존 아키텍처 원칙을 깨지 않는다** — 결정은 순수 함수, 부작용은 인터프리터, 실행 평면 격리, decider 망라성.

### 비목표

- 라이브 뷰 / 브라우저 화면 스트리밍 (별도: A-2)
- 모바일 승인 · 푸시 알림 (별도: A-3)
- 실패 원인의 AI 진단 리포트 격상 (별도: B)
- 담당자 노코드 시나리오 저작 (기각됨 — 비현실적으로 판단)
- **자가 치유 엔진 변경** — 셀렉터 치유(`SPEC-HEAL-001`)는 스텝 *내부*에서 이미 동작한다. 이 설계는 스텝 *바깥*의 재시도 계층이며 둘은 독립이다.

---

## 3. 설계

### 3.1 실패 신호 (`FailureSignal`)

되감기 등급을 고르기 위한 **최소한의** 실패 분류를 도입한다. AI 도 휴리스틱 문자열 매칭도 아니고, 예외 타입 기반의 순수 매핑이다.

```python
class FailureSignal(StrEnum):
    TIMEOUT       = "TIMEOUT"        # 대기 시간 초과
    SELECTOR_MISS = "SELECTOR_MISS"  # 요소를 찾지 못함
    NAVIGATION    = "NAVIGATION"     # 페이지 이동·로드 실패
    SESSION_LOST  = "SESSION_LOST"   # 세션·로그인 만료, 컨텍스트 소실
    DIALOG        = "DIALOG"         # 예기치 않은 다이얼로그·팝업
    SITE          = "SITE"           # 사이트 이상 (RuntimeError → ANOMALY)
    UNKNOWN       = "UNKNOWN"        # 미분류
```

**분류 위치:** `app/runner/workflow_engine.py` 의 `execute_step` except 절. 여기가 **예외 객체 자체를 볼 수 있는 유일한 지점**이며, 이미 `ANOMALY`/`ERROR` 를 가르고 있는 곳이다.

**분류 함수:** `app/runner/failure_signal.py` 에 순수 함수로 분리한다.

```python
def classify_failure(exc: BaseException) -> FailureSignal: ...
```

| 조건 | 신호 |
| --- | --- |
| `RuntimeError` (의도적 사이트 이상 신호) | `SITE` |
| Playwright `TimeoutError` | `TIMEOUT` |
| Playwright `Error` 중 메시지가 셀렉터 해석 실패 | `SELECTOR_MISS` |
| Playwright `Error` 중 navigation/`net::` 계열 | `NAVIGATION` |
| `TargetClosedError` · 컨텍스트/페이지 소실 계열 | `SESSION_LOST` |
| 그 외 | `UNKNOWN` |

> **주의:** Playwright 예외의 세부 판별에는 메시지 검사가 일부 불가피하다. 그러나 이 검사는 **어댑터 경계 안(runner)에 갇히고**, 도메인은 오직 `FailureSignal` enum 만 본다. §1.5 가 지적한 안티패턴(도메인이 문자열을 sniff)은 발생하지 않는다.

**운반 경로:** `StepExecutionResult` 에 필드를 추가한다.

```python
failure_signal: FailureSignal = FailureSignal.UNKNOWN
```

기본값이 있으므로 기존 생성자 호출부는 변경 없이 동작한다 (`StepExecutionResult.failure` 포함).

### 3.2 복구 등급 (`RecoveryTier`)

재시도를 "무엇을 되감고 다시 하는가"로 계층화한다.

| Tier | 이름 | 되감기 범위 | 비용 |
| --- | --- | --- | --- |
| 0 | `RETRY_IN_PLACE` | 없음. backoff 후 같은 페이지에서 재시도 (**현행 동작**) | 낮음 |
| 1 | `RESET_TO_MODULE_ENTRY` | 다이얼로그 정리 → 모듈 진입 URL 로 재이동 → 재시도 | 중간 |
| 2 | `REPLAY_FROM_LOGIN` | 세션 폐기 → 재개설 → 로그인 모듈부터 실패 모듈까지 주행 | 높음 |

**신호 → 등급 매핑** (순수 테이블):

| `FailureSignal` | Tier |
| --- | --- |
| `TIMEOUT` | 0 |
| `SELECTOR_MISS` | 0 |
| `DIALOG` | 1 |
| `NAVIGATION` | 1 |
| `SESSION_LOST` | 2 |
| `UNKNOWN` | 0 |
| `SITE` | — (복구 대상 아님, §3.5) |

**등급 상승(escalation):** 같은 모듈에서 같은 tier 로 재실패하면 다음 시도는 한 단계 올린다. `TIMEOUT` 이 3번 연속이면 0 → 0 → 1 로 올라간다. 이유: 반복되는 타임아웃은 대개 페이지가 이미 잘못된 상태라는 뜻이다.

**결정 함수 확장:** `decide_post_step_failure` 는 순수성을 유지한 채 입력 두 개(`failure_signal`, `attempted_tiers`)를 받고 `RetryModule` 에 `tier` 를 실어 반환한다.

```python
@dataclass(frozen=True)
class RetryModule:
    backoff_ms: int
    tier: RecoveryTier
```

> `app/contexts/run/domain/commands.py` 의 `RetryModule` (커맨드)과 `state_machine` 의 `RetryModule` (결정)은 **현재도 이름이 겹치는 별개 타입**이다. 이 설계는 결정 쪽만 확장한다. 구현 계획에서 이름 혼동을 방지할 것.

### 3.3 되감기 실행 — 게이트웨이 포트 확장

Tier 1·2 는 브라우저 세션에 손을 대므로 **실행 평면의 책임**이다. 도메인은 tier 만 정하고, 실행은 `ExecutionGateway` 포트에 위임한다.

```python
class ExecutionGatewayPort(Protocol):
    async def recover_session(
        self, handle: SessionHandle, tier: RecoveryTier, entry_url: str | None
    ) -> RecoveryOutcome: ...
```

| Tier | 워커(`worker/session_server.py`) 동작 |
| --- | --- |
| 1 | 열린 다이얼로그 닫기 → `page.goto(entry_url)` → 로드 완료 대기 |
| 2 | `close_session` → `open_session(storage_state=None)` → 로그인 모듈부터 `resume_from_step` |

**`entry_url` 문제 — 여기서 설계 판단이 하나 필요했다.**

`ModuleDefinition` 에는 **모듈 진입 URL 필드가 없다** (`app/core/system_models.py:10-34` 확인). 따라서 tier 1 의 되감기 지점을 매니페스트에서 읽어올 수 없다.

선택지는 둘이었다.

| 안 | 내용 | 판단 |
| --- | --- | --- |
| (a) 매니페스트에 `entry_url` 필드 추가 | 6개 시스템 × 전 모듈에 URL 을 선언 | **기각** — 저작 부담이 늘고, URL 이 동적인 모듈은 선언 불가 |
| (b) 모듈 시작 시 런타임에서 URL 캡처 | `StartModule` 시점의 `page.url` 을 Run 상태에 보관 | **채택** |

(b) 는 매니페스트 변경이 없고, `_safe_page_url(runtime)` 이 이미 존재하므로 (`workflow_engine.py:323`) 캡처 수단도 이미 있다. 캡처 실패(`None`)면 tier 1 은 **tier 2 로 강등하지 않고 tier 0 으로 폴백**한다 — 되감을 곳을 모르는 채 세션을 버리는 것이 더 위험하기 때문이다.

### 3.4 복구 가시성 (flake 신호)

**목표 3 의 구현이며, 목표 1 과 함께 배포되어야 한다.**

`RunModule` 에 필드를 추가한다.

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `recovered` | `bool` | 재시도를 거쳐 최종 통과했는가 |
| `recovery_tiers` | `list[str]` | 실제로 사용된 등급 이력 (예: `["0","0","1"]`) |
| `failure_signals` | `list[str]` | 각 시도의 실패 신호 |

**모듈 최종 상태는 `PASSED` 를 유지한다.** 등급을 강등하지 않는 이유: 상태 3분류(`PASSED`/`ANOMALY`/`ERROR`)는 이 시스템 전체의 SSOT 이며 (`app/core/status_labels.py`), 여기에 네 번째 개념을 섞으면 집계·알림·통계가 모두 흔들린다. **"통과했다"와 "불안정하다"는 직교하는 축이므로 직교하게 표현한다.**

노출 지점:

| 위치 | 표현 |
| --- | --- |
| Run 상세 화면 | 모듈 행에 "자동 복구됨 (2회 재시도)" 배지 |
| 일간 점검 현황 | 복구된 모듈이 있는 시스템에 불안정 표식 |
| Run 완료 이메일 | 복구 요약 줄 추가 |
| 이상징후 인박스 | **넣지 않음** — 인박스는 사람의 조치가 필요한 건만 담는다 |

### 3.5 안전 규칙 — `ANOMALY` 는 자동 복구하지 않는다

이 설계에서 유일하게 타협 불가한 규칙이다.

> **사이트 이상을 재시도로 덮으면 이 도구의 존재 이유가 무너진다.**

강제 지점을 **두 겹**으로 둔다.

1. `retryable_on` 기본값이 `[ERROR]` 이므로 정책상 이미 차단된다 (기존 동작 유지).
2. 추가로 `decide_post_step_failure` 안에서 `failure_signal is SITE` 이면 **`retryable_on` 설정과 무관하게** `CompleteStep()` 을 반환한다. 매니페스트가 실수로 `retryable_on: [ANOMALY]` 를 선언해도 도메인이 거부한다.

이 규칙은 `test_run_state_machine.py` 에 **명시적 회귀 테스트**로 고정한다.

### 3.6 Run 수준 자동 재실행 게이트

모듈 재시도가 모두 소진되어 Run 이 `ERROR` 로 끝난 경우에만 발동한다.

| 조건 | 동작 |
| --- | --- |
| Run 최종 상태 `ERROR` **and** 트리거가 예약(cron) **and** 자동 재실행 예산 잔여 | 실패 모듈부터 1회 자동 재실행 |
| Run 최종 상태 `ANOMALY` | **재실행 없음** |
| 트리거가 수동 실행 | **재실행 없음** — 사람이 보고 있으므로 판단을 뺏지 않는다 |
| 이미 자동 재실행으로 생성된 Run | **재실행 없음** (연쇄 차단) |

**구현:** 새 실행 경로를 만들지 않고 기존 `PreparePartialRerun` / `decide_partial_rerun` 을 재사용한다. 재실행 Run 은 원본 Run 을 `auto_rerun_of` 로 참조해 이력에서 한 쌍으로 보이게 한다.

**예산:**

| 항목 | 기본값 | 근거 |
| --- | --- | --- |
| Run 당 자동 재실행 | 1회 | 2회 이상 실패하면 사람이 봐야 할 문제다 |
| Run 당 tier 2 총 횟수 | 2회 | 로그인 재주행은 비싸다 |
| Run 당 총 재시도 횟수 | `sum(모듈별 max_retries)` 를 넘지 않음 | 모듈별 예산만 있으면 등급 상승(§3.2)이 총량을 늘릴 수 있다. 이 상한은 **새 설정값이 아니라 기존 매니페스트 값에서 파생**되므로 추가 튜닝 지점을 만들지 않는다 |
| Run 총 실행 시간 상한 | 신규 설정 `E2E_RUN_MAX_DURATION_S` (기본 무제한 = 기존 동작 유지) | 예약 창을 넘기지 않게. 기본값이 무제한이므로 도입 자체로는 기존 동작을 바꾸지 않는다 |

---

## 4. 아키텍처 영향

| 계약 | 영향 | 대응 |
| --- | --- | --- |
| 도메인 순수성 (import-linter) | `state_machine.py` 는 `FailureSignal` enum 만 의존 | enum 을 `app/core/enums.py` 에 둔다 |
| Playwright 격리 | `classify_failure` 가 Playwright 예외 타입 참조 | `app/runner/` 안에 둔다 (실행 평면) |
| 실행 평면 분리 | 게이트웨이 포트에 `recover_session` 추가 | `SPEC-PLATFORM-003` 갱신 필요 |
| decider 망라성 (pyright) | 새 결정·이벤트 타입 추가 | `evolve` / `match` 분기 추가, `reportMatchNotExhaustive` 로 검증 |
| 이벤트 코덱 | `tests/test_run_event_codec.py` 가 **17개 이벤트 payload 키 집합을 불변으로 고정** | 신규 필드는 기본값 포함 추가 + 코덱 테스트 동시 갱신 + **기존 스트림 재생 하위호환 필수** |
| 스냅샷·프로젝션 | `RunModule` 필드 추가 | `snapshot_validate` / `projection_validate` 게이트 통과 확인 |

---

## 5. 상태 전이

| 현재 | 신호 | 다음 | 부작용 |
| --- | --- | --- | --- |
| 모듈 `RUNNING` | `ERROR` + tier 0 결정 | 모듈 `QUEUED` | backoff 후 동일 세션 재시도 |
| 모듈 `RUNNING` | `ERROR` + tier 1 결정 | 모듈 `QUEUED` | 다이얼로그 정리 → `entry_url` 재이동 → 재시도 |
| 모듈 `RUNNING` | `ERROR` + tier 2 결정 | 모듈 `QUEUED` | 세션 재개설 → 로그인부터 주행 → 재시도 |
| 모듈 `RUNNING` | `ANOMALY` (`SITE`) | 모듈 `ANOMALY` | 재시도 없음. 인박스 대상 |
| 모듈 `RUNNING` | 예산 소진 | 모듈 `ERROR` | Run 계속 (기존 blocking 규칙 적용) |
| 모듈 재시도 후 통과 | — | 모듈 `PASSED` | `recovered=true` 기록, 배지 노출 |
| Run `ERROR` 종료 | 예약 Run + 예산 잔여 | 신규 Run `PENDING` | 실패 모듈부터 자동 재실행 |

**신규 이벤트:** `RunModuleRecovered` (복구 성공 사실), `RunAutoRerunTriggered` (자동 재실행 발동).

---

## 6. 테스트 전략

| 유형 | 위치 | 내용 |
| --- | --- | --- |
| 단위 (순수) | `tests/test_run_state_machine.py` | 신호×시도횟수 → tier 결정 테이블 전수 |
| 단위 (순수) | `tests/test_run_state_machine.py` | **`SITE` 는 `retryable_on` 설정과 무관하게 재시도 금지** (§3.5 회귀 고정) |
| 단위 | `tests/test_failure_signal.py` (신규) | 예외 타입 → `FailureSignal` 분류 |
| 단위 | `tests/test_run_aggregate.py` | `recovered` / `recovery_tiers` 기록 |
| 단위 | `tests/test_run_event_codec.py` | 신규 이벤트 payload 키 + **기존 17개 불변** |
| 통합 | `tests/integration/` + `simulated_gateway` | tier 0/1/2 각 경로가 실제로 다른 복구 동작을 유발 |
| 회귀 | 기존 재시도 테스트 전부 | tier 0 = 현행 동작과 **바이트 단위로 동일** |
| CI 게이트 | `run_all_gates.py --profile full` | import 계약 · pyright 망라성 · projection · snapshot |

---

## 7. 위험과 미결 사항

| # | 위험 | 완화 |
| --- | --- | --- |
| R1 | **`RuntimeError` 가 정말 사이트 이상만 의미하는가?** 실제 코드가 도구 오류에도 `RuntimeError` 를 던지고 있다면 §3.5 안전 규칙이 오히려 복구를 막는다 | 구현 착수 전 `app/automation/page_objects/` 의 `raise RuntimeError` 전수 조사 — **첫 번째 작업으로 배치** |
| R2 | 자동 복구가 진짜 장애를 늦게 발견하게 만든다 | tier 2 까지 가면 복구 성공이어도 인박스가 아닌 **운영 로그에 경고** 기록. §3.4 배지로 상시 가시화 |
| R3 | tier 2(로그인 재주행)가 OTP 를 다시 요구해 무인 실행이 멈춘다 | `requires_user_input` 모듈이 재주행 경로에 있으면 tier 2 를 **차단**하고 실패 확정. OTP 중계가 설정된 경우만 허용 |
| R4 | 자동 재실행이 알림을 중복 발송한다 | 기존 이메일 dedup 스토어(`sqlite_email_notification_dedup.py`) 재사용. 원본+재실행을 한 건으로 묶어 발송 |
| R5 | 이벤트 스키마 변경이 기존 Run 이력 재생을 깨뜨린다 | 모든 신규 필드에 기본값. 코덱 하위호환 테스트를 구현 계획 앞쪽에 배치 |
| R6 | 복구가 Run 실행 시간을 크게 늘려 예약 창을 넘긴다 | §3.6 예산·시간 상한 |

**미결 (구현 계획 단계에서 확정):**

- tier 1 의 "다이얼로그 정리" 구체 동작 — 기존 `dialog_messages` 수집 경로와의 상호작용
- 자동 재실행 예산의 설정 노출 위치 (`E2ESettings` vs 매니페스트 vs 예약별)

---

## 8. 이 설계가 담당자에게 주는 것

| 현재 | 이후 |
| --- | --- |
| 도구 오류로 깨지면 사람이 처음부터 재실행 | 도구 오류는 세션을 되감아 자동 복구 |
| 새벽 예약이 깨지면 아침까지 방치 | 예약 Run 은 1회 자동 재실행 후 결과 확정 |
| 재시도로 통과한 사실이 안 보임 | "자동 복구됨" 배지로 불안정 지점이 드러남 |
| 사이트 이상과 도구 오류가 같은 무게로 옴 | 도구 오류는 도구가 삼키고, **사이트 이상만 사람에게 온다** |

---

## 9. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-17 | 초안 | Claude (brainstorming) |
