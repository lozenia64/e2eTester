# SPEC-UI-004: 일간 점검 대시보드 — Premium Light 리디자인

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-004` |
| **상태** | `approved` (시각 폴리시는 `SPEC-UI-005`가 §3·FR·AC 일부 우선) |
| **우선순위** | P1 |
| **의존** | `SPEC-UI-001`, `SPEC-IDENTITY-002` |
| **대체** | `SPEC-UI-001` §3 UI (시각·레이아웃만; API·집계 규칙 유지) |
| **SSOT 링크** | `docs/specs/dashboard/01-daily-dashboard.md`, `app/contexts/insights/application/daily_dashboard.py` |
| **구현 위치** | `app/web/templates/dashboard.html`, `app/web/templates/dashboard/partials/`, `app/web/static/dashboard.js`, `app/web/static/dashboard.css` (신규) |
| **비주얼 레퍼런스** | `research/dashboard-redesign-demos.html` §② Premium Light |

## 1. 개요

### 1.1 목적

로그인 후 첫 화면(`GET /`)인 **일간 점검 현황 대시보드**를 Premium Light 비주얼로 전면 리디자인한다. 대담한 타이포·깨끗한 화이트 베이스·시스템 카드 리스트로 **데모·발표 시 즉각적인 인상**을 주되, 일상 업무에서도 한 화면에 오늘의 상태를 파악할 수 있게 한다.

핵심 제약: **모든 뷰포트 크기(PC·모바일·소형 창 포함)에서 상하·좌우 스크롤이 발생하지 않는다.** 콘텐츠는 가용 영역에 맞춰 축소·압축되며, 넘치는 정보는 드로어·툴팁·Run 상세 링크로 위임한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | 일반 사용자 (`role=user`) — 랜딩 대시보드 소비 |
| `admin` | 관리자 — `GET /` 접근 시 기존과 동일하게 `/admin` 리다이렉트 (본 Spec 범위 밖) |

### 1.3 범위

**In scope:**

- Premium Light 디자인 시스템(색·타이포·카드·배지·모션)
- 뷰포트 핏 셸 — **모든 해상도** 무스크롤 (최소 320×568 포함)
- Cytoscape 파이프라인 매트릭스 **제거** → 시스템 카드 리스트 UI로 교체
- 기존 HTMX fragment 갱신·30초 auto-refresh·시스템 드로어 유지
- `attention` 데이터 활용 — 주의 항목 인라인 노출(공간 허용 시)
- 밀도 자동 조절(density tier) — 뷰포트 높이·시스템 수에 따른 축소

**Out of scope:**

- `/api/dashboard/daily` 응답 스키마·집계 규칙 변경 (`daily_dashboard.py` 로직 불변)
- 관리자 대시보드(`/admin`) 리디자인
- 다크 모드
- WebSocket 실시간 전환(기존 30초 polling 유지)

## 2. 디자인 시스템 — Premium Light

### 2.1 무드·원칙

| 원칙 | 설명 |
| --- | --- |
| **Editorial clarity** | 거대한 통과율 숫자가 시선을 먼저 잡고, 보조 KPI·시스템 카드가 뒤를 받침 |
| **Quiet luxury** | 화이트·연한 그레이·얇은 보더. 그라데이션은 히어로 숫자·시스템 아이콘에만 제한 |
| **Status as accent** | 상태 색은 배지·모듈 칩·좌측 액센트에만 사용. 본문은 `#09090b` / `#71717a` |
| **Motion with purpose** | 최초 진입 시 KPI 카운트업(optional), 진행 중 모듈만 subtle pulse. `prefers-reduced-motion` 존중 |

### 2.2 색상 토큰

```text
--pl-bg:           #fafafa          /* 페이지 배경 */
--pl-surface:      #ffffff          /* 카드 */
--pl-border:       #e4e4e7          /* 카드·구분선 */
--pl-text:         #09090b          /* 제목 */
--pl-text-muted:   #71717a          /* 메타·라벨 */
--pl-text-subtle:  #a1a1aa          /* 보조 */

/* 상태 — 기존 대시보드 tone과 동일 팔레트 유지 */
--st-passed:       #10b981
--st-anomaly:      #f59e0b
--st-error:        #ef4444
--st-running:      #3b82f6
--st-blocked:      #f97316
--st-idle:         #a1a1aa
```

### 2.3 타이포그래피 (fluid)

