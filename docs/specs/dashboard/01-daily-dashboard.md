# SPEC-UI-001: 일간 점검 현황 대시보드

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-001` |
| **상태** | `approved` |
| **의존** | `SPEC-IDENTITY-002` |
| **구현** | `app/web/templates/dashboard.html`, `app/web/templates/dashboard/partials/`, `app/web/frontend/entries/dashboard.ts`, `app/web/frontend/styles/dashboard.css`, `app/web/frontend/styles/shell.css`, `app/web/frontend/components/{status-hero,system-matrix,activity-feed,kpi-card}/`, `app/api/routes_daily.py`, `app/contexts/insights/application/daily_dashboard.py`, `app/contexts/insights/application/daily_summary.py` |

## 1. 개요

로그인 후 **첫 화면** (`GET /`). 오늘(KST) 시스템·모듈별 점검 상태를 한 화면에서 보여 주는 관제탑이다.

| 액터 | 동작 |
| --- | --- |
| `operator` | 접근 가능한 시스템의 오늘 상태를 본다 |
| `admin` | `GET /` 접근 시 `/admin` 으로 리다이렉트 |

사용자는 5초 안에 오늘 전체 상태, 주의가 필요한 시스템, 시스템별 모듈 진행을 파악할 수 있어야 한다.

**Out of scope:** 다크 모드, 대시보드 WebSocket(폴링 + morph 유지), 7일 추이.

## 2. API

| Method | Path | 용도 |
| --- | --- | --- |
| GET | `/api/dashboard/daily` | 시스템·모듈 현황 JSON |
| GET | `/api/dashboard/daily/summary` | KPI 카드 4장 JSON |
| GET | `/api/dashboard/daily/fragments/{zone}` | `kpi`·`matrix`·`activity` HTML. 그 외 zone 은 404 |
| GET | `/api/dashboard/daily/fragments/system/{code}/panel` | 시스템 상세 드로어. 접근 불가 시스템은 404 |

**스코프:** 사용자 `allowed_system_codes`. PII-free. `matrix` zone 이름은 HTMX 호환을 위해 유지한다.

## 3. 레이아웃

### 3.1 화면 구성

| 영역 | 호스트 | 내용 |
| --- | --- | --- |
| 상태 | `#dash-host-kpi` | 진행 링, 상태 문장, 날짜·갱신 시각, 새로고침, KPI 카드 4장, 주의 스트립 |
| 매트릭스 | `#dash-host-matrix` | 시스템당 1행 |
| 활동 | `#dash-host-activity` | 최근 활동 피드 |

| 조건 | 배치 |
| --- | --- |
| 뷰포트 `< 768px` | 1열 세로 스택. 활동 영역 높이는 최대 30% |
| `main` 내부 폭 `≤ 1440px` | 2열. 왼쪽에 상태·활동, 오른쪽에 매트릭스 |
| `main` 내부 폭 `> 1440px` | 3열. 상태·매트릭스·활동 순서 |

### 3.2 스크롤

**문서는 스크롤되지 않는다.** 내용이 넘치면 스크롤을 추가하지 않고 CSS 컨테이너 쿼리로 줄이거나 말줄임으로 잘라 낸다.

내부 스크롤은 활동 영역과 시스템 상세 드로어만 허용한다. 밀도를 JS 로 계산하지 않으며 `data-density`·`data-scrollable` 속성을 쓰지 않는다.

### 3.3 사이드바 인셋

데스크톱(`≥ 768px`)에서 본문은 고정 사이드바(16rem) 오른쪽에서 시작한다. `main` 은 `padding-left: 16rem` 을 유지하고, 모바일에서는 `0` 이다.

겹침을 `z-index` 로 해결하지 않는다. `main` 에 `padding: 0` 축약형이나 `width: 100vw` 를 쓰지 않는다.

## 4. 기능 요구사항 (FR)

### FR-001: 상태 영역

- 진행 링은 `passed / modules` 비율을 보여 준다. 링 안에 `N/M`, `모듈 정상 · 통과율%` 를 표시한다.
- 링 색은 `error > anomaly > running > 전체 미점검 > passed` 순서로 정한다.
- 상태 문장(`.status-hero__headline`)은 아래 표에서 처음 맞는 조건을 쓴다.

| 조건 | 문구 |
| --- | --- |
| `modules == 0` | `점검 대상이 없습니다` |
| `error > 0` | `점검실패 {error}건 — 우선 확인이 필요합니다` |
| `anomaly > 0` | `이상징후 {anomaly}건이 감지되었습니다` |
| `running > 0` | `{running}개 모듈이 진행 중입니다` |
| `not_inspected == modules` | `오늘 아직 점검이 시작되지 않았습니다` |
| 그 외 | `오늘 점검은 정상입니다` |

### FR-002: KPI 카드

값이 0이어도 항상 4장을 렌더한다.

