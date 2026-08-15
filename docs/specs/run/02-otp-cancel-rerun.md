# SPEC-RUN-002: OTP·취소·재실행

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-RUN-002` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-RUN-001` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2 |
| **구현 위치** | `app/contexts/run/application/service.py`, `app/api/routes_runs.py`, `app/api/routes_otp.py` |

## 1. 개요

### 1.1 목적

OTP 일시정지·재개, Run 취소, 전체/부분 재실행, 외부 OTP 중계 위임을 정의한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | OTP 입력·취소·재실행 |
| `external` | SMS OTP relay (`SPEC-INT-001`) |
| `system` | ControlStore·checkpoint·JobQueue |

### 1.3 범위

**In scope:**

- Pause/Resume·cancel·rerun·Suite/Trigger OTP 위임·SMS inbound

**Out of scope:**

- Suite 사가 (`SPEC-SUITE-001`)
- 체크포인트 상세 (`SPEC-RUN-004`)

## 2. 기능 요구사항 (FR)

### FR-001: OTP Pause

manifest `requires_user_input: true` 모듈만 합법적 pause.

1. Run/module `WAITING_INPUT`
2. `RunControlStorePort.set_pending(...)`
3. `save_checkpoint()` — storage_state
4. 실행 루프 종료 (in-process 세션 유지)
5. WS `run_waiting_input`

### FR-002: OTP Resume

**API:** `POST /api/runs/{run_id}/otp` body `{otp_code}`

1. pending 로드 → `gateway.submit_input` (OTP 미저장)
2. `resume_after_input()` → RUNNING
3. `enqueue(kind=resume, start_index=pending.resume_index)`

### FR-003: OTP 위임

| API | 동작 |
| --- | --- |
| `POST /api/suites/{suite_id}/otp` | active run에 위임 |
| `POST /api/trigger/{token}/otp` | 스케줄 연결 run에 위임 |
| `POST /api/otp/inbound` | SMS relay — 최신 WAITING_INPUT run |

### FR-004: 취소

**API:** `POST /api/runs/{run_id}/cancel`

| 상태 | 동작 |
| --- | --- |
| terminal | `400` |
| WAITING_INPUT + pending | 즉시 CANCELLED, 세션 close |
| RUNNING/PENDING | cooperative — 모듈 경계까지 |

### FR-005: 재실행

- 전체: `POST /api/runs/{run_id}/rerun` → 새 `run_id`
- 부분: `POST /api/runs/{run_id}/rerun?from_module={module_id}` — `partial_rerun_allowed` + `decide_partial_rerun`

## 3. 수용 기준 (AC)

### AC-001: OTP 워커 해제

```gherkin
Given WAITING_INPUT
When pause 완료
Then execution worker slot 해제
And resume 시 새 job enqueue
```

### AC-002: 부분재실행 거부

```gherkin
Given hom.login partial_rerun_allowed=false
When rerun?from_module=hom.login
Then 400
```

### AC-003: 취소 연쇄

```gherkin
Given RUNNING Run
When cancel
Then 미완료 모듈 CANCELLED
And Run status=CANCELLED
```

## 4. API 계약 (해당 시)

| Method | Path | Auth | Request | Response | 오류 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/runs/{run_id}/otp` | JWT | `{otp_code}` | RunView | 400 |
| POST | `/api/runs/{run_id}/cancel` | JWT | — | RunView | 400 |
| POST | `/api/runs/{run_id}/rerun` | JWT | `?from_module=` | RunView | 400 |
| POST | `/api/otp/inbound` | relay token | SMS payload | ok | 401/404 |

## 5. 상태·이벤트 (해당 시)

### 5.1 WS

`run_waiting_input`, `run_resumed`, `module_waiting_input` — `SPEC-PLATFORM-004`

## 6. 데이터 모델 (해당 시)

```text
PendingOtpState — RunControlStorePort
Session checkpoint — SessionCheckpointStorePort
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP |
| --- | --- | --- |
| OTP 대기 Run 없음 (inbound) | no-op/에러 | 404 |
| 다중 WAITING_INPUT (inbound) | `paused_at` 최신 1건 | — |
| terminal Run cancel | 400 | 400 |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | OTP 코드는 영속 저장 금지 |
| NFR-002 | WAITING_INPUT 시 worker 슬롯 반환 |
| NFR-003 | cancel_requested는 ControlStore 영속 |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | 단위 | `tests/test_run_queue.py` | resume job enqueue |
| AC-002 | 단위 | `tests/test_run_state_machine.py` | `decide_partial_rerun` 거부 |
| AC-003 | 단위 | `tests/test_run_aggregate.py` | cancel·CANCELLED 모듈 |
| — | 단위 | `tests/test_otp_inbound.py` | inbound 라우팅·추출 |
| — | 통합 | `tests/test_run_checkpoint_integration.py` | OTP·checkpoint 연동 |
| — | 단위 | `tests/test_session_checkpoint.py` | rehydration |

**수동:** 라이브 OTP·cross-restart resume (워커 프로세스).

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| RunService OTP | `app/contexts/run/application/service.py` |
| OTP routes | `app/api/routes_otp.py` |
| Run routes | `app/api/routes_runs.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 | SDD 보강 |