| 역할 | clamp 예시 | 용도 |
| --- | --- | --- |
| Hero rate | `clamp(2.5rem, 6cqh, 5rem)` | 통과율 % |
| Page title | `clamp(1.25rem, 3cqh, 2rem)` | "오늘의 점검 현황" |
| Stat value | `clamp(1.25rem, 2.5cqh, 2rem)` | 이상징후·실패 등 |
| System name | `clamp(0.75rem, 1.8cqh, 0.875rem)` | 카드 제목 |
| Module chip | `clamp(0.6rem, 1.4cqh, 0.7rem)` | 모듈 pill |

`cqh`/`cqi`는 대시보드 루트에 `container-type: size`를 설정한 뒤 사용한다.

### 2.4 모션

| 요소 | 동작 | reduced-motion |
| --- | --- | --- |
| KPI 숫자 | 첫 로드 시 600ms ease-out 카운트업 | 즉시 최종값 표시 |
| 시스템 카드 | stagger fade-in 40ms 간격 | 없음 |
| 진행 중 칩 | 1.6s pulse ring | 정적 |
| 카드 hover | `translateY(-1px)` + shadow | shadow만 |

## 3. 레이아웃 — Viewport-Fit Shell

### 3.1 가용 영역 정의

대시보드 콘텐츠 박스 — **브레이크포인트별**:

| 조건 | width | height |
| --- | --- | --- |
| `≥ 768px` (사이드바 고정) | `100vw − 16rem` | `100dvh` |
| `< 768px` (모바일 헤더) | `100vw` | `100dvh − 3.25rem` (sticky header) |

대시보드 전용으로 `base.html`의 `main > div` 기본 `py-8 space-y-6`·`max-w-7xl`을 **페이지 스코프에서 무효화**하고, `.dash`가 위 박스를 꽉 채운다.

```text
body:has(.dash) {
  overflow: hidden;              /* 문서 스크롤 차단 */
}
body:has(.dash) main > div {
  max-width: none;
  padding: 0;
  height: 100dvh;
  overflow: hidden;
}
body:has(.dash) main {
  height: 100dvh;
  overflow: hidden;
}
@media (max-width: 767px) {
  body:has(.dash) main > div,
  body:has(.dash) main {
    height: calc(100dvh - 3.25rem);
  }
}
```

모바일에서도 `body.mobile-nav-open` 시 사이드바 드로어는 `position: fixed` 오버레이 — 대시보드 본문 높이는 변하지 않음.

### 3.2 Zone 구조

세로 3구역 — **합계 높이 = 100%**, Zone C만 `flex: 1; min-height: 0`.

```text
┌─────────────────────────────────────────────────────────┐
│ Zone A — Hero (flex-shrink: 0)                          │
│  · 날짜·메타 · 거대 통과율 · "N/M 모듈 정상"              │
├─────────────────────────────────────────────────────────┤
│ Zone B — Stats strip (flex-shrink: 0)                   │
│  · 이상징후 | 점검실패 | 진행 중 | 미점검 (4칸 균등)      │
├─────────────────────────────────────────────────────────┤
│ Zone C — System cards (flex: 1; min-height: 0)          │
│  · 시스템당 1행 카드 × N — 남은 높이를 N등분              │
│  · 각 카드: [아이콘+이름] [모듈 pills] [상태 배지]        │
└─────────────────────────────────────────────────────────┘
```

Zone C 행 높이:

```text
row_h = (zone_c_height − gap × (N−1)) / N
```

`N` = 접근 가능 시스템 수(최대 6). 행 높이가 밀도 임계값 이하로 내려가면 §3.4 density tier가 상승한다.

### 3.3 Zone C — 시스템 카드 (Premium Light)

각 시스템 1행. 그리드 3열:

| 열 | 너비 | 내용 |
| --- | --- | --- |
| Identity | `minmax(10rem, 14rem)` | 시스템 코드 아이콘(모노 배지) + 이름 + `inspected/module_total` |
| Modules | `1fr` | 모듈 pill 가로 나열. `overflow: hidden` — 넘치면 시각적으로 클리핑(스크롤 없음) |
| Badge | `auto` | 시스템 대표 상태 배지(정상·이상징후·점검실패·진행 중·미점검) |

**인터랙션:**

