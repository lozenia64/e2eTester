# SPEC-SCHED-003: 모바일 즉시 점검

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SCHED-003` |
| **상태** | `approved` |
| **의존** | `SPEC-SCHED-001`, `SPEC-RUN-002` |
| **구현** | `app/api/routes_trigger.py`, `mobile_trigger.html` |

## 1. 개요

스케줄별 secret `trigger_token`으로 JWT 없이 모바일에서 즉시 점검.

## 2. FR-001: 페이지

`GET /m/{trigger_token}` — side-effect free (prefetch 안전)

## 3. FR-002: 트리거

`POST /api/trigger/{trigger_token}`

- `run-now`와 동일 동작
- **Idempotency:** 이전 run/suite still active → 새로 안 만들고 attach
- 토큰 불일치 → uniform `404` (`hmac.compare_digest`)
- 스케줄 삭제 → URL revoke

## 4. FR-003: 상태·OTP

| API | 용도 |
| --- | --- |
| GET `/api/trigger/{token}/status` | polling (`execution_id`, OTP 대기 시 `otp_run_id`·`otp_request_id` 포함) |
| POST `/api/trigger/{token}/otp` | phone auth resume (Run 서비스가 대기 컨텍스트를 재검사해 다른 실행·인증 단계로 전달 차단) |

## 5. 토큰

- 생성: schedule create
- 레거시: `list_schedules` 시 lazy backfill

## 6. 수용 기준

### AC-001: 이중 실행 방지

```gherkin
Given trigger fires run still RUNNING
When POST trigger again
Then same run_id returned
And no duplicate run
```

### AC-002: 토큰 타이밍

```gherkin
Given wrong token
When POST /api/trigger/{token}
Then 404 (same as nonexistent)
```

## 7. 보안

- constant-time compare
- JWT 불필요 (모바일 링크 공유)