| key | 라벨 | 링크 |
| --- | --- | --- |
| `pass_rate` | 통과율 | 없음 |
| `self_healed` | 스스로 복구 | `/self-healing` |
| `pending_patches` | 내 승인 대기 | 패치 목록 |
| `savings` | 이번 달 절감 (`추정` 표시 가능) | 관리자만 모듈 설정 |

### FR-003: 주의 스트립

- `attention` 이 비어 있지 않으면 표시하고, 공간 부족을 이유로 숨기지 않는다.
- 대상은 `error`·`anomaly`·`running` 모듈과 미점검 시스템이며 심각도 순으로 정렬한다.
- 첫 항목만 펼치고 나머지는 `+N건` 으로 표시한다. `run_id` 가 있으면 `Run` 링크를 둔다.
- `전체 보기` 는 `/anomalies` 로 이동한다.

### FR-004: 시스템 매트릭스

- 한 행은 `코드 · 이름 · 모듈 셀 · 점검 수 · 배지` 이며 모듈 셀은 한 줄 진행 막대다. 전체 미점검 시스템은 배지 대신 `점검 실행`(`/runs/execute`) 링크를 둔다.
- N개 행이 매트릭스 높이를 균등하게 나눈다.
- 대표 배지는 `error > anomaly > running > 주의(blocked) > 미점검 > 정상` 순서로 하나만 정한다.
- 화면 순서는 대표 배지 기준 `passed > anomaly > error > running > blocked > not_inspected` 이다. 그룹 안에서는 API 순서를 유지하고, API 정렬은 바꾸지 않는다.
- 시스템이 없으면 `표시할 시스템이 없습니다.` 를 보여 준다.
- `run_id` 가 있는 셀은 `/runs/{run_id}` 링크다. 자동 복구된 모듈에는 `⟳` 를 표시한다.
- 대표 배지가 `error`·`anomaly`·`running`·`waiting_input`·`blocked` 인 행은 `data-priority="attention"` 이고 왼쪽에 3px 강조선을 둔다. 강조선은 레이아웃에 영향이 없도록 inset `box-shadow` 로 그린다.
- 행 id 는 `dash-system-{code}` 로 고정해 정렬이 바뀌어도 morph 가 같은 행을 유지하게 한다.

### FR-005: 활동 피드

오늘 결과가 있는 모듈 상태를 최신순으로 최대 20건 보여 준다. 시각·시스템·모듈·상태를 표시하고, `run_id` 가 있으면 Run 상세로 연결한다. 항목이 없으면 `오늘 기록된 점검 활동이 없습니다.` 를 보여 준다.

### FR-006: 드로어

행의 일반 영역이나 시스템 이름 버튼을 누르면 시스템 상세 드로어가 열린다. 셀 링크, 활동 링크, `점검 실행` 은 드로어를 열지 않고 자기 목적지로 이동한다.

### FR-007: 갱신

- 탭이 보이는 동안 30초마다, 탭 복귀 시, 새로고침 버튼을 누를 때 세 영역을 다시 불러온다.
- 세 영역은 `hx-swap="morph:innerHTML"` 로 교체해 노드·포커스·애니메이션을 보존한다.
- 대시보드 fragment 요청이 실패하면 `#dash-error` 배너를 표시하고, 다음 교체 성공 시 숨긴다.

### FR-008: 모션

- 첫 진입에서만 행 순차 등장, 막대 차오름, 링 채움, 카운트업을 재생하고 폴링 갱신에서는 재생하지 않는다.
- `anomaly`·`error` 행은 첫 진입 때 테두리가 3회 깜빡인다.
- 카운트업 중 새 값을 받으면 애니메이션을 취소하고 최신 값을 즉시 표시한다.
- `running` 셀은 shimmer, `waiting_input` 셀은 pulse 로 표시한다.
- `prefers-reduced-motion: reduce` 에서는 위 애니메이션을 재생하지 않는다.

## 5. 수용 기준 (AC)

### AC-001: 오늘만

```gherkin
Given E2E_SCHEDULE_TZ=Asia/Seoul
When GET /api/dashboard/daily at 23:59 KST
Then only today's runs reflected
```

### AC-002: 스코프

```gherkin
Given user allowed ["hom"]
When GET daily
Then mhm modules absent
```

### AC-003: 대표 배지 우선순위

```gherkin
Given system module counts
When system_summary_badge is computed
Then the highest priority of error > anomaly > running > blocked > not_inspected > passed wins
  And a system with zero modules is not_inspected
```

### AC-004: 문서 무스크롤

```gherkin
Given viewports 320×568, 390×844, 1280×720, 1920×1080
  And 6 systems loaded
When dashboard rendered
Then document scrollHeight <= innerHeight
  And document scrollWidth <= innerWidth
```

### AC-005: 내부 스크롤은 활동 영역만

