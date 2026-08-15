# SPEC-SCHED-002: 예약 점검 관리 센터

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SCHED-002` |
| **상태** | `approved` |
| **의존** | `SPEC-SCHED-001` |
| **구현** | `app/contexts/scheduling/schedule_center.py`, `app/web/static/schedules.js` |

## 1. UI

`GET /schedules` → `schedules.html` (사이드바 "예약 관리")

## 2. API

### FR-001: 관제 보드

`GET /api/schedules/board`

- KPI strip
- 문제 분류: stuck / failing / missed / stale
- `missed` = overlap-skip 슬롯

### FR-002: 주간 캘린더

`GET /api/schedules/calendar`

- croniter 확장 vs 실제 schedule-tagged runs/suites
- missed 슬롯 해칭
- per-system 24h 커버리지
- same-slot clustering 경고

### FR-003: 스케줄 상세

| API | 내용 |
| --- | --- |
| GET `/api/schedules/{id}` | detail + change_log |
| GET `.../history` | 최근 30 dot strip, success rate, avg duration, streak |
| PUT `/api/schedules/{id}` | in-place edit; `input_data`는 non-empty key만 merge (PII 미반환) |
| POST `.../pause-until` | 임시 pause, 다음 tick 자동 resume |
| POST `.../duplicate` | disabled 복사본 |

## 3. 순수 빌더

규칙은 `schedule_center.py` — issue 분류, cron→한글 라벨, occurrence matching.

`SchedulerService`는 thin I/O interpreter.

## 4. 수용 기준

### AC-001: PII 미반환

```gherkin
Given schedule with phone_number in input_data
When GET /api/schedules/{id}
Then phone_number not in response
```

### AC-002: edit merge

```gherkin
Given stored input {name, phone}
When PUT with input_data {name: "new"} only
Then phone preserved in store, name updated
```

## 5. 테스트

`tests/test_schedule_center.py`
