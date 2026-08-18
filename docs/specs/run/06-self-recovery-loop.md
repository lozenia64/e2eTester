# SPEC-RUN-006: 자동 복구 루프

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-RUN-006` |
| **상태** | `approved` |
| **우선순위** | P1 |
| **의존** | `SPEC-RUN-001`, `SPEC-RUN-002`, `SPEC-PLATFORM-003` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2, `docs/INSTALL.md` |
| **구현 위치** | `app/contexts/run/domain/`, `app/contexts/run/application/service.py`, `app/execution/gateway.py`, `app/runner/failure_signal.py` |

## 1. 개요

### 1.1 목적

도구 실패(`ERROR`)로 끝난 모듈을 세션 상태를 적절한 지점까지 되감아 사람 개입 없이 재시도하고, 재시도로 통과했다는 사실을 결과 화면·대시보드·메일에서 항상 볼 수 있게 한다. 사이트 이상(`ANOMALY`)은 안전 규칙으로 절대 자동 복구하지 않는다. 예약(cron) Run 이 도구 오류로 끝나면 실패 모듈부터 1회 자동 재실행하는 Run 수준 게이트도 포함한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `system` | `RunService`(결정 위임·되감기 호출)·워커 `SessionServer`(되감기 실행)·스케줄러(예약 트리거) |
| `operator` | Run 상세·일간 현황·완료 메일에서 복구 표식을 관찰 |

### 1.3 범위

**In scope:**

- 실패 신호 분류(`FailureSignal`) → 복구 등급(`RecoveryTier`) 결정 → 등급 상승(escalation)
- `ExecutionGateway.recover_session` 을 통한 tier 1(모듈 진입 URL 재이동)·tier 2(세션 재개설·로그인 재주행) 되감기
- 되감기 실패·진입 URL 미확보 시 tier 0(제자리 재시도) 폴백
- 복구 가시성(`recovered`/`recovery_tiers`/`failure_signals`) 및 노출 지점(Run 상세 배지·일간 현황·완료 메일)
- Run 수준 자동 재실행 게이트(`decide_auto_rerun`) — 예약 Run·`ERROR`·예산 잔여일 때만
- tier 2 예산(`E2E_RECOVERY_TIER2_BUDGET`)·Run 실행 시간 상한(`E2E_RUN_MAX_DURATION_S`)
- tier 2 재주행이 사람 입력을 요구하는데 OTP 중계가 없을 때의 안전장치(R3)
- 자동 재실행의 완료 메일 중복 발송 방지(R4)

**Out of scope:**

- 자가 치유 엔진(셀렉터 복구, `SPEC-HEAL-001`) — 스텝 *내부* 동작이며 이 루프와 독립
- 프로세스 재기동 후 세션 체크포인트 복구(`SPEC-RUN-004`)
- 실패 원인의 AI 진단 리포트(`SPEC-INT-003`)
- 라이브 뷰·모바일 승인·푸시 알림

## 2. 기능 요구사항 (FR)

### FR-001: 실패 신호 분류

**설명:** 모듈 실행 예외를 `FailureSignal`(`TIMEOUT`/`SELECTOR_MISS`/`NAVIGATION`/`SESSION_LOST`/`DIALOG`/`SITE`/`UNKNOWN`)로 분류한다. 분류는 `app/runner/failure_signal.py::classify_failure`(실행 평면 경계 안)에서만 수행하고, 절대 예외를 던지지 않는다. 도메인(`state_machine.py`)은 enum 값만 관찰하며 예외 메시지를 직접 들여다보지 않는다.

**비즈니스 규칙:**

1. `RuntimeError`(page object 가 사이트 이상을 알리는 의도적 신호)는 항상 `SITE`.
2. 그 외는 예외 타입·메시지 휴리스틱으로 분류하고, 매칭 실패 시 `UNKNOWN`.
3. `StepExecutionResult.failure_signal` 기본값은 `UNKNOWN` — 기존 생성자 호출부는 변경 없이 동작한다.

### FR-002: 신호 → 등급 매핑·등급 상승

**설명:** `RunStateMachine.decide_post_step_failure` 가 `FailureSignal` 을 `RecoveryTier` 로 매핑하고, 같은 모듈이 같은 등급으로 이미 실패했으면 한 단계 올린다(`REPLAY_FROM_LOGIN` 에서 상한).

**매핑 표:**

| `FailureSignal` | 기본 Tier |
| --- | --- |
| `TIMEOUT` | 0 (`RETRY_IN_PLACE`) |
| `SELECTOR_MISS` | 0 |
| `UNKNOWN` | 0 |
| `DIALOG` | 1 (`RESET_TO_MODULE_ENTRY`) |
| `NAVIGATION` | 1 |
| `SESSION_LOST` | 2 (`REPLAY_FROM_LOGIN`) |
| `SITE` | 복구 대상 아님 (FR-003) |

### FR-003: 사이트 이상 안전 규칙

**설명:** `ANOMALY`(사이트 이상)는 어떤 매니페스트 설정으로도 자동 재시도되지 않는다 — 이 기능 전체에서 유일하게 타협 불가한 규칙이다.

**비즈니스 규칙:**

1. `retryable_on` 기본값이 `[ERROR]` 이므로 정책상 이미 차단된다(기존 동작).
2. `decide_post_step_failure` 는 `failure_signal is SITE` 이면 `retryable_on` 설정과 **무관하게** `CompleteStep()` 을 반환한다 — 매니페스트가 실수로 `ANOMALY` 를 재시도 대상에 넣어도 도메인이 거부한다.

### FR-004: 세션 되감기 실행

**설명:** tier 1·2 결정은 `RunService._recover_session_for_retry` 가 `ExecutionGateway.recover_session(handle, tier, entry_url)` 로 위임한다. 도메인은 tier 만 정하고, 실제 되감기(다이얼로그 정리·재이동·세션 재개설)는 실행 평면(`worker/session_server.py`)이 수행한다.

| Tier | 워커 동작 |
| --- | --- |
| 1 (`RESET_TO_MODULE_ENTRY`) | 열린 다이얼로그 기록 정리 → `page.goto(entry_url)` |
| 2 (`REPLAY_FROM_LOGIN`) | 기존 런타임 폐기 → 같은 `session_id` 로 재개설(재개설 실패 시 옛 런타임 유지) |

**비즈니스 규칙:**

1. `entry_url` 은 매니페스트 필드가 아니라 모듈 첫 실행 시점의 `execution_result.current_url` 을 런타임에서 캡처해 둔다.
2. tier 1 인데 `entry_url` 이 `None` 이면 되감기 자체를 생략하고 tier 0(제자리 재시도)으로 폴백한다 — 되감을 곳을 모른 채 세션을 버리는 것이 더 위험하다.
3. `recover_session` 호출이 예외를 던지면 로그만 남기고 tier 0 으로 폴백한다 — 되감기 실패가 재시도 자체를 막지 않는다.
4. 되감기를 지원하지 않는 어댑터는 포트 기본 구현(`False`)을 그대로 쓴다 — 기존 어댑터 무변경.

### FR-005: tier 2 예산

**설명:** 로그인 재주행(tier 2)은 비용이 크므로, 같은 모듈의 재시도 시퀀스 안에서 이미 사용한 `REPLAY_FROM_LOGIN` 횟수가 `E2E_RECOVERY_TIER2_BUDGET`(기본 2) 이상이면 결정을 한 단계 낮춘 `RESET_TO_MODULE_ENTRY` 로 강등한다.

### FR-006: OTP 안전장치 (R3)

**설명:** tier 2 는 로그인 모듈부터 다시 주행하므로 OTP 입력을 다시 요구할 수 있다. Run 에 `requires_user_input` 모듈이 있는데 `E2E_OTP_RELAY_TOKEN` 이 설정돼 있지 않으면(공백만 있어도 미설정 취급) 되감기를 생략한다 — 무인 실행을 영원히 멈추게 두는 대신 실패를 빠르게 확정한다.

### FR-007: Run 실행 시간 상한

**설명:** 재시도를 진행하기 전 `RunService._run_deadline_exceeded` 가 `run.started_at` 대비 경과 시간을 `E2E_RUN_MAX_DURATION_S` 와 비교한다. 초과하면 재시도를 중단하고 `CompleteStep()` 으로 강제한다. 기본값은 `None`(무제한)이라 도입 자체는 기존 동작을 바꾸지 않는다.

### FR-008: 복구 가시성

**설명:** `RunModule` 에 `recovered`(bool)·`recovery_tiers`(list[int])·`failure_signals`(list[str]) 필드를 추가한다. 재시도 이력을 남기되(`record_retry`), 재시도를 거쳐 최종 통과한 모듈만 `recovered=true` 로 표시한다(`record_recovered`, 재시도 0회면 no-op). 모듈 최종 상태는 그대로 `PASSED` 를 유지한다 — 상태 3분류(`PASSED`/`ANOMALY`/`ERROR`)는 이 시스템의 SSOT(`app/core/status_labels.py`)이므로 복구 여부는 그와 직교하는 별도 축으로 표현한다.

**노출 지점:**

| 위치 | 표현 |
| --- | --- |
| Run 상세 화면(`/runs/{id}`) | 모듈 행에 "자동 복구됨" 배지(`badge--recovered`) |
| 일간 점검 현황(`daily_system_status` 프로젝션) | `recovered` 플래그로 불안정 표식 |
| Run 완료 이메일(HTML/텍스트) | "자동 복구됨" 문구 |
| 이상징후 인박스 | 넣지 않음 — 인박스는 사람 조치가 필요한 건만 담는다 |

### FR-009: Run 수준 자동 재실행 게이트

**설명:** `RunStateMachine.decide_auto_rerun` 이 Run 봉인 시점(`_finalize_run`)에 자동 재실행 여부를 결정한다.

| 조건 | 결과 |
| --- | --- |
| `run_status != ERROR` | `SkipAutoRerun` — `ANOMALY` 는 사이트 이상이므로 절대 재실행하지 않는다 |
| `triggered_by != "schedule"` | `SkipAutoRerun` — 수동 실행은 사람의 판단을 뺏지 않는다 |
| `is_auto_rerun` (이미 자동 재실행으로 이어지는 Run) | `SkipAutoRerun` — 연쇄 차단 |
| `budget_remaining <= 0` | `SkipAutoRerun` |
| 그 외 | `TriggerAutoRerun` |

`budget_remaining` 은 `E2E_AUTO_RERUN_ENABLED` 가 `true` 일 때만 1, 아니면 0 이다 — 기본값 `false` 라 도입 자체는 기존 동작을 바꾸지 않는다.

**비즈니스 규칙:**

1. `TriggerAutoRerun` 이면 실패(ERROR/FAILED) 모듈부터 기존 부분 재실행 경로(`rerun_from_module`)를 재사용해 **같은 `run_id`** 로 제자리 재개한다 — 새 Run 을 만들지 않는다.
2. `auto_rerun_of` 는 그래서 항상 **자기 자신의 `run_id`** 를 가리키는 자기 참조 필드다(별도 원본 Run 을 가리키지 않는다). 자동 재실행 연쇄를 막는 근거(`is_auto_rerun` 판정)로만 쓰인다.
3. 자동 재실행 큐잉이 실패해도 예외를 흡수하고 로그만 남긴다 — 원본 Run 의 결과·완료 알림은 그대로 보존된다.
4. 큐잉이 실제로 성공했을 때만 `auto_rerun_pending` 플래그를 세운다(R4의 전제 조건).

### FR-010: 알림 중복 방지 (R4)

**설명:** 자동 재실행은 같은 `run_id` 를 제자리에서 재개하므로, 완료 메일은 기존 `EmailNotificationSubscriber` + `sqlite_email_notification_dedup.py` 를 그대로 재사용해 원본·재실행을 한 건으로 묶어 발송한다. 새 dedup 메커니즘을 추가하지 않는다.

## 3. 수용 기준 (AC)

### AC-001: 신호에 따른 복구 등급 선택

```gherkin
Given ERROR 로 끝난 모듈과 재시도 예산 잔여
When 실패 신호가 SESSION_LOST 다
Then 결정은 RetryModule(tier=REPLAY_FROM_LOGIN) 이다
```

### AC-002: 사이트 이상은 자동 재시도하지 않는다

```gherkin
Given 매니페스트가 retryable_on 에 ANOMALY 를 선언했다
When 모듈이 SITE 신호로 실패한다
Then 결정은 CompleteStep 이며 재시도하지 않는다
```

### AC-003: 등급 상승

```gherkin
Given 같은 모듈이 tier 0 으로 이미 재시도해 실패했다
When TIMEOUT 신호로 다시 실패한다
Then 결정은 RetryModule(tier=RESET_TO_MODULE_ENTRY) 이다
```

### AC-004: 복구 가시성

```gherkin
Given 모듈이 2회 재시도 후 통과했다
When Run 상세를 조회한다
Then 모듈 상태는 PASSED 이고 recovered=true 이며 "자동 복구됨" 배지가 보인다
```

### AC-005: 되감기 실패 시 폴백

```gherkin
Given tier 1 결정이 내려졌으나 모듈 진입 URL 이 없다
When 재시도를 진행한다
Then 되감기를 생략하고 제자리 재시도(tier 0)로 진행한다
```

### AC-006: 자동 재실행 게이트

```gherkin
Given 예약 Run 이 ERROR 로 끝났고 auto_rerun_enabled=true 다
When Run 이 봉인된다
Then 실패 모듈부터 1회 자동 재실행이 큐잉되고 auto_rerun_of 가 원본 run_id 다
```

### AC-007: tier 2 예산

```gherkin
Given 같은 Run 에서 로그인 재주행을 이미 2회 사용했다
When 모듈이 SESSION_LOST 신호로 다시 실패한다
Then 결정은 RetryModule(tier=RESET_TO_MODULE_ENTRY) 로 낮춰진다
```

## 4. API 계약 (해당 시)

신규 REST 표면 없음. 자동 재실행은 기존 부분 재실행 내부 경로(`RunService.rerun_from_module`, `SPEC-RUN-002`)를 재사용해 제자리에서 트리거된다 — `POST /api/runs/{run_id}/rerun` 을 사람이 호출하는 경로와 별개로, `_finalize_run` 이 같은 내부 메서드를 직접 호출한다.

## 5. 상태·이벤트 (해당 시)

### 5.1 상태 전이

| 현재 | 신호 | 다음 | 부작용 |
| --- | --- | --- | --- |
| 모듈 `RUNNING` | `ERROR` + tier 0 결정 | 모듈 `QUEUED` | backoff 후 동일 세션 재시도 |
| 모듈 `RUNNING` | `ERROR` + tier 1 결정 | 모듈 `QUEUED` | 다이얼로그 정리 → `entry_url` 재이동 → 재시도(URL 없으면 되감기 생략) |
| 모듈 `RUNNING` | `ERROR` + tier 2 결정 | 모듈 `QUEUED` | 세션 재개설 → 재시도(예산·OTP 안전장치 대상) |
| 모듈 `RUNNING` | `ANOMALY`(`SITE`) | 모듈 `ANOMALY` | 재시도 없음 — 이상징후 인박스 대상 |
| 모듈 재시도 후 최종 통과 | — | 모듈 `PASSED` | `recovered=true`, `recovery_tiers`/`failure_signals` 기록 |
| Run `ERROR` 봉인 | 예약 Run + 자동 재실행 예산 잔여 | 같은 Run `RUNNING`(제자리 재개) | 실패 모듈부터 자동 재실행 큐잉, `auto_rerun_of=run_id` |
| 재시도 진행 중 | Run 실행 시간 상한 초과 | 모듈 `ERROR`(강제 `CompleteStep`) | 남은 재시도 중단 |

### 5.2 WebSocket 이벤트

신규 `event_type` 없음. `recovered`/`recovery_tiers`/`failure_signals` 는 기존 `module_*`/`snapshot` 페이로드의 모듈 필드로 실려 나간다. `RunModuleRecovered`·`RunAutoRerunTriggered` 는 감사용 도메인 이벤트로, `RunEventPublisher` 를 거치지 않고 이벤트 스트림·프로젝션 경로로만 흐른다.

## 6. 데이터 모델 (해당 시)

```text
FailureSignal(StrEnum)  — app/core/enums.py
  TIMEOUT | SELECTOR_MISS | NAVIGATION | SESSION_LOST | DIALOG | SITE | UNKNOWN

