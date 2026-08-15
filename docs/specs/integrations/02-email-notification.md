# SPEC-INT-002: 완료 이메일 알림

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INT-002` |
| **상태** | `approved` |
| **구현** | `email_notification.py`, `run_completion_email.py` |

## 1. 개요

Run/Suite 종료 시 Gmail SMTP 알림. **기본 비활성** — env 미설정 시 no-op.

## 2. FR-001: 구독

`EmailNotificationSubscriber` on `EventBus`:
- `RunFinished` (suite_id 없을 때)
- `SuiteFinished` (통합 1통)

## 3. FR-002: Env

`docs/INSTALL.md`, `.env.example` 참조 (Gmail app password 등)

## 4. FR-003: Dedup

`SqliteEmailNotificationDedup` — 중복 발송 방지

## 5. 수용 기준

### AC-001: 비활성 시 동작

```gherkin
Given email env unset
When Run finishes
Then app continues, no SMTP attempt
```

### AC-002: Suite 억제

```gherkin
Given run with suite_id
When RunFinished
Then per-run email suppressed
And SuiteFinished sends one email
```
