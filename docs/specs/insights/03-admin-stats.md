# SPEC-INSIGHT-003: 관리자 통계·커버리지

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INSIGHT-003` |
| **상태** | `approved` |
| **의존** | `SPEC-IDENTITY-003` |
| **구현** | `stats_service.py`, `admin_coverage_dashboard.py` |

## 1. 관제 대시보드

`GET /api/admin/dashboard` — 7일×3-slot (주간/저녁/야간) coverage heatmap

`/admin`은 성과 보고형 대시보드다. 월간 추정 절감 시간·누적 추이·시스템별 기여도를 중심으로 오늘의 모듈 결과와 커버리지를 함께 제공한다.

`GET /api/admin/dashboard/performance` — 관리자 전용 월간 성과 읽기 모델.

- `Asia/Seoul` 기준 월초부터 조회 시각까지, 실행 요청일(`requested_at`)로 귀속한다.
- 기존 통계와 동일하게 통계 대상 완료 Run의 PASSED 모듈 기준 초만 합산한다. 모듈 설정 override를 공유하며 ERROR/CANCELLED Run은 제외한다.
- 전월 동기간과 비교한다. 해당 일자가 없는 짧은 전월은 월말까지 비교하고, 전월 합계 0이면 비교율은 null이다.
- `total_seconds`, `previous_seconds`, `change_percent`, `total_runs`, `by_system`, `daily`, `period`, `generated_at`, `timezone`, `basis_note`를 제공한다. 개인별 통계·차트 figure는 포함하지 않는다.
- 일별 누적은 오늘까지이며 실행이 없는 날은 직전 누적을 유지한다. 누적 마지막 값·시스템별 합계·전체 합계는 초 단위로 일치한다.
- 기준 시간이 변경되면 과거 추정치도 현재 기준으로 재계산한다. 기준 초가 0이면 합계에 기여하지 않는다.
- 통과율은 오늘 전체 모듈을 분모로 한다. 오늘 확인할 모듈 수는 당일 anomaly+error이며 7일 슬롯 수와 혼용하지 않는다.
- 첫 성공 조회에 숫자·선·막대 연출을 한 번 적용하며, 30초 갱신은 변경 데이터만 반영한다. 동작 줄이기 설정은 모션을 생략한다.
- 성과·일간·커버리지는 독립 갱신한다. 실패 시 마지막 성공 데이터를 보존하고 실패와 정상 0 실적을 구분한다. 숨김 탭에서는 폴링을 쉬고 복귀 시 갱신한다.
- 일별 데이터 표와 산정 기준, 실제 실행 결과 링크를 제공한다. 모바일에서는 본문 세로 스크롤과 히트맵 내부 가로 스크롤을 허용한다.

## 2. Run 보드

| API | 용도 |
| --- | --- |
| GET `/api/admin/runs/board` | 이번 달 시스템 지도 (`system_map`, `today_start`) |
| GET `/api/admin/runs/heatmap` | 시간대 heatmap |
| GET `/api/admin/runs` | paginated list |
| GET `/api/admin/runs/export.csv` | CSV export |

`/api/admin/runs/board` 의 `system_map` — `/admin/runs` 상단 트리맵:

- 기간은 `Asia/Seoul` 월초 00:00부터 조회 시각까지, `requested_at` 귀속. `period.from`/`to` 는 UTC ISO.
- 실행 횟수는 정상·이상징후 Run(`ADMIN_VISIBLE_RUN_STATUSES`), 이상징후는 ANOMALY+FAILED. 점검실패·취소는 일일 보존 정리로 사라져 제외한다.
- `systems[]` 는 `system_code` 단위(`system_name` 은 기간 내 최신 행), `runs` 내림차순·동률 코드 오름차순. 실행 0회 시스템은 없다.
- `top_runs`/`top_anomaly` 는 최댓값 시스템 코드(동률 코드 오름차순). 값이 전부 0이면 `null`.
- 대시보드와 겹치는 KPI·7일 추이·주의 Run·시스템별 최근 결과는 이 화면에 두지 않는다(`/admin` 참조).

## 3. 사용량 통계

`GET /api/admin/stats/usage` — `StatsQueryPort`

- 사용자별·시스템별 Run 수
- 정상·이상징후 완료 실행 집계 (ERROR/CANCELLED admin stats 제외)

`GET /api/admin/stats/savings/csv` — `estimated_manual_seconds` 기반 절감

## 4. 모듈 설정

`GET/PUT /api/admin/module-settings` — 모듈별 수동 업무 시간 (`ModuleSettingsRepositoryPort`)

## 5. Ops

`GET /api/admin/ops/snapshot` — Run/Suite/스케줄·큐 운영 스냅샷 (`OpsService`, `ops_buffer`)

## 6. 수용 기준

### AC-001: ERROR 통계 제외

```gherkin
Given runs with ERROR outcome
When stats usage
Then ERROR runs excluded from success rate denominator per policy
```

### AC-002: admin only

```gherkin
Given user role
When GET /api/admin/stats/usage
Then 403
```

### AC-003: 월간 성과 정합성

동일 기간과 기준 시간 설정에서 월간 성과 합계는 기존 사용량 통계의 시스템별 절감 초 합계와 일치한다. 일별 누적의 마지막 값과 시스템별 기여 합계도 일치한다. 한국 자정·연도 경계·윤년·짧은 전월·전월 0·기준 초 override를 검증한다.

### AC-004: 성과 화면 갱신과 접근성

일부 API가 실패해도 성공한 영역은 표시하며 실패 영역의 마지막 성공 수치를 보존한다. 중복 조회를 만들지 않고 최초 모션을 반복하지 않는다. 커버리지 갱신 후 동일 링크의 키보드 포커스를 유지한다. 동작 감소·차트 대체 표·모바일 가로 넘침을 검증한다.
