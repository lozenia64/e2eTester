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
| `/suites/{suite_id}` | 넌스크롤 수직 파이프라인 — 진행 중 스텝만 자동 전개, 상단 진도 블록(경과·ETA), 스텝별 실측/평균 소요시간, 하위 Run 링크, OTP 패널 |

**WS:** Run 상세는 `app.js`. 수트 상세는 `app/web/frontend/suite/` (엔트리 `entries/suite.ts`) — 수트 이벤트 WS + 현재 하위 Run 진행 WS 두 개.

**수트 상세 구조(Cycle 2):**
- 셸: `body:has(.suite)` 넌스크롤(공통 `shell.css`). 내부 스크롤은 스텝 목록 하나뿐.
- 자동 펼침: `SuiteView.expanded_step_order`(서버 파생) 를 그대로 반영. 클라이언트는 규칙을 재구현하지 않는다. 행 클릭은 Run 상세 이동(펼침 아님).
- ETA: `RunSummaryQueryPort.avg_duration_ms_by_system` 의 `PASSED` Run 평균을 baseline 으로 라우트가 1회 주입(`step_baselines`), 산술은 클라이언트가 소켓 이벤트마다. `WAITING_INPUT` 에서 정지.
- 도메인 모델·이벤트 wire 불변(설계 D9).

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

### AC-003: 수트 상세 자동 펼침

```gherkin
Given 실행 중인 suite
When 진행 중 스텝이 바뀐다
Then 펼쳐진 스텝이 서버의 expanded_step_order 와 일치한다
And 수동 펼침 경로는 존재하지 않는다
```

### AC-004: 수트 상세 넌스크롤

```gherkin
Given 시스템 6개 suite 가 OTP 입력 대기
When 1366x768 에서 렌더한다
Then body 세로 스크롤이 0 이다
And 펼쳐진 스텝의 모듈 진행이 뷰포트 안에 있다
```

## 6. 스크립트

- `app.js` — run 상세·Run 이력·예약 오버뷰 (수트 몫은 Cycle 2 에서 이관)
- `entries/suite.ts` + `app/web/frontend/suite/` — 수트 상세
- `admin-dashboard.js`, `admin-runs.js`, `admin-ops.js`, `admin-stats.js`