```gherkin
Given viewports 1280×720, 1366×768, 1920×1080, 2560×1440
When dashboard rendered
Then #dash-host-kpi and #dash-host-matrix have overflow-y hidden
  And .dash__systems scrollHeight <= clientHeight
  And #dash-host-activity has overflow-y auto or scroll
```

### AC-006: 반응형 배치

```gherkin
Given viewport 1920×1080
Then status, matrix, activity sit left to right on the same row

Given viewport 1280×720
Then matrix is right of status and activity is below status

Given viewport 390×844
Then status and matrix are stacked in one column
```

### AC-007: 행 균등 분할

```gherkin
Given 6 .dash-sys-row at 1280×720
Then max(height) - min(height) <= 2
  And sum(heights) + gaps equals .dash__systems clientHeight within 4px
```

### AC-008: CSS 단독 수납

```gherkin
Given dashboard loaded at 1280×720
When viewport height is reduced to 568px
Then document and matrix still do not overflow
  And .dash__systems has no data-density and no data-scrollable="true"
  And rows have no inline flex style
```

### AC-009: 상태 영역 가시성

```gherkin
Given viewport 1280×720 and 6 systems
Then .status-hero__ring exposes data-passed and data-total
  And .status-hero__headline is at least 120×16px and carries the highest priority message
  And the first KPI card is visible
```

### AC-010: 빈 점검일

```gherkin
Given all modules are not_inspected
When dashboard rendered at 1280×720
Then headline contains "아직 점검이 시작되지 않았습니다"
  And ring data-passed is 0
  And headline is inside .dash
```

### AC-011: KPI 카드 4장

```gherkin
Given any totals
Then exactly 4 .kpi-card render inside .status-hero__cards
  And all of them are inside .dash at 1280×720
```

### AC-012: 시스템 행 구조

```gherkin
Given matrix fragment at 1920×1080
Then each row has .dash-sys-row__cells and .dash-sys-row__count
  And module cells stay on one line
  And legacy .dash-mod, .dash-seg, segment bar and chevron are absent
```

### AC-013: 화면 정렬

```gherkin
Given systems with mixed summary badges
When matrix fragment rendered
Then rows follow passed > anomaly > error > running > blocked > not_inspected
```

### AC-014: 시스템 정체성

```gherkin
Given viewport 1280×720
Then .dash-sys-row__icon is at least 24×24px
  And .dash-sys-row__name is at least 40px wide with font-size >= 14px
  And both are inside .dash
```

### AC-015: 주의 스트립

```gherkin
Given attention is not empty and viewport 320×568
Then #dash-zone-attention is visible
  And it links to /anomalies
```

### AC-016: 주의 행 강조

```gherkin
Given system with summary badge tone "error"
Then its row has data-priority "attention"
  And computed box-shadow contains inset 3px
  And border-left width is 0
```

### AC-017: 키보드 접근

```gherkin
Given matrix fragment
Then the row element has no tabindex, role=button or aria-label
  And system name is a native button labelled "{name} 상세 보기"
When a run cell or activity link is focused
Then a 2px focus ring in --st-running-solid is visible
```

### AC-018: 사이드바 비겹침

```gherkin
Given viewport 1280×720
Then main padding-left is 16rem
  And .dash does not overlap #app-sidebar
  And headline, first KPI card, system icon and name start right of the sidebar
```

### AC-019: 모바일 인셋 없음

```gherkin
Given viewport 390×844
Then main padding-left is 0
  And .dash starts at the left edge
```

### AC-020: 모션 감소

```gherkin
Given prefers-reduced-motion: reduce
When dashboard loads
Then system rows and module cells have animation-name none
```

### AC-021: 활동 피드

```gherkin
Given module status rows
When activity feed is built
Then items are newest first, at most 20
  And rows without a result or a registered module are excluded
```

### AC-022: 드로어 분리

```gherkin
Given a system row
When user clicks the row or the system name
Then drawer opens with that system panel
When user activates a run cell link
Then the link navigates and the drawer stays closed
```

## 6. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | PII-free |
| NFR-002 | UI 문자열 한국어 |
| NFR-003 | 상태를 색만으로 전달하지 않는다. 배지 문구·`title`·`aria-label` 로 함께 제공한다 |

## 7. 테스트

| 파일 | 범위 |
| --- | --- |
| `tests/test_daily_dashboard.py` | 집계·배지·주의 항목·활동 피드 |
| `tests/test_dashboard_fragments_http.py` | fragment 구조·정렬 |
| `tests/test_dashboard_viewport.py` | Playwright 무스크롤·배치·가시성·모션 |
| `app/web/frontend/entries/dashboard.test.ts` | AC-022 드로어 분리 |
| `app/web/frontend/entries/dashboard.morph.test.ts` | morph 행 식별 |

## 8. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-10-31 | `SPEC-UI-004`~`008` 을 현재 구현 기준으로 통합. AC 번호 재부여 | AI |
