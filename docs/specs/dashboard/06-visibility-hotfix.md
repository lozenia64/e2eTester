# SPEC-UI-006: 일간 대시보드 — 가시성 핫픽스 (히어로·Identity·KPI)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-006` |
| **상태** | `approved` |
| **우선순위** | P0 (배포 차단) |
| **의존** | `SPEC-UI-001`, `SPEC-UI-004`, `SPEC-UI-005` |
| **대체·수정** | `SPEC-UI-005` §3.1·§3.2·§3.3·AC-001·AC-003·AC-004 (본 Spec이 우선) |
| **SSOT 링크** | `docs/specs/dashboard/05-hierarchy-polish.md` |
| **구현 위치** | `app/web/static/dashboard.css`, `app/web/templates/dashboard/partials/zone_a_kpi.html`(선택), `app/web/templates/dashboard/partials/_macros.html`(선택), `tests/test_dashboard_viewport.py`, `tests/test_dashboard_fragments_http.py` |
| **트리거** | 실사용 스크린샷(사이드바·6시스템·attention)에서 UI-005 P0 요소 미가시 확인 |

## 1. 개요

### 1.1 목적

`SPEC-UI-005` 구현 후 Playwright AC는 통과하나 **실제 운영 화면**에서 다음 3가지가 보이지 않는 회귀를 수정한다.

| # | 증상 | 영향 |
| --- | --- | --- |
| **HF-1** | 히어로 좌측 `오늘의 점검 현황`·메타·summary 소실 — `통과율`/`0%`만 보임 | P0-1 실패 |
| **HF-2** | 시스템 카드 좌측 아이콘·시스템명·`N/M 모듈` 소실 — 칩·세그먼트만 보임 | P0-2 실패 |
| **HF-3** | KPI 4타일 중 `이상징후` 타일이 뷰포트 밖·잘림 | P0-3 실패 |

목표: **사이드바 표시·1280×720·6시스템·attention 존재** 조건에서 위 3요소가 **픽셀 단위로 화면 안에** 들어온다.

### 1.2 근본 원인 (진단)

| HF | 원인 | 메커니즘 |
| --- | --- | --- |
| HF-1 | 히어로 그리드 1열 `min-width: 0` + `align-items: end` | `1fr` 열이 수축·하단 정렬되며 텍스트 블록이 시각적으로 사라지거나 높이 0으로 계산됨 |
| HF-1 | `#dash-host-kpi`가 `.dash` flex 압박 시 클리핑 | `overflow: hidden` on `.dash` — KPI 영역 최소 높이 미보장 |
| HF-2 | `.dash-sys-row { overflow: hidden }` + 3행 그리드 + 낮은 `min-height` | Row 1(identity)이 세그먼트·칩에 밀려 클리핑 |
| HF-2 | `grid-template-columns: 1fr auto auto auto` | `auto` 열(배지·CTA·chevron)이 넓을 때 identity `1fr` → 0px 수축 |
| HF-3 | `.dash-stats` 4열 그리드 + 타일 `min-height`/패딩 | 좁은 main 폭에서 4번째 열이 잘리거나 1열(`이상징후`)이 뷰포트 왼쪽 밖 |

### 1.3 범위

**In scope:**

- Zone A 히어로 레이아웃·KPI 호스트 최소 높이
- Zone B stats 그리드·타일 수축 규칙
- Zone C 카드 Row 1 identity 보호·overflow 정책
- Playwright **가시성(bounding box in viewport)** AC 강화

**Out of scope:**

- API·집계·`daily_dashboard.py`
- 사이드바·`base.html` 구조 변경
- UI-005 P2 기능 제거·축소 (segment, CTA, attention 유지)

---

## 2. 디자인·레이아웃 변경

### 2.1 HF-1 — 히어로 텍스트 항상 가시

#### 2.1.1 레이아웃 변경

**현행 (폐기):**

```text
grid-template-columns: 1fr auto;
align-items: end;
.dash-hero__text { min-width: 0; grid-row: 1 / 3; }
```

**신규:**

```text
┌─────────────────────────────────────────────────────────────┐
│ [오늘의 점검 현황]                         [통과율] [0 %]    │  ← Row 1 flex
│ [date · N/M · 갱신]                        [새로고침]       │  ← Row 2 flex
│ [summary 한 줄]                                              │  ← Row 3 (optional)
└─────────────────────────────────────────────────────────────┘
```

- `.dash-hero` → **단일 열 flex column** (grid 폐기)
- 내부 `.dash-hero__top` → `display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem`
  - 좌: `.dash-hero__text` (`flex: 1 1 auto; min-width: 12rem`)
  - 우: `.dash-hero__rate-block` (`flex: 0 0 auto`)
- `.dash-hero__bottom` → `display: flex; justify-content: space-between; align-items: center`
  - 좌: 비움 또는 summary만 (summary를 top text 아래에 두면 bottom은 actions만)
- **권장 단순화:** summary는 `dash-hero__text` 안에 유지, actions는 `dash-hero__top` 우측 하단에 `align-self: flex-end`가 아닌 **별도 행**으로:

