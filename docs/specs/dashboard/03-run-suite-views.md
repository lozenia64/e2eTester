# SPEC-UI-003: Run/Suite 상세·이력·관리자

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-003` |
| **상태** | `approved` |
| **의존** | `SPEC-PLATFORM-004`, `SPEC-INSIGHT-003` |

## 1. Run/Suite 상세

| Path | 설명 |
| --- | --- |
| `/runs/{run_id}` | 넌스크롤 2열 Run 상세 — 모듈 관제, 실패 분석, 로그, OTP 패널, WS |
| `/suites/{suite_id}` | 넌스크롤 수직 파이프라인 — 진행 중 스텝만 자동 전개, 상단 진도 블록(경과·ETA), 스텝별 실측/평균 소요시간, 하위 Run 링크, OTP 패널 |

**WS:** Run 상세는 `app/web/frontend/run/` (엔트리 `entries/run.ts`). 수트 상세는 `app/web/frontend/suite/` (엔트리 `entries/suite.ts`) — 수트 이벤트 WS + 현재 하위 Run 진행 WS 두 개.

**Run 상세 구조(Cycle 3):**
- 셸: `body:has(.run)` 넌스크롤(공통 `shell.css`). 좌우 열이 각각 모듈 목록과 로그의 세로 스크롤 하나를 소유한다.
- 자동 초점: `error` → `anomaly` → `running`/`waiting_input` 순으로 첫 모듈을 초점 처리하고, 실패 분석을 펼친다.
- 로그 필터: 초점 모듈을 자동으로 따른다. 사용자가 필터를 바꾸면 페이지를 떠날 때까지 자동 추종을 멈춘다.
- 도메인 모델·이벤트 wire 불변.

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

### AC-005: 런 상세 2열과 초점 전환

```gherkin
Given 모듈이 실패한 run
When 상세 화면을 연다
Then 그 모듈에 data-focus="true" 가 있고 AI 분석이 뷰포트 안에 있다
And 로그 필터가 그 모듈로 맞춰져 있다
And 사용자가 필터를 바꾸면 이후 자동 추종이 멈춘다
```

### AC-006: 런 상세 스크롤 소유권

```gherkin
Given 모듈 10개짜리 run
When 1366x768 에서 렌더한다
Then body 세로 스크롤이 0 이다
And 내부 스크롤러가 좌우 열에 하나씩 정확히 2개다
```

## 6. 스크립트

- `entries/run.ts` + `app/web/frontend/run/` — Run 상세
- `app.js` — Run 이력·예약 오버뷰·공용 피드백 보조 함수
- `entries/suite.ts` + `app/web/frontend/suite/` — 수트 상세
- `admin-dashboard.js`, `admin-runs.js`, `admin-ops.js`, `admin-stats.js`