- 카드 행 클릭 → 기존 HTMX 시스템 드로어 (`GET .../fragments/system/{code}/panel`)
- 모듈 pill에 `run_id` 있으면 pill 클릭 → `/runs/{run_id}` (행 클릭과 `stopPropagation`)
- 키보드: 행 `tabindex=0`, Enter/Space → 드로어

**모듈 pill 스타일:**

| tone | pill |
| --- | --- |
| passed | filled, `--st-passed` 배경 |
| anomaly / error | filled, 해당 색 |
| running / waiting_input | filled + pulse |
| not_inspected / pending | dashed border, muted |
| 기타 | outline |

### 3.4 Density tier (자동)

`ResizeObserver`가 Zone C 컨테이너 높이·시스템 수를 관찰해 `data-density` 속성을 설정한다.

| tier | 조건 (row_h 기준) | 조절 |
| --- | --- | --- |
| `comfortable` | ≥ 72px | 기본 패딩·풀 모듈명 |
| `compact` | 56–71px | 패딩 축소, 모듈명 `max-width` + ellipsis |
| `dense` | 44–55px | 아이콘 축소, 모듈명 6자 초과 `…`, 배지 텍스트 축약 |
| `minimal` | < 44px | 모듈 pill → **상태 dot**만 표시(이름은 `title` 툴팁). 시스템명 1줄 ellipsis |
| `micro` | < 32px | Identity 열 축소(코드만), hero·stats 압축, attention strip 숨김 |

`minimal`/`micro`에서도 6시스템 × 최대 4모듈이 가로로 들어가야 하므로, dot 크기 `clamp(5px, 1cqw, 10px)` + `gap: 2px`를 사용한다.

모바일(`< 768px`) 레이아웃:

- Zone A·B는 동일 flex-shrink: 0 (더 작은 `clamp` 타이포)
- Zone C는 **세로 스택이 아닌** 동일하게 N등분 flex 행 — 카드 내부 그리드만 1열로 축소(identity 위, modules 아래, badge 우측 상단)
- `flex-wrap`으로 높이 증가 금지 — `overflow: hidden` 유지

### 3.5 지원 뷰포트 (무스크롤 AC 기준)

| 해상도 | 비고 |
| --- | --- |
| 320 × 568 | 최소 지원 (iPhone SE). `micro` tier 예상 |
| 390 × 844 | 모바일 기준 |
| 1280 × 720 | 데스크톱 최소. `dense`~`minimal` |
| 1920 × 1080 | 기준 comfortable |
| 3440 × 1440 (울트라와이드) | 좌우 여백만 증가, 스크롤 없음 |

가로·세로 모두 **스크롤바 금지** (`overflow: auto|scroll` 사용 금지, `overflow: hidden` + 클리핑).

## 4. 기능 요구사항 (FR)

### FR-001: Premium Light 히어로 (Zone A)

**설명:** 날짜·통과율·모듈 요약을 한 눈에 보여준다.

**표시 필드:**

| 필드 | 소스 |
| --- | --- |
| `date_label` | `data.date_label` |
| 통과율 | `data.totals.pass_rate` + `%` |
| 모듈 요약 | `{passed}/{modules} 모듈 정상` |
| 갱신 시각 | `data.generated_at` (HH:MM, 선택) |

**비즈니스 규칙:**

1. 영문 eyebrow `"Daily Inspection"` 제거 — 한국어 UI 일관성
2. 제목 카피: **"오늘의 점검 현황"**

### FR-002: Stats strip (Zone B)

**설명:** 주의 지표 4개를 균등 그리드로 표시.

| 타일 | 값 | 색 |
| --- | --- | --- |
| 이상징후 | `totals.anomaly` | `--st-anomaly` |
| 점검실패 | `totals.error` | `--st-error` |
| 진행 중 | `totals.running` | `--st-running` |
| 미점검 | `totals.not_inspected` | `--st-idle` |

타일 사이 1px `#e4e4e7` 구분(데모 ② stats grid 패턴).

### FR-003: 시스템 카드 리스트 (Zone C)

**설명:** `data.systems`를 대표 배지 tone 그룹 순서로 카드 행 렌더 — `passed > anomaly > error > running > blocked > not_inspected`(그룹 안은 API 순서). API(`sort_systems_attention_first`)는 불변이며 재정렬은 대시보드 템플릿(`zone_b_matrix.html`)에서만 한다. 모듈 셀은 칸으로 이어진 진행 막대로 그리고, 첫 진입 시 행 순차 등장 → 막대 차오름 → 이상징후·오류 행 테두리 3회 깜빡임(`prefers-reduced-motion` 시 생략).

