# SPEC-RUN-001: Run 생명주기·상태머신

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-RUN-001` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-PLATFORM-001`, `SPEC-PLATFORM-003` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2 (Run) |
| **구현 위치** | `app/contexts/run/application/service.py`, `app/contexts/run/application/planner.py`, `app/contexts/run/domain/` |

## 1. 개요

### 1.1 목적

Run 생성·모듈 루프·상태머신·종료 분류를 정의한다. `RunService`는 순수 도메인 결정을 I/O로 해석한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | Run 시작·조회 |
| `system` | JobQueue·ExecutionGateway·Outbox |

### 1.3 범위

**In scope:**

- Run/Module 상태·시작·실행 루프·종료 분류·목록 API

**Out of scope:**

- OTP·취소·재실행 (`SPEC-RUN-002`)
- 큐 동시성 (`SPEC-RUN-003`)

## 2. 기능 요구사항 (FR)

### FR-001: Run 시작

**API:** `POST /api/runs/systems/{system_code}`

1. `RunPlanner.prepare()` — 입력 정제, `selected_module_ids`, `auth_method` 검증
2. `run_id = run_{YYYYMMDD_HHMMSS}_{6hex}`
3. PII → `RunInputStorePort`
4. `RunAggregate.for_new_run()` → `RunCreated`
5. Job enqueue (`kind=execute`, `start_index=0`)

**모듈 선택:**

- `selected_module_ids=null` → 전체
- 미선택 → `SKIPPED`
- `depends_on` 미충족 조합 → `400`

**auth_method:** manifest `supported_auth_methods` 외 거부

### FR-002: 실행 루프

```
decide_module_entry → ExecuteModule | BlockModule | CancelRemaining
QUEUED (0.6s) → RUNNING
gateway.run_step (retry loop)
decide_post_step / decide_post_step_failure
finalize (unless paused)
```

| decide_module_entry | 조건 → 결정 |
| --- | --- |
| cancel | `CancelRemaining` |
| !deps | `BlockModule` |
| else | `ExecuteModule` |

`dependencies_satisfied` = 모든 `depends_on` 모듈 `PASSED`

### FR-003: 종료 분류

| Terminal | 의미 | 통계 |
| --- | --- | --- |
| `PASSED` | 정상 | 포함 |
| `ANOMALY` | `RuntimeError` | 포함 |
| `ERROR` | 도구 실패 | 제외 |
| `CANCELLED` | 취소·봉인 | 제외 |

**최종 우선순위:** `ERROR > ANOMALY > PASSED`. `FAILED` 레거시 → ANOMALY.

### FR-004: Module Status

`QUEUED`, `BLOCKED`, `SKIPPED`, `CANCELLED` (Run status 외 추가)

## 3. 수용 기준 (AC)

### AC-001: 의존성 차단

```gherkin
Given hom.contract.list 선택, hom.login 미선택
And hom.login not PASSED
When Run 시작
Then hom.contract.list status=BLOCKED
```

### AC-002: 비정책 OTP

```gherkin
Given requires_user_input=false 모듈
When adapter가 WAITING_INPUT 반환
Then module status=ERROR (RejectUnexpectedInput)
```

### AC-003: 검증 API

```gherkin
Given schedule/preset/suite 등록
When validate_run_request 호출
Then start_run 과 동일 검증 (400 동일 조건)
```

## 4. API 계약 (해당 시)

| Method | Path | Auth | Request | Response | 오류 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/runs?scope=today\|before_today` | JWT | — | Run 목록 | 401 |
| POST | `/api/runs/systems/{system_code}` | JWT | run_form JSON | RunView | 400/403 |
| GET | `/api/runs/{run_id}` | JWT | — | RunView | 404 |
| GET | `/api/runs/{run_id}/nodes` | JWT | — | 모듈 노드 | 404 |

## 5. 상태·이벤트 (해당 시)

### 5.1 Run Status 전이

`PENDING` → `RUNNING` → (`WAITING_INPUT`) → terminal (`PASSED`|`ANOMALY`|`ERROR`|`CANCELLED`)

## 6. 데이터 모델 (해당 시)

```text
Run / RunModule — app/core/run_models.py
RunAggregate — app/contexts/run/domain/aggregate.py
RunStateMachine — app/contexts/run/domain/state_machine.py
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP |
| --- | --- | --- |
| 잘못된 auth_method | 400 | 400 |
| system_code 스코프 밖 | 403 | 403 |
| cancel_requested | `CancelRemaining` | — |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | 상태 변이는 `RunAggregate`만 수행 (AG-008) |
| NFR-002 | REST 응답은 `RunView.dump` (AG-005) |
| NFR-003 | PII는 InputStore만 — REST/WS 미포함 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | 단위 | `tests/test_run_state_machine.py` | `decide_module_entry` → BlockModule |
| AC-002 | 단위 | `tests/test_run_state_machine.py` | `RejectUnexpectedInput` |
| AC-003 | 단위 | `tests/test_preset_service.py` | validate_run_request |
| — | 단위 | `tests/test_run_aggregate.py` | aggregate 변이·불변식 |
| — | 단위 | `tests/test_run_decider.py` | decide/evolve/rebuild |
| — | 단위 | `tests/test_run_list_scope.py` | 목록 스코프 |

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| RunService | `app/contexts/run/application/service.py` |
| RunPlanner | `app/contexts/run/application/planner.py` |
| State machine | `app/contexts/run/domain/state_machine.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 | SDD 보강 |
