# SPEC-RUN-004: 세션 체크포인트·재기동 복구

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-RUN-004` |
| **상태** | `approved` |
| **의존** | `SPEC-RUN-002`, `SPEC-PLATFORM-003` |
| **구현** | `app/contexts/run/infrastructure/sqlite_session_checkpoint_store.py` |

## 1. 개요

Playwright `storage_state`를 모듈 경계·OTP pause 시 캡처. 프로세스 재기동 후 복구.

## 2. FR-001: 캡처 시점

- OTP pause (`_pause_for_input`)
- 모듈 경계 (checkpoint-capable adapter만; local in-process = no-op)

## 3. FR-002: reconcile_interrupted_runs

| 시나리오 | 동작 |
| --- | --- |
| WAITING_INPUT + Redis heartbeat | 봉인 스킵 |
| checkpoint + WAITING_INPUT | pause 유지, submit_otp로 재개 |
| checkpoint + 기타 active | `kind=resume`, `start_index=checkpoint+1` enqueue |
| checkpoint 없음 | `seal_interrupted()` → CANCELLED |

## 4. FR-003: 복원 경로

`open_session(..., storage_state)` → cookie 재주입 → `start_index`부터 실행

`decide_rehydration`:
- cookies 유효 → `ResumeFromCheckpoint`
- 무효 → `ReplayFromLogin` (login 모듈부터)

## 5. 제한

- in-process local 모드: checkpoint 없음 → 재기동 시 항상 CANCELLED
- cross-restart OTP: 워커 out-of-process 수동 검증 게이트

## 6. 수용 기준

### AC-001: 체크포인트 없는 봉인

```gherkin
Given RUNNING Run, checkpoint 없음
When API 재기동
Then Run status=CANCELLED
```

### AC-002: storage_state 복원

```gherkin
Given checkpoint with valid cookies
When resume job 실행
Then open_session에 storage_state 전달
And login 모듈 스킵 가능
```

## 7. 테스트

`tests/test_run_state_machine.py` — `decide_rehydration`