```html
<section class="dash-hero">
  <div class="dash-hero__top">
    <div class="dash-hero__text">…title, meta, summary…</div>
    <div class="dash-hero__aside">
      <div class="dash-hero__rate-block">…</div>
      <div class="dash-hero__actions">…</div>
    </div>
  </div>
</section>
```

#### 2.1.2 CSS 규칙 (필수)

| 속성 | 값 | 이유 |
| --- | --- | --- |
| `.dash-hero__text` | `min-width: 12rem; flex: 1 1 12rem` | 1fr 수축 방지 |
| `.dash-hero__title` | `overflow: visible` | 클리핑 금지 |
| `#dash-host-kpi` | `min-height: clamp(7rem, 18cqh, 11rem); overflow: visible` | KPI 블록 최소 높이 보장 |
| `.dash-hero` | `align-items: stretch` (flex) | end 정렬 제거 |

#### 2.1.3 템플릿 (선택)

`zone_a_kpi.html` — 위 DOM 구조로 래퍼 추가. 기존 copy·Jinja 조건 **불변**.

---

### 2.2 HF-2 — 시스템 카드 Identity 항상 가시

#### 2.2.1 카드 그리드 재구성

**현행 Row 1:** `identity | badge | cta | chevron` (한 행 4열)  
**신규 Row 1:** **헤더 flex 한 줄**

```text
┌─ accent ───────────────────────────────────────────────────┐
│ [icon] [시스템명          ]     [badge] [CTA?] [›]         │  ← flex header
│ [segment bar ───────────────────────────────────────────]  │
│ [module chips ──────────────────────────────────────────]  │
└────────────────────────────────────────────────────────────┘
```

- `.dash-sys-row__header` (신규 wrapper) — `display: flex; align-items: center; gap: 0.5rem; min-height: 2.25rem; flex-shrink: 0`
  - `.dash-sys-row__identity` — `flex: 1 1 auto; min-width: 8rem; max-width: 55%`
  - `.dash-sys-row__badge` — `flex: 0 0 auto`
  - `.dash-sys-row__cta` — `flex: 0 0 auto`
  - `.dash-sys-row__chevron` — `flex: 0 0 auto; margin-left: auto` (CTA 없을 때도 우측 정렬)

**그리드 단순화:**

```css
.dash-sys-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  overflow: visible; /* hidden → visible; 클리핑은 modules 행만 */
}
.dash-sys-row__modules {
  overflow: hidden; /* 칩 말줄임만 여기 */
}
```

#### 2.2.2 Identity 최소 가시 규칙

| 요소 | 규칙 |
| --- | --- |
| `.dash-sys-row__icon` | `min-width: 1.75rem; min-height: 1.75rem` (density tier에서도) |
| `.dash-sys-row__name` | `min-width: 4ch` — 완전 0폭 금지 |
| `.dash-sys-row__meta` | `display: block` — `minimal`/`micro`에서도 유지 (축소만) |

#### 2.2.3 `_macros.html` 변경

`system_row` 매크로 — identity·badge·cta·chevron을 `.dash-sys-row__header`로 감싼다. segment·modules 순서 유지.

---

### 2.3 HF-3 — KPI 4타일 전부 뷰포트 내

#### 2.3.1 Stats 그리드

```css
.dash-stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  width: 100%;
  min-width: 0;
}

.dash-stats__tile {
  min-width: 0;           /* 균등 수축 허용 */
  padding: clamp(0.35rem, 1cqh, 1rem) clamp(0.35rem, 1cqi, 0.75rem);
}

.dash-stats__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

#### 2.3.2 좁은 main 폭 대응 (`main` content width < 42rem)

```css
@media (max-width: 900px) {
  .dash-stats__value {
    font-size: max(1rem, clamp(1rem, 2cqh, 1.5rem));
  }
  .dash-stats__label {
    font-size: 0.6875rem;
  }
}
```

#### 2.3.3 검증 기준

4타일 각각의 bounding box가 **main 콘텐츠 영역** (`document.querySelector('.dash').getBoundingClientRect()`) 안에 완전히 포함.

특히 **첫 타일** `.dash-stats__tile[data-tone="anomaly"]`의 `left >= dash.left`.

---

## 3. 기능 요구사항 (FR)

### FR-001: 히어로 텍스트 가시성 (HF-1)

1. `오늘의 점검 현황` — `opacity > 0`, `display` ≠ `none`, bounding width ≥ 120px, height ≥ 16px
2. `dash-hero__meta` — `date_label` 문자열 포함, 동일 가시성
3. 전체 미점검일 — `dash-hero__summary`에 `아직 점검이 시작되지 않았습니다` 표시
4. `통과율` 라벨·숫자 — 기존 UI-005 유지 (회귀 없음)

### FR-002: 시스템 Identity 가시성 (HF-2)

1. 모든 `.dash-sys-row`에서 `.dash-sys-row__icon`·`.dash-sys-row__name` 가시
2. 아이콘 bounding box width·height 각 ≥ 24px (`comfortable`~`dense`)
3. 시스템명 computed `font-size` ≥ 14px
4. `micro` tier에서도 시스템명·아이콘 **숨김 금지** (UI-005 재확인)

### FR-003: KPI 4타일 완전 노출 (HF-3)

1. 4타일 DOM 존재 (기존)
2. 4타일 모두 뷰포트(또는 `.dash` 박스) 내 완전 포함
3. 첫 타일 라벨 텍스트 `이상징후` 가시

### FR-004: 회귀 방지

UI-005에서 추가된 요소 유지: segment bar, glyph, CTA, chevron, attention strip, Zone C scroll.

---

## 4. API 계약

**변경 없음.**

---

## 5. 수용 기준 (AC)

### AC-001: 히어로 실가시 (HF-1) — Playwright

```gherkin
Given viewport 1280×720
  And sidebar visible (md breakpoint)
  And daily dashboard loaded with 6 systems, all not_inspected