RecoveryTier(IntEnum)   — app/core/enums.py
  RETRY_IN_PLACE=0 | RESET_TO_MODULE_ENTRY=1 | REPLAY_FROM_LOGIN=2

RunModule (추가 필드)    — app/core/run_models.py
  recovered: bool = False
  recovery_tiers: list[int] = []
  failure_signals: list[str] = []

RunRecord.auto_rerun_of: str | None  — app/contexts/run/contracts/records.py
  자기 자신의 run_id 를 가리키는 자기 참조 필드(별도 원본 Run 을 가리키지 않는다).
  자동 재실행 연쇄 차단(is_auto_rerun 판정)에만 쓰인다.

ExecutionGateway.recover_session(handle, tier, entry_url) -> bool  — app/execution/gateway.py
  기본 구현 False(미지원). 어댑터가 되감았으면 True.

RunModuleRecovered / RunAutoRerunTriggered  — app/contexts/run/domain/events.py
  감사 이벤트. 기존 17개 이벤트 payload 키 집합과 별개로 기본값 포함 신규 필드만 추가(하위호환).
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP/WS |
| --- | --- | --- |
| tier 1 인데 `entry_url` 미확보 | 되감기 생략, tier 0 폴백으로 재시도 계속 | — |
| `recover_session` 이 예외를 던짐 | 로그만 남기고 tier 0 폴백 | — |
| tier 2 필요한데 `requires_user_input` 모듈 + OTP 중계 미설정 | 되감기 생략(R3) — 실패가 빠르게 확정됨 | — |
| tier 2 예산(`E2E_RECOVERY_TIER2_BUDGET`) 소진 | `RESET_TO_MODULE_ENTRY` 로 강등 | — |
| Run 실행 시간 상한(`E2E_RUN_MAX_DURATION_S`) 초과 | 재시도 중단, `CompleteStep` 강제 | — |
| 자동 재실행 큐잉 중 예외 | 원본 Run 결과·완료 알림 보존, 로그만 기록 | — |
| 자동 재실행 성공 큐잉 | `auto_rerun_pending=true`, 완료 메일은 dedup 스토어로 1건만 발송(R4) | — |
| 매니페스트가 `retryable_on` 에 `ANOMALY` 를 선언 | `SITE` 신호는 여전히 무조건 `CompleteStep`(FR-003) | — |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | `SITE` 신호는 어떤 매니페스트 설정으로도 재시도 대상이 될 수 없다(이중 강제 안전 규칙) |
| NFR-002 | 신규 `RunModule`/이벤트 필드는 전부 기본값을 가져 기존 이벤트 스트림 재생·`test_run_event_codec.py` 하위호환을 깨지 않는다 |
| NFR-003 | `E2E_RUN_MAX_DURATION_S`/`E2E_AUTO_RERUN_ENABLED` 기본값은 각각 무제한/`false` — 도입 자체가 기존 동작을 바꾸지 않는다 |
| NFR-004 | `recover_session` 미구현 어댑터는 기본 `False` — 기존 어댑터 무변경 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | 단위 | `tests/test_run_state_machine.py::test_signal_maps_to_base_tier` | 신호 → 기본 tier 매핑 전수(파라미터화, `SESSION_LOST`→`REPLAY_FROM_LOGIN` 포함) |
| AC-002 | 단위 | `tests/test_run_state_machine.py::test_site_signal_never_retries_even_when_policy_allows` | `retryable_on` 이 `ANOMALY` 를 허용해도 `SITE` 는 재시도 금지 |
| AC-003 | 단위 | `tests/test_run_state_machine.py::test_tier_escalates_when_same_tier_already_attempted` | 같은 tier 반복 실패 시 한 단계 상승 |
| AC-004 | 단위 | `tests/test_run_detail_recovery_badge.py::test_run_detail_shows_recovered_badge` | Run 상세 HTML 에 "자동 복구됨"/`badge--recovered` 노출 |
| AC-005 | 단위 | `tests/test_otp_recovery_guard.py::test_reset_to_module_entry_without_entry_url_skips_rewind` | `entry_url=None` 이면 `RunService._recover_session_for_retry` 가 `gateway.recover_session` 자체를 호출하지 않고 되감기를 생략(제자리 재시도로 폴백) |
| AC-006 | 단위 | `tests/test_auto_rerun_gate.py::test_auto_rerun_queues_and_auto_rerun_of_is_self_referential` | 큐잉 표시(`auto_rerun_pending`)와 `auto_rerun_of` 가 자기 자신(원본) `run_id` 를 가리키는지 애그리거트 수준에서 검증 |
| AC-007 | 단위 | `tests/test_run_state_machine.py::test_tier_two_budget_exhaustion_downgrades_to_tier_one` | tier 2 예산 소진 시 `RESET_TO_MODULE_ENTRY` 로 강등 |
| — | 단위 | `tests/test_run_state_machine.py` | tier 상승 상한(`REPLAY_FROM_LOGIN` 에서 멈춤)·기본 신호 tier 0 하위호환 |
| — | 단위 | `tests/test_run_aggregate.py` | `record_retry`/`record_recovered`(재시도 이력 누적·`RunModuleRecovered` 발행)·`mark_auto_rerun_pending` |
| — | 단위 | `tests/test_recovery_tier_execution.py` | `ExecutionGateway.recover_session` 기본 구현·`CompositeExecutionGateway` 위임 배선 |
| — | 단위 | `tests/test_session_server.py` | tier 1(진입 URL 재이동, `entry_url=None` 시 `SessionServer.recover()` 자체의 no-op 포함)·tier 2(런타임 재구축, 재개설 실패 시 옛 런타임 유지) 워커 동작 |
| — | 단위 | `tests/test_otp_recovery_guard.py` | R3 — OTP 중계 미설정 시 tier 2 되감기 생략 |
| — | 단위 | `tests/test_auto_rerun_gate.py` | `ANOMALY`/수동 실행/연쇄/예산 소진 시 `SkipAutoRerun`, 순수 결정(`TriggerAutoRerun`) |
| 통합 | `tests/integration/test_auto_rerun_wiring.py::test_scheduled_error_run_auto_reruns_in_place_when_enabled` | `RunService` 전체 실행 경로로 자동 재실행·`auto_rerun_of` 를 종단간 검증(traceability 스캔 대상 밖 — `tests/` 최상위가 아님) |
| CI 게이트 | `tests/test_spec_traceability.py` | 본 Spec 의 `@pytest.mark.spec` 마커 ↔ AC 섹션 정합 |
| CI 게이트 | `scripts/check_docs_consistency.py` | env 변수(`E2E_AUTO_RERUN_ENABLED` 등) 문서화 정합 |

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| 실패 신호 분류 | `app/runner/failure_signal.py` |
| 실패 신호·복구 등급 enum | `app/core/enums.py` |
| 복구 등급·자동 재실행 결정 | `app/contexts/run/domain/state_machine.py` |
| 복구 가시성·자동 재실행 상태 변경 | `app/contexts/run/domain/aggregate.py` |
| 감사 이벤트 | `app/contexts/run/domain/events.py`, `app/contexts/run/infrastructure/codec.py` |
| 되감기 호출·자동 재실행 큐잉·시간 상한 | `app/contexts/run/application/service.py` |
| 되감기 포트 | `app/execution/gateway.py` |
| 되감기 워커 실행 | `worker/session_server.py` |
| 되감기 시뮬레이션 더블 | `app/execution/simulated_gateway.py` |
| 설정값 | `app/core/settings.py`(`auto_rerun_enabled`/`run_max_duration_s`/`recovery_tier2_budget`) |
| Run 상세 배지 | `app/web/templates/run.html`, `app/api/routes_dashboard.py` |
| 일간 현황 노출 | `app/contexts/insights/application/daily_dashboard.py` |
| 완료 메일 노출 | `app/notifications/report_renderer.py` |
| 알림 중복 방지 | `app/notifications/infrastructure/sqlite_email_notification_dedup.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-18 | 초안 — Task 1~9(Self-Recovery Loop) 구현을 역작성 | SDD Task 10 |