**시스템 대표 배지 우선순위** (높은 것 하나만):

```text
error > anomaly > running > other > not_inspected(미점검 모듈 존재) > passed(전체 정상)
```

**비즈니스 규칙:**

1. 시스템 0개 → Zone C에 "표시할 시스템이 없습니다." (중앙 정렬, 스크롤 없음)
2. 시스템 코드 아이콘: `system_code` 대문자 3~5자 (HOM, MHM, FP, HRP, HWTC, CHBOT)
3. 아이콘 배경색: 대표 tone 기반 단색

### FR-004: 주의 항목 (선택 노출)

**설명:** `data.attention`이 비어 있지 않고 Zone A+B 이후 **남는 세로 공간 ≥ 80px**일 때만 Zone B 하단 또는 Zone C 상단에 컴팩트 attention strip 표시.

| 항목 | 최대 |
| --- | --- |
| attention 행 | 3개 (초과분은 "+N건" 뱃지) |

공간 부족 시 attention strip **숨김** (드로어·카드 배지로 충분). 스크롤로 해결하지 않음.

### FR-005: 갱신·에러 UX (기존 유지)

1. 30초 `dash-refresh` custom event → HTMX fragment 재요청
2. 탭 visibility 복귀 시 즉시 refresh
3. 수동 새로고침 버튼 — Zone A 우측, 컴팩트 pill
4. API 오류 시 `#dash-error` 배너 (기존)
5. 통과 수·정상률 카운트업은 노드당 첫 진입에만 실행한다. 진행 도중 새 목표값을 수신하면 이전 애니메이션을 취소하고 최신 값을 즉시 표시한다.

### FR-006: 시스템 드로어 (기존 유지)

- Alpine `drawerOpen` + `#dash-drawer-body` HTMX swap
- `system_panel.html` — Premium Light 톤에 맞게 스타일만 정비 (구조 동일)

## 5. API 계약

**변경 없음.** `SPEC-UI-001` §2 전부 적용.

| Method | Path | 용도 |
| --- | --- | --- |
| GET | `/api/dashboard/daily` | JSON (날짜 라벨·카운트업 초기값) |
| GET | `/api/dashboard/daily/fragments/kpi` | Zone A + Zone B (+ optional attention) |
| GET | `/api/dashboard/daily/fragments/matrix` | Zone C 시스템 카드 리스트 |
| GET | `/api/dashboard/daily/fragments/system/{code}/panel` | 드로어 |

**Fragment 변경:**

| zone | 기존 | 변경 |
| --- | --- | --- |
| `kpi` | KPI strip only | Zone A hero + Zone B stats (+ optional attention) |
| `matrix` | Cytoscape bento | Zone C card list HTML |

`matrix` zone ID는 HTMX 트리거 호환을 위해 **유지**한다 (이름만 legacy).

## 6. 제거·교체

| 항목 | 처리 |
| --- | --- |
| Cytoscape.js | `dashboard.html` script 태그 제거 |
| cytoscape-node-html-label | 제거 |
| `dashboard.js` 내 `buildElements`/`renderMatrixFromPayload` 등 | 제거 |
| `zone_b_matrix.html` Cytoscape 마크업 | 카드 리스트 템플릿으로 교체 |
| 인라인 `<style>` 370줄 | `dashboard.css`로 추출 |

## 7. 수용 기준 (AC)

### AC-001: 무스크롤 — 최소 뷰포트 320×568

```gherkin
Given viewport 320×568 (mobile)
  And user has access to all 6 systems
When GET / loads daily dashboard
Then document.documentElement.scrollHeight <= window.innerHeight
  And document.documentElement.scrollWidth <= window.innerWidth
  And no element within .dash shows overflow scrollbars
```

### AC-002: 무스크롤 — 1280×720

```gherkin
Given viewport 1280×720 and sidebar visible (md breakpoint)
When dashboard loaded with 6 systems
Then no page scrollbars in any direction
```

### AC-003: 무스크롤 — 1920×1080

```gherkin
Given viewport 1920×1080
When dashboard loaded with 6 systems
Then no page scrollbars
  And Zone C data-density is comfortable or compact
```

### AC-004: 무스크롤 — 울트라와이드

