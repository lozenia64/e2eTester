# SPEC-UI-007: 일간 대시보드 — Viewport-Fit 무스크롤 (축소 수납) SSOT

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-007` |
| **상태** | `approved` |
| **우선순위** | P0 (제품 의도 정합) |
| **의존** | `SPEC-UI-001`, `SPEC-UI-004`, `SPEC-UI-005`, `SPEC-UI-006` |
| **대체·수정** | `SPEC-UI-004` §3.1·§3.4 (본 Spec이 SSOT), `SPEC-UI-005` §3.4·FR-004, `SPEC-UI-006` §9 (Zone C 스크롤 허용 조항 **폐기**) |
| **SSOT 링크** | `docs/specs/dashboard/04-premium-light-redesign.md` §1.1·§3.5 |
| **구현 위치** | `app/web/static/dashboard.css`, `app/web/static/dashboard.js`, `app/web/templates/dashboard/partials/zone_a_kpi.html`, `tests/test_dashboard_viewport.py` |

## 1. 개요

### 1.1 목적

사용자 의도를 명확히 한다:

> **「스크롤이 생기지 않는다」= 이 영역(가용 뷰포트) 안에 화면의 모든 요소가 축소·압축되어 들어가야 한다.**

즉, 문서 스크롤뿐 아니라 **Zone C 내부 스크롤·가로 스크롤·스크롤바 UI도 금지**한다. 넘치는 콘텐츠는 **스크롤로 보여주지 않고** 밀도(density) 단계 하향·선택적 요소 숨김·말줄임·드로어/툴팁으로 처리한다.

`SPEC-UI-005`/`006`에서 도입된 **콘텐츠 높이 기반 행 + `overflow-y: auto`** 는 본 의도와 충돌하므로 **폐기**한다.

### 1.2 핵심 원칙 — Fit, don’t scroll

| 원칙 | 설명 |
| --- | --- |
| **Zero scrollbar** | `.dash` 하위 모든 노드에서 `overflow: auto|scroll` 금지. `scrollHeight === clientHeight` (세로·가로). |
| **Partition, don’t pile** | Zone C 높이를 시스템 수 N으로 **균등 분할**. 행이 내용만큼 커지지 않음. |
| **Compress ladder** | 공간 부족 시 density tier 하향 → 선택 행 숨김 → 타이포·패딩 축소. |
| **Identity survives compression** | 축소해도 히어로 제목·시스템명·아이콘·KPI 4타일은 **숨기지 않음** (UI-006 유지). |
| **Overflow is clipped, not scrolled** | 모듈 칩·긴 라벨은 `overflow: hidden` + ellipsis / dots. |

### 1.3 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | 일반 사용자 — 랜딩 대시보드 |

### 1.4 범위

**In scope:**

- Zone C `flex: 1 1 0` 균등 분할 복원
- `.dash__systems` `overflow-y: auto` 제거
- density 알고리즘을 **row_h = zoneC / N** 기준으로 복원·강화
- Zone A+B+attention **고정 예산** 내 축소 (히어로 잘림 방지)
- `data-scrollable` 속성·fade mask 제거
- Playwright 무스크롤 + **Zone C scrollbar absence** AC
- E2E: `.agents/skills/e2e-browser` 로 실화면 확인

**Out of scope:**

- API·집계 변경
- 사이드바 리디자인
- 드로어 내부 스크롤 (시스템 패널 `overflow-y: auto` 유지 가능 — 대시보드 셸 밖)

---

## 2. 가용 영역 정의

`SPEC-UI-004` §3.1과 동일:

| 조건 | width | height |
| --- | --- | --- |
| `≥ 768px` | `100vw − 16rem` (사이드바) | `100dvh` |
| `< 768px` | `100vw` | `100dvh − 3.25rem` |

```text
body:has(.dash) { overflow: hidden; }
.dash { height: 100%; overflow: hidden; display: flex; flex-direction: column; }
```

**금지 CSS (전역):**

```css
/* NEVER on dashboard shell */
overflow: auto;
overflow: scroll;
overflow-y: auto;
scrollbar-gutter: stable; /* scroll 전제 — 제거 */
```

---

## 3. Zone 레이아웃 — 압축 수납 모델

### 3.1 세로 3구역 + 선택 attention

```text
┌─ .dash (height = 100%, overflow hidden) ─────────────────┐
│ Zone KPI host (#dash-host-kpi)     flex-shrink: 0        │
│   ├─ Zone A Hero                     (압축 가능 tier)    │
│   ├─ Zone B Stats                    (압축 가능 tier)    │
│   └─ Zone Attention (optional)       (압축·1행)          │
├──────────────────────────────────────────────────────────┤
│ Zone C (#dash-zone-matrix)           flex: 1; min-h: 0  │
│   └─ .dash__systems                  overflow: hidden    │
│        ├─ row × N  (flex: 1 1 0)     균등 높이 분할      │
│        └─ …                                              │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Zone KPI host — 히어로 잘림 방지 (HF-1 회귀 교정)

**문제:** `min-height: clamp(7rem, 18cqh, 11rem)` on `#dash-host-kpi`가 Zone C를 과도하게 밀어 히어로·통과율이 뷰포트 밖으로 잘림.

**규칙:**

1. `#dash-host-kpi` — **`min-height` 제거**. 높이는 콘텐츠 + tier 압축으로만 결정.
2. `#dash-host-kpi` — `max-height: 42%` of `.dash.clientHeight` (6시스템·attention 시 상한). 초과 시 `data-kpi-compress="true"`로 패딩·폰트 축소.
3. Zone A flex 구조(UI-006) **유지** — `dash-hero__top` / `dash-hero__aside`.
4. **필수 가시 요소** (어떤 tier에서도 DOM에 존재 + bounding box in `.dash`):
   - `.dash-hero__title` — `오늘의 점검 현황`
   - `.dash-hero__rate-label` — `통과율`
   - `.dash-hero__meta`
   - `#dash-zone-stats` 4타일 전체

### 3.3 Zone C — 균등 분할 (UI-004 복원)

```css
.dash-host-matrix {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.dash__systems {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--dash-row-gap);
  overflow: hidden;          /* NOT auto */
}

.dash-sys-row {
  flex: 1 1 0;               /* 균등 분할 — UI-006의 flex: 0 0 auto 폐기 */
  min-height: 0;             /* UI-006의 min-height tier vars 폐기 */
  max-height: none;
  overflow: hidden;          /* 행 내부 클리핑만 */
}
```

**행 높이:**

```text
row_h = (zoneC_clientHeight − gap × (N−1)) / N
```

`N` = `data-system-count` (1~6).

### 3.4 Density tier — row_h 기준 (SSOT)

`ResizeObserver` → `#dash-zone-matrix`에 `data-density` 설정.

**알고리즘 (`dashboard.js`):**

```javascript
const rowH = (container.clientHeight - gap * (n - 1)) / Math.max(n, 1);
const tier = rowH >= 72 ? "comfortable"
  : rowH >= 56 ? "compact"
  : rowH >= 44 ? "dense"
  : rowH >= 32 ? "minimal"
  : "micro";
container.dataset.density = tier;
```

**`data-scrollable` / `dataset.scrollable` — 삭제.** fade `mask-image` — 삭제.

| tier | row_h | Zone C UI | Zone KPI 압축 |
| --- | --- | --- | --- |
| `comfortable` | ≥ 72px | segment bar + chip labels + header | 기본 |
| `compact` | 56–71px | segment 3px, chip ellipsis 8ch | stats padding − |
| `dense` | 44–55px | segment 숨김, chip 6ch | hero rate 축소 |
| `minimal` | 32–43px | chips → dots, header 유지 | attention 1줄 compact |
| `micro` | < 32px | dots only, meta 축소, CTA 텍스트 숨김(아이콘만) | hero title 1rem, stats min-h 40px |

**UI-006 유지 (축소해도):**

- 시스템명 `display:none` 금지
- `dash-sys-row__header` flex 구조 유지
- KPI 4타일 DOM 4개 유지

**선택 숨김 (공간 확보, micro):**

- `.dash-sys-row__segment` — `dense` 이하
- `.dash-hero__summary` — `micro`에서만 숨김 (제목·메타는 유지)
- `.dash-sys-row__cta` 글자 — `micro`에서 `점검`만 또는 아이콘 버튼

### 3.5 가로 수납

- KPI 4타일: `grid-template-columns: repeat(4, minmax(0, 1fr))` (UI-006 유지)
- 모듈 칩: `overflow: hidden`, 가로 스크롤 금지
- 카드 header: `min-width: 0` on identity, badge/cta `flex-shrink: 0`

---

## 4. 기능 요구사항 (FR)

### FR-001: 절대 무스크롤

1. `document.documentElement` — `scrollHeight <= innerHeight`, `scrollWidth <= innerWidth`
2. `.dash` 및 모든 자손 — `scrollHeight <= clientHeight` (드로어 패널 제외 — `position:fixed` 밖)
3. `.dash__systems` — `overflow-y` computed value ≠ `auto|scroll`
4. 스크롤바 UI 없음 (WebKit `::-webkit-scrollbar` width 0이 아닌 **overflow 자체 금지**)

### FR-002: 균등 분할

1. N개 시스템 → N행이 Zone C 높이를 **완전히** 채움 (빈 여백 없음)
2. 행 높이 편차 ≤ 2px (반올림 오차만 허용)
3. `flex: 1 1 0` on `.dash-sys-row`

### FR-003: 압축 사다리

공간 부족 시 순서:

1. density tier 하향 (comfortable → micro)
2. segment bar 숨김
3. chip label → dots
4. padding / font-size tier CSS
5. summary / CTA 텍스트 축소 (micro)
6. **스크롤 도입 — 금지** (이 단계不存在)

### FR-004: 가시성 최소선 (UI-006 계승)

| 요소 | 최소선 |
| --- | --- |
| Hero title | width ≥ 120px, height ≥ 16px, in `.dash` box |
| Hero 통과율 라벨 | visible |
| KPI 4타일 | 4개 모두 in `.dash` box |
| System icon | ≥ 20px (micro에서 16px) |
| System name | font ≥ 12px (micro), ≥ 14px (그 외) |

### FR-005: 회귀

UI-005/006 기능 유지: HTMX refresh, attention strip, segment(comfortable~compact), glyphs, chevron, drawer.

---

## 5. API 계약

**변경 없음.**

---

## 6. 명시적 폐기

| 조항 | 출처 | 처리 |
| --- | --- | --- |
| Zone C `overflow-y: auto` | UI-005/006 | **폐기** |
| `data-scrollable` + fade mask | UI-005/006 | **삭제** |
| `flex: 0 0 auto` + `--dash-row-min-h` | UI-006 | **폐기** |
| `#dash-host-kpi min-height: 7rem` | UI-006 | **폐기** → `max-height: 42%` |
| viewport 기반 `ROW_MIN_H` tier pick | UI-006 JS | **폐기** → row_h tier pick |
| UI-004 `micro`에서 system name 숨김 | UI-004 | **이미 UI-006에서 폐기** — 유지 |

---

## 7. 수용 기준 (AC)

### AC-001: 문서 무스크롤

```gherkin
Given viewports 320×568, 1280×720, 1920×1080
  And 6 systems loaded
When dashboard rendered
Then document scrollHeight <= innerHeight
  And document scrollWidth <= innerWidth
```

### AC-002: Zone C 무스크롤

```gherkin
Given viewport 1280×720, 6 systems
When dashboard loaded
Then .dash__systems scrollHeight <= clientHeight
  And getComputedStyle(.dash__systems).overflowY is "hidden"
  And no descendant of .dash__systems shows overflow auto/scroll
```

### AC-003: 균등 분할

```gherkin
Given 6 .dash-sys-row elements
When measuring clientHeight of each row
Then max(height) - min(height) <= 2
  And sum(heights) + gaps ≈ .dash__systems.clientHeight (±4px)
```

### AC-004: 히어로·KPI in-view (UI-006 계승)

```gherkin
Given viewport 1280×720, sidebar visible
Then .dash-hero__title bounding box inside .dash bounding box
  And all 4 .dash-stats__tile inside .dash bounding box
  And first tile label is "이상징후"
```

### AC-005: Identity in-view (UI-006 계승)

```gherkin
Given first .dash-sys-row
Then .dash-sys-row__icon and __name visible inside row rect
  And name fontSize >= 14 (or >= 12 at micro density)
```

### AC-006: Density responds to resize

```gherkin
Given dashboard at 1920×1080
When height reduced to 568px
Then data-density changes to dense, minimal, or micro
  And AC-001 and AC-002 still pass
```

### AC-007: No scrollable dataset

```gherkin
When dashboard loaded at any viewport
Then .dash__systems does not have data-scrollable="true"
```

---

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | `dashboard.js` density 함수 단순화 (< row_h 기준 30줄) |
| NFR-002 | `dashboard.css?v=4` cache bust |
| NFR-003 | E2E: `.agents/skills/e2e-browser` — AC-002 육안·스냅샷으로 스크롤바 없음 확인 |
| NFR-004 | `prefers-reduced-motion` 유지 |

---

## 9. 테스트 요구사항

| 유형 | 파일 | 내용 |
| --- | --- | --- |
| Playwright | `tests/test_dashboard_viewport.py` | AC-001~007 신규/갱신 |
| Fragment | `tests/test_dashboard_fragments_http.py` | 회귀 |
| E2E 수동 | e2e-browser skill | 1280×720 실서버 — **스크롤바 없음** 체크리스트 |

### 9.1 E2E 체크리스트 (e2e-browser)

```text
E2E-FIT-1: 페이지·Zone C 모두 세로 스크롤바 없음
E2E-FIT-2: 6개 시스템 카드가 한 화면에 전부 보임 (스크롤 없이)
E2E-FIT-3: 히어로 제목 + 통과율 + KPI 4타일 동시 노출
E2E-FIT-4: 각 카드에 시스템 아이콘·이름 보임
E2E-FIT-5: 창 높이 50%로 줄여도 스크롤 없이 tier만 변경
```

### 9.2 Playwright assert 스니펫

```javascript
// AC-002
const sys = document.querySelector('.dash__systems');
return sys.scrollHeight <= sys.clientHeight + 1
  && getComputedStyle(sys).overflowY === 'hidden';
```

---

## 10. 구현 파일 맵

| 파일 | 변경 |
| --- | --- |
| `dashboard.css` | `.dash__systems overflow:hidden`, `.dash-sys-row flex:1 1 0`, remove scrollable/mask, kpi max-height |
| `dashboard.js` | row_h tier algorithm, remove scrollable logic |
| `zone_a_kpi.html` | optional `data-kpi-compress` hook only if needed |
| `dashboard.html` | `css?v=4` |
| `tests/test_dashboard_viewport.py` | AC-002, AC-003, AC-007 |

---

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 초안 — 무스크롤 = 축소 수납 SSOT, UI-005/006 스크롤 폐기 | AI |
