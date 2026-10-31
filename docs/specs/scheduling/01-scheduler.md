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

## 9. FR-006: 최신 인증 프리셋 참조

단일 예약은 `preset_id`, 수트 예약은 시스템별 `preset_ids`를 저장한다. 실행 시작 시 예약
생성자 소유의 최신 프리셋을 읽는다. 예약 모듈·시스템·브라우저 설정과 실행 중 입력은 유지한다.
연결된 프리셋을 삭제하면 예전 값으로 회귀하지 않고 `preparation_error`를 표시한다.
자동 실행 실패는 다음 cron 슬롯으로 넘기며 다른 예약을 차단하지 않는다.

기존 예약은 기동 시와 실행 준비 시 소유자·시스템·기존 인증값 전체가 일치하는 후보가 유일할 때 자동 연결한다(새 프리셋 필드 추가는 허용).
모호하거나 불일치하는 예약은 저장값 호환 모드로 유지하고 편집에서 직접 연결한다.
상세 응답은 인증값 없이 `preset_bindings`(연결 상태·이름)와 `preset_options`(예약 소유자 후보의 ID·시스템·이름)를 제공한다.
관리자 대리 실행도 원래 소유자 기준으로 조회하며, 다른 소유자로 참조 예약을 복제하지 못한다. 프리셋 참조와 직접 인증값을 함께 받지 않는다.

### AC-003: 다음 실행에 수정값 반영

```gherkin
Given a schedule bound to its owner's preset
When the preset gains a manager_employee_id or its authentication values change
Then the next scheduled, immediate or mobile execution uses the updated preset
And already started executions keep their captured inputs
```

### AC-004: 기존 예약 전환과 참조 오류

```gherkin
Given an existing schedule with copied authentication inputs
When exactly one preset of the same owner and system matches every stored authentication value
Then persist its preset reference and discard the copied authentication values
And otherwise keep legacy inputs until a user selects a preset in schedule edit
When a bound preset becomes unavailable
Then block execution and show a reconnection error without falling back
```
