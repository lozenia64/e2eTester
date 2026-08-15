# SPEC-UI-003: Run/Suite 상세·이력·관리자

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-003` |
| **상태** | `approved` |
| **의존** | `SPEC-PLATFORM-004`, `SPEC-INSIGHT-003` |

## 1. Run/Suite 상세

| Path | 설명 |
| --- | --- |
| `/runs/{run_id}` | Run 상세, 모듈 노드, 로그, OTP 패널, WS |
| `/suites/{suite_id}` | Suite 단계, 하위 run 링크, OTP |

**WS:** 실시간 상태·로그 (`app.js`)

## 2. Run 이력

`GET /runs/history` — `scope=before_today` Run 목록

## 3. 관리자

| Path | API | 기능 |
| --- | --- | --- |
| `/admin` | `/api/admin/dashboard` | 7일×3-slot coverage heatmap |
| `/admin/runs` | `/api/admin/runs`, board, heatmap, export.csv | 전체 Run 이력 |
| `/admin/ops` | `/api/admin/ops/snapshot` | 큐·스케줄 스냅샷 |
| `/admin/stats` | `/api/admin/stats/usage`, savings/csv | 사용량·절감 |
| `/admin/modules` | `/api/admin/module-settings` | 모듈 수동 업무 시간 |

`DELETE /api/admin/runs/{run_id}` — Run 삭제 (admin)

## 4. 기타 페이지

| Path | Spec |
| --- | --- |
| `/presets` | SPEC-PRESET-001 |
| `/schedules` | SPEC-SCHED-002 |
| `/anomalies` | SPEC-INSIGHT-001 |
| `/insights`, `/systems/{code}/insights` | SPEC-INSIGHT-002 |
| `/self-healing` | SPEC-HEAL-001 |

## 5. 수용 기준

### AC-001: OTP 패널

```gherkin
Given run_waiting_input WS event
When UI renders
Then OTP input visible
And POST /api/runs/{id}/otp on submit
```

### AC-002: admin heatmap

```gherkin
Given admin
When GET /api/admin/dashboard
Then 7-day coverage matrix returned
```

## 6. 스크립트

- `app.js` — run/suite
- `admin-dashboard.js`, `admin-runs.js`, `admin-ops.js`, `admin-stats.js`
