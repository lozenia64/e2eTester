# SPEC-INSIGHT-003: 관리자 통계·커버리지

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INSIGHT-003` |
| **상태** | `approved` |
| **의존** | `SPEC-IDENTITY-003` |
| **구현** | `stats_service.py`, `admin_coverage_dashboard.py` |

## 1. 관제 대시보드

`GET /api/admin/dashboard` — 7일×3-slot (아침/점심/저녁) coverage heatmap

## 2. Run 보드

| API | 용도 |
| --- | --- |
| GET `/api/admin/runs/board` | Kanban 유사 보드 |
| GET `/api/admin/runs/heatmap` | 시간대 heatmap |
| GET `/api/admin/runs` | paginated list |
| GET `/api/admin/runs/export.csv` | CSV export |

## 3. 사용량 통계

`GET /api/admin/stats/usage` — `StatsQueryPort`

- 사용자별·시스템별 Run 수
- ANOMALY/ERROR/PASSED 집계 (ERROR/CANCELLED admin stats 제외)

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