```gherkin
Given viewport 3440×1440
When dashboard loaded
Then no page scrollbars
  And content spans full main area (no max-w-7xl cap on dashboard)
```

### AC-005: Density tier 전환

```gherkin
Given dashboard loaded at 1920×1080
When viewport height reduced to 568px without width change
Then [data-density] on Zone C changes to dense, minimal, or micro
  And still no scrollbars
```

### AC-006: 집계·스코프 불변

```gherkin
Given SPEC-UI-001 AC-001, AC-002
When Premium Light dashboard rendered
Then API responses and module tones match SPEC-UI-001 expectations
```

### AC-007: 인터랙션

```gherkin
Given system card for "hom" visible
When user clicks card row (not a module pill)
Then drawer opens with hom module list

Given module pill with run_id
When user clicks the pill
Then navigates to /runs/{run_id}
```

### AC-008: 접근성

```gherkin
Given prefers-reduced-motion: reduce
When dashboard loads
Then no count-up or pulse animations
  And all status information available without hover
```

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | PII-free — 기존과 동일 |
| NFR-002 | First Contentful Paint: Cytoscape 제거로 기존 대비 JS weight 감소 (목표 −80KB+) |
| NFR-003 | `dashboard.css` + HTMX fragment만으로 Zone C 렌더 — JS는 density·카운트업·드로어만 |
| NFR-004 | 한국어 UI 문자열 유지 |
| NFR-005 | `prefers-reduced-motion` 전 구간 준수 |
| NFR-006 | Playwright viewport 테스트: `320×568`, `390×844`, `1280×720`, `1920×1080`에서 `scrollHeight === innerHeight` 및 `scrollWidth === innerWidth` assert |

## 9. 테스트 요구사항

| 유형 | 위치 | 내용 |
| --- | --- | --- |
| 단위 | `tests/test_daily_dashboard.py` | 변경 없음 (집계기 불변) |
| 브라우저 수동 | 체크리스트 §10 | 5종 해상도 무스크롤 확인 |
| E2E | `tests/test_dashboard_viewport.py` (신규) | Playwright viewport + scroll assert (4 해상도) |
| CI | 기존 gates | docs consistency — `SPEC-UI-004` 인덱스 등록 |

## 10. 구현 힌트

### 10.1 파일 맵

| 구성요소 | 파일 |
| --- | --- |
| 페이지 셸 | `dashboard.html` — `.dash` 루트, CSS link, script |
| 스타일 | `dashboard.css` — shell, zones, cards, density tiers, drawer |
| 로직 | `dashboard.js` — ResizeObserver density, count-up, HTMX hooks, drawer |
| Zone A+B | `partials/zone_a_kpi.html` → hero + stats 로 확장 |
| Zone C | `partials/zone_b_matrix.html` → card list |
| 드로어 | `partials/system_panel.html` — 톤 정비 |

### 10.2 Viewport shell CSS 스케치

```css
.dash {
  container-type: size;
  container-name: dash;
  display: flex;
  flex-direction: column;
  height: 100dvh;
  overflow: hidden;
  padding: clamp(0.75rem, 2cqh, 1.5rem) clamp(1rem, 3cqi, 2rem);
  background: var(--pl-bg);
}
.dash__systems {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: clamp(4px, 0.8cqh, 8px);
  overflow: hidden;
}
.dash-sys-row {
  flex: 1 1 0;
  min-height: 0;
  /* grid 3-col identity | modules | badge */
}
```

### 10.3 Density JS 스케치

```javascript
function updateDensity(container, systemCount) {
  const h = container.clientHeight;
  const gap = 8 * (systemCount - 1);
  const rowH = (h - gap) / Math.max(systemCount, 1);
  const tier = rowH >= 72 ? "comfortable"
    : rowH >= 56 ? "compact"
    : rowH >= 44 ? "dense"
    : rowH >= 32 ? "minimal" : "micro";
  container.dataset.density = tier;
}
```

### 10.4 base.html 영향 최소화

`dashboard.html`의 `{% block content %}` 앞뒤로만 스코프 한정:

```css
body:has(.dash) main > div { ... }
```

다른 페이지에는 영향 없음.

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 초안 — Premium Light + viewport-fit | AI |
| 2026-08-15 | 승인 — 전 뷰포트 무스크롤, micro tier, 모바일 예외 제거 | User |
