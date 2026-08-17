# SPEC-UI-008: 일간 대시보드 — 사이드바 셸 인셋 (본문 가림 교정)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-008` |
| **상태** | `approved` |
| **우선순위** | P0 (가시성·레이아웃 회귀) |
| **의존** | `SPEC-UI-004` §3.1, `SPEC-UI-006` AC-001, `SPEC-UI-007` |
| **대체·수정** | `SPEC-UI-004` §3.1 구현 누락 보완, `SPEC-UI-007` Out of scope "사이드바 리디자인"과 무관 — **셸 인셋만** |
| **증거** | `research/dashboard-sidebar-overlap-orca.png` (Orca 브라우저 실화면, 2026-08-15) |
| **구현 위치** | `app/web/static/dashboard.css`, `tests/test_dashboard_viewport.py` |

## 1. 개요

### 1.1 문제 (실화면 확인)

Orca 브라우저(`http://127.0.0.1:2222/`, 1280×720)에서 **좌측 고정 사이드바(`#app-sidebar`, `w-64` = 16rem)가 대시보드 본문(`.dash`) 위에 겹쳐** 우측 콘텐츠 좌측이 잘려 보인다.

**관찰된 증상:**

| 영역 | 증상 |
| --- | --- |
| Zone A Hero | 제목·메타·통과율 블록 좌측이 사이드바 뒤로 숨음 |
| Zone B KPI | 첫 타일(이상징후)이 사이드바에 가려져 라벨·숫자 일부 비가시 |
| Zone C 카드 | 시스템 아이콘·이름·모듈 칩 시작점이 사이드바 아래로 들어감 |
| 가로 스크롤 | 없음 — 콘텐츠가 **클리핑**되어 정보 손실 |

### 1.2 근본 원인

`base.html`은 데스크톱에서 `main`에 Tailwind `md:pl-64`(padding-left: 16rem)로 사이드바 폭만큼 본문을 밀어낸다.

```html
<main class="md:pl-64">
```

그러나 `dashboard.css`의 viewport-fit 셸 규칙이 **shorthand `padding: 0`** 으로 `main`·`main > div`의 **모든 패딩을 제거**하여 `md:pl-64`를 무효화한다.

```css
/* 현재 — 문제 */
body:has(.dash) main,
body:has(.dash) main > div {
  max-width: none;
  padding: 0;   /* ← padding-left: 16rem 제거 */
  height: 100dvh;
  overflow: hidden;
}
```

`#app-sidebar`는 `position: fixed`이므로, `main`에 좌측 인셋이 없으면 `.dash`는 뷰포트 x=0부터 그려지고 사이드바에 **물리적으로 가려진다**.

`SPEC-UI-004` §3.1은 가용 폭을 `100vw − 16rem`으로 정의했으나, 구현이 이를 만족하지 못하는 **셸 인셋 회귀**다.

### 1.3 목적

데스크톱(≥768px)에서 대시보드 본문이 **사이드바 오른쪽 가용 영역에만** 배치되도록 셸 CSS를 교정한다. 사이드바 디자인·메뉴 항목 변경은 범위 밖.

### 1.4 핵심 원칙 — Shell inset, don’t overlap

| 원칙 | 설명 |
| --- | --- |
| **Respect fixed sidebar** | `fixed` 사이드바 폭(16rem)만큼 `main` 콘텐츠 시작점을 오른쪽으로 이동 |
| **Targeted padding reset** | `padding: 0` shorthand 금지 — 세로·우측만 0, **좌측 인셋 유지** |
| **No 100vw bleed** | `.dash`는 `main` 콘텐츠 박스 안에서 `width: 100%` — 뷰포트 전체 폭 사용 금지 |
| **Mobile unchanged** | `<768px`에서 사이드바는 오버레이 드로어 — `padding-left: 0` 유지 |

---

## 2. 가용 영역 (SSOT 재확인)

`SPEC-UI-004` §3.1 / `SPEC-UI-007` §2와 동일:

| 조건 | content box left | content box width | height |
| --- | --- | --- | --- |
| `≥ 768px` | `16rem` (sidebar right edge) | `100vw − 16rem` | `100dvh` |
| `< 768px` | `0` | `100vw` | `100dvh − 3.25rem` |

**불변식 (데스크톱):**

```text
.dash.left  >=  #app-sidebar.right  (±1px 반올림)
.dash.width <=  innerWidth - sidebarWidth
```

---

## 3. CSS 요구사항

### 3.1 `main` 패딩 — shorthand 제거

```css
body:has(.dash) main,
body:has(.dash) main > div {
  max-width: none;
  padding-top: 0;
  padding-right: 0;
  padding-bottom: 0;
  /* padding-left: 아래 미디어쿼리에서만 설정 */
  height: 100dvh;
  overflow: hidden;
  box-sizing: border-box;
}

@media (min-width: 768px) {
  body:has(.dash) main {
    padding-left: 16rem; /* = Tailwind w-64 / md:pl-64 */
    width: 100%;
  }

  body:has(.dash) main > div {
    padding-left: 0;
    width: 100%;
    max-width: none;
  }
}

@media (max-width: 767px) {
  body:has(.dash) main,
  body:has(.dash) main > div {
    padding-left: 0;
    width: 100%;
  }
}
```

