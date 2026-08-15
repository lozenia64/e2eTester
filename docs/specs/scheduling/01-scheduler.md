# SPEC-SCHED-001: 스케줄러·Cron

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SCHED-001` |
| **상태** | `approved` |
| **구현** | `app/contexts/scheduling/scheduler.py`, `cron.py` |

## 1. 개요

5-field cron 기반 자동 Run/Suite 트리거. `SchedulerService`가 lifespan에서 백그라운드 루프.

## 2. FR-001: 스케줄 생성

| API | 대상 |
| --- | --- |
| `POST /api/schedules/systems/{system_code}` | 단일 시스템 Run |
| `POST /api/schedules/suites` | Suite (`selected_system_codes` 지원) |

생성 시 `validate_run_request` / `validate_suite_request` 동일 검증.

**태그:** `triggered_by=schedule`, `schedule_id`

## 3. FR-002: Cron

- `croniter` 기반 parse/validate
- `E2E_SCHEDULE_TZ` 타임존 (KST 기본)
- DST 처리
- `next_run_at` 계산

## 4. FR-003: 틱 동작

due schedule → Run/Suite 생성. 이전 실행 active 시 overlap-skip (`last_skipped_at` 기록).

재기동 시 과거 due는 catch-up 안 함 — 다음 cron 슬롯으로 재계산.

## 5. FR-004: CRUD

| Method | Path |
| --- | --- |
| GET | `/api/schedules` |
| GET/PUT | `/api/schedules/{id}` |
| POST | `/api/schedules/{id}/toggle` |
| POST | `/api/schedules/{id}/run-now` |
| POST | `/api/schedules/{id}/pause-until` |
| POST | `/api/schedules/{id}/duplicate` |
| DELETE | `/api/schedules/{id}` |

## 6. FR-005: 보존

`run_retention` — ERROR/CANCELLED 일일 purge (ANOMALY 유지)

## 7. 수용 기준

### AC-001: 검증 동기화

```gherkin
Given invalid auth_method for hom
When POST schedule for hom
Then 400 (same as manual run)
```

### AC-002: overlap skip

```gherkin
Given schedule due, previous run still RUNNING
When tick
Then no new run
And last_skipped_at updated
```

## 8. persistence

`SqliteScheduleRepository` — JSON blob, `trigger_token` per schedule
