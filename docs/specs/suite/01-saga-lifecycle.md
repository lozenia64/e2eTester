# SPEC-SUITE-001: Suite 사가 생명주기

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SUITE-001` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-RUN-001`, `SPEC-RUN-002` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2 (Suite) |
| **구현 위치** | `app/contexts/suite/application/service.py`, `app/contexts/suite/domain/` |

## 1. 개요

### 1.1 목적

등록된 시스템을 `display_order` 순으로 순차 Run 실행하는 **이벤트 기반 사가**를 정의한다. 폴링·WS 구독 없음.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | Suite 시작·취소·OTP |
| `system` | EventBus·RunCommandPort·SuiteControlStore |

### 1.3 범위

**In scope:**

- Suite 시작·사가 루프·취소·OTP 미러링·재기동 봉인·통합 이메일

**Out of scope:**

- 개별 Run 실행 루프 (`SPEC-RUN-001`)
- Suite rerun API (없음 — 새 Suite 시작)

## 2. 기능 요구사항 (FR)

### FR-001: Suite 시작

**API:** `POST /api/suites`

Body: `browser_mode`, `systems`, `selected_system_codes`, `scope_system_codes`

1. 선택 시스템 `validate_run_request`
2. PII → `SuiteInputStorePort`
3. `SuiteAggregate.for_new_suite()` → `SuiteCreated`
4. `_advance()` → `SuiteStarted` + 첫 PENDING step Run 시작

### FR-002: 사가 루프

```
_advance → decide_advance → StartStep | FinalizeSuite | CancelSuite
on_run_finished → record_step_result → _advance
on_run_waiting_input / on_run_resumed → suite 상태 미러링
```

**직렬화:** `suite_id`별 `asyncio.Lock`

### FR-003: 상태머신

| decide_after_run_finished | Run CANCELLED ∨ cancel → RecordAndCancel, else RecordAndAdvance |
| decide_advance | cancel → CancelSuite; no pending → FinalizeSuite; else StartStep |

Run → Step: PASSED→PASSED, CANCELLED→CANCELLED, ERROR→ERROR, ANOMALY/FAILED→ANOMALY

### FR-004: 취소·OTP·재기동

- Cancel: `POST /api/suites/{suite_id}/cancel` → control store + active run cancel
- OTP: `POST /api/suites/{suite_id}/otp` → `submit_otp` 위임
- Reconcile: active suite → CANCELLED 봉인 (checkpoint 없음)
- Email: Suite 완료 1통; `suite_id` Run 개별 메일 억제

## 3. 수용 기준 (AC)

### AC-001: 순차 실행

```gherkin
Given Suite with hom, mhm selected
When hom Run finishes PASSED
Then mhm Run starts automatically
```

### AC-002: 실패 후 진행

```gherkin
Given hom Run finishes ANOMALY
When on_run_finished
Then mhm step still starts (unless cancel)
```

### AC-003: OTP 미러링

```gherkin
Given child run WAITING_INPUT
When on_run_waiting_input
Then suite status=WAITING_INPUT
And awaiting_input_run_id set
```

## 4. API 계약 (해당 시)

| Method | Path | Auth | Response | 오류 |
| --- | --- | --- | --- | --- |
| GET | `/api/suites` | JWT | Suite 목록 | 401 |
| POST | `/api/suites` | JWT | SuiteView | 400 |
| GET | `/api/suites/{suite_id}` | JWT | SuiteView | 404 |
| POST | `/api/suites/{suite_id}/cancel` | JWT | SuiteView | 400 |
| POST | `/api/suites/{suite_id}/otp` | JWT | SuiteView | 400 |
| WS | `/ws/suites/{suite_id}` | JWT 쿠키 | SuiteEvent | close 1008 |

## 5. 상태·이벤트 (해당 시)

### 5.2 Suite 도메인 이벤트

`SuiteCreated`, `SuiteStarted`, `SuiteFinished`, step linked/finished, `SuiteWaitingInput`, `SuiteResumed`

## 6. 데이터 모델 (해당 시)

```text
SuiteRun / SuiteStep — app/core/suite_models.py
SuiteAggregate — app/contexts/suite/domain/aggregate.py
RunCommandPort — app/contexts/scheduling/command_port.py (SuiteService 주입)
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 |
| --- | --- |
| cancel_requested during advance | CancelSuite |
| child run CANCELLED | RecordAndCancel |
| 프로세스 재기동 | reconcile → CANCELLED |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | SuiteService는 RunService에 직접 의존하지 않음 — `RunCommandPort` |
| NFR-002 | REST/WS는 `SuiteView.dump` |
| NFR-003 | Suite 입력 PII는 SuiteInputStore |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | 단위 | `tests/test_suite_state_machine.py` | `decide_advance` → StartStep |
| AC-002 | 단위 | `tests/test_suite_state_machine.py` | ANOMALY 후 RecordAndAdvance |
| AC-003 | 단위 | `tests/test_suite_aggregate.py` | waiting_input·awaiting run |
| — | 단위 | `tests/test_suite_decider.py` | decide/evolve |
| — | 단위 | `tests/test_suite_control_store.py` | cancel intent 영속 |
| — | 단위 | `tests/test_suite_browser_mode.py` | browser_mode 병합 |

**수동:** 라이브 Suite 순차 실행·OTP (`/suites/{id}`).

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| SuiteService | `app/contexts/suite/application/service.py` |
| State machine | `app/contexts/suite/domain/state_machine.py` |
| SuiteView | `app/contexts/suite/views/view.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 | SDD 보강 |