**금지:**

```css
padding: 0; /* main에 shorthand 사용 금지 — pl-64 재삭제됨 */
width: 100vw; /* main 또는 .dash에 금지 */
```

### 3.2 `.dash` 폭 수납

```css
.dash {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  /* 기존 height/flex/overflow 규칙 유지 (UI-007) */
}
```

### 3.3 z-index 변경 금지

사이드바·본문 겹침을 `z-index`로 "해결"하지 않는다. **레이아웃 인셋**이 정답.

---

## 4. 기능 요구사항 (FR)

### FR-001: 데스크톱 인셋

1. `≥768px`에서 `.dash.getBoundingClientRect().left >= #app-sidebar.getBoundingClientRect().right - 1`
2. `main` computed `padding-left` = `256px` (16rem, root font 16px 기준)
3. 사이드바와 본문 **픽셀 겹침 없음** (`overlapPx === 0`)

### FR-002: 가용 폭 준수

1. `.dash.width <= innerWidth - sidebarWidth + 1`
2. 가로 문서 스크롤 없음 (`scrollWidth <= innerWidth`)

### FR-003: UI-006/007 회귀 없음

1. 문서·Zone C 무스크롤 (UI-007 AC-001~003)
2. 히어로·KPI·identity bounding box in `.dash` (UI-006)
3. `titleRect.left >= sidebarWidth` (UI-006 AC-001 — 본 Spec에서 **강제**)

### FR-004: 모바일

1. `<768px`에서 `main.padding-left === 0`
2. 모바일 헤더 아래 본문 높이 규칙 유지 (UI-007)

---

## 5. API 계약

**변경 없음.**

---

## 6. 수용 기준 (AC)

### AC-001: 사이드바-본문 비겹침 (Playwright)

```gherkin
Given viewport 1280×720
  And dashboard loaded with 6 systems
When measuring getBoundingClientRect()
Then #app-sidebar.right <= .dash.left + 1
  And overlapPx between sidebar and .dash equals 0
```

**evaluate 스니펫:**

```javascript
() => {
  const sb = document.querySelector('#app-sidebar');
  const dash = document.querySelector('.dash');
  const sr = sb.getBoundingClientRect();
  const dr = dash.getBoundingClientRect();
  return {
    dashLeft: dr.left,
    sidebarRight: sr.right,
    overlapPx: Math.max(0, sr.right - dr.left),
    ok: dr.left >= sr.right - 1,
  };
}
```

### AC-002: main padding-left 복원

```gherkin
Given viewport 1280×720
Then getComputedStyle(main).paddingLeft is "256px" (or 16rem computed)
```

### AC-003: 히어로·KPI 좌측 가시 (UI-006 강화)

```gherkin
Given viewport 1280×720
Then .dash-hero__title.left >= sidebarWidth
  And first .dash-stats__tile.left >= sidebarWidth
  And first .dash-stats__tile label "이상징후" is fully visible
```

### AC-004: 시스템 identity 좌측 가시

```gherkin
Given first .dash-sys-row
Then .dash-sys-row__icon.left >= sidebarWidth
  And .dash-sys-row__name.left >= sidebarWidth
```

### AC-005: 모바일 인셋 없음

```gherkin
Given viewport 390×844
Then getComputedStyle(main).paddingLeft is "0px"
  And .dash.left is approximately 0
```

### AC-006: UI-007 무스크롤 회귀

```gherkin
Given viewports 1280×720 and 320×568
Then UI-007 AC-001 and AC-002 still pass
```

---

## 7. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | CSS 변경은 `dashboard.css`만 — `base.html` Tailwind 클래스 구조 유지 |
| NFR-002 | `dashboard.css?v=5` cache bust |
| NFR-003 | E2E: Orca 브라우저 스크린샷으로 AC-001 육안 확인 |
| NFR-004 | Playwright AC는 `tests/test_dashboard_viewport.py`에 `@pytest.mark.spec("SPEC-UI-008", ...)` |

---

## 8. 테스트 요구사항

| 유형 | 파일 | 내용 |
| --- | --- | --- |
| Playwright | `tests/test_dashboard_viewport.py` | AC-001~006 |
| E2E | e2e-browser skill | Orca 스크린샷 — 히어로·KPI 첫 타일·첫 카드 identity가 사이드바 오른쪽에서 시작 |

### 8.1 E2E 체크리스트

```text
E2E-INSET-1: .dash 좌측이 사이드바 우측과 맞닿거나 그 오른쪽에서 시작
E2E-INSET-2: "오늘의 점검 현황" 전체 문자열 가시
E2E-INSET-3: KPI 첫 타일 "이상징후" 라벨 가시
E2E-INSET-4: 첫 시스템 카드 아이콘·이름 가시
```

---

## 9. 구현 파일 맵

| 파일 | 변경 |
| --- | --- |
| `app/web/static/dashboard.css` | `padding: 0` → targeted reset + `md` `padding-left: 16rem`; `.dash width: 100%` |
| `app/web/templates/dashboard.html` | `dashboard.css?v=5` |
| `tests/test_dashboard_viewport.py` | AC-001~005 신규 |

---

## 10. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 초안 — Orca 실화면 사이드바 가림, `padding:0` 회귀 원인·교정 SSOT | AI |
