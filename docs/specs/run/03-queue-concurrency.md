# SPEC-RUN-003: 실행 큐·동시성

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-RUN-003` |
| **상태** | `approved` |
| **의존** | `SPEC-PLATFORM-003` |
| **구현** | `app/execution/profile_queue.py`, `run_queue.py` |

## 1. JobDescriptor

| 필드 | 값 |
| --- | --- |
| `kind` | `execute` \| `resume` |
| `start_index` | 모듈 인덱스 |
| `execution_profile` | manifest 시스템 수준 |

## 2. 프로필별 큐

`ProfilePartitionedRunQueue` — 프로필당 독립 `RunExecutionQueue`

| Profile | Env | 기본 동시성 | 시스템 |
| --- | --- | --- | --- |
| heavy | `E2E_RUN_CONCURRENCY_HEAVY` | 2 | hom, mhm |
| light | `E2E_RUN_CONCURRENCY_LIGHT` | 4 | (예약) |
| interactive | `E2E_RUN_CONCURRENCY_INTERACTIVE` | 2 | fp, hrp, hwtc, chbot |

`E2E_RUN_CONCURRENCY` — 레거시 fallback (4)

## 3. Remote 모드

`E2E_EXECUTION_MODE=remote` → `RedisJobQueue`, 워커가 `dispatch_run_job` 소비

## 4. OTP 동시성 이점

`WAITING_INPUT` 시 실행 루프 종료 → worker 슬롯 반환. resume은 별도 job.

## 5. 수용 기준

### AC-001: 프로필 격리

```gherkin
Given HEAVY concurrency=2, 3 hom Run 동시 시작
When 3번째 enqueue
Then 3번째는 큐 대기 (2개만 RUNNING)
```

### AC-002: Resume job

```gherkin
Given OTP pause 후 submit_otp
When enqueue
Then kind=resume, start_index=pending.resume_index
```

## 6. Suite 연동

Suite 하위 Run도 동일 큐·프로필 규칙 적용 (`triggered_by=suite`)