When measuring getBoundingClientRect()
Then .dash-hero__title is visible
  And titleRect.width >= 120
  And titleRect.height >= 16
  And titleRect.top >= 0
  And titleRect.left >= sidebarWidth
  And .dash-hero__summary contains "아직 점검이 시작되지 않았습니다"
  And .dash-hero__rate-label is visible
```

### AC-002: Identity 실가시 (HF-2) — Playwright

```gherkin
Given viewport 1280×720, 6 systems loaded
When measuring first .dash-sys-row
Then .dash-sys-row__icon bounding width >= 24 and height >= 24
  And .dash-sys-row__name is visible
  And nameRect.width >= 40
  And parseFloat(getComputedStyle(name).fontSize) >= 14
  And iconRect.left >= rowRect.left
```

### AC-003: KPI 4타일 in-view (HF-3) — Playwright

```gherkin
Given viewport 1280×720, dashboard loaded
Then #dash-zone-stats .dash-stats__tile count is 4
  And for each tile, tileRect.right <= dashRect.right + 1
  And for each tile, tileRect.left >= dashRect.left - 1
  And first tile .dash-stats__label text is "이상징후"
  And first tile is visible
```

### AC-004: 문서 무스크롤 유지

```gherkin
Given AC-001~003 conditions
Then document.documentElement.scrollHeight <= window.innerHeight
```

### AC-005: Fragment 회귀

```gherkin
Given GET /api/dashboard/daily/fragments/kpi and matrix
Then existing SPEC-UI-005 fragment assertions still pass
  And HTML contains dash-hero__top or dash-hero__header structure (new wrapper)
  And HTML contains dash-sys-row__header
```

---

## 6. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | CSS-only + 최소 템플릿 래퍼 — JS 변경 없음 (density 로직 유지) |
| NFR-002 | `dashboard.css?v=3` cache bust |
| NFR-003 | 한국어 copy 불변 |
| NFR-004 | Playwright AC는 **DOM 존재**가 아닌 **bounding box in viewport** assert |

---

## 7. 테스트 요구사항

| 파일 | 추가 내용 |
| --- | --- |
| `tests/test_dashboard_viewport.py` | AC-001~004 — `getBoundingClientRect` 기반 |
| `tests/test_dashboard_fragments_http.py` | AC-005 — `dash-hero__top`, `dash-sys-row__header` 존재 |

**수동 QA (필수):** 사이드바·1280×720·전체 미점검 데이터에서 스크린샷 — 제목·이상징후 타일·HOM 아이콘/이름 확인.

---

## 8. 구현 파일 맵

| 파일 | 변경 |
| --- | --- |
| `zone_a_kpi.html` | `.dash-hero__top` / `.dash-hero__aside` 래퍼 |
| `_macros.html` | `.dash-sys-row__header` 래퍼 |
| `dashboard.css` | HF-1~3 CSS; hero flex; card flex column; stats minmax |
| `dashboard.html` | `dashboard.css?v=3` |
| `tests/test_dashboard_viewport.py` | bounding box AC |

### 8.1 CSS 스케치 (핵심)

```css
#dash-host-kpi {
  min-height: clamp(7rem, 18cqh, 11rem);
  overflow: visible;
}

.dash-hero__top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.dash-hero__text {
  flex: 1 1 12rem;
  min-width: 12rem;
}

.dash-hero__aside {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.35rem;
}

.dash-sys-row {
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.dash-sys-row__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 2.25rem;
  flex-shrink: 0;
}

.dash-sys-row__identity {
  flex: 1 1 auto;
  min-width: 8rem;
  max-width: 55%;
}

.dash-stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
```

---

## 9. UI-005 대비 변경 요약

| UI-005 | UI-006 |
| --- | --- |
| Hero CSS grid 2열 | Hero flex `__top` / `__aside` |
| Card CSS grid 3행 | Card flex column + `__header` flex |
| `.dash-sys-row overflow: hidden` | `overflow: visible` (modules만 hidden) |
| Playwright `is_visible()` only | `getBoundingClientRect` in-view assert |
| `#dash-host-kpi` 높이 무제한 | `min-height` 보장 |

---

## 10. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 초안 — 실화면 회귀 3건 핫픽스 | AI |
