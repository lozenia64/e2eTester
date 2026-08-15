# SPEC-UI-005: 일간 대시보드 — 정보 위계·가독성 폴리시 (P0–P2)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-UI-005` |
| **상태** | `approved` (가시성 핫픽스는 `SPEC-UI-006`이 §3.1·§3.2·§3.3·AC 우선) |
| **우선순위** | P0 (위계 복구) + P1 (카드·타이포) + P2 (예외 우선·인터랙션) |
| **의존** | `SPEC-UI-001`, `SPEC-UI-004` |
| **대체·수정** | `SPEC-UI-004` §2.1·§3.1·§3.2·§3.4·FR-001·FR-003·FR-004·AC-001~005 (본 Spec이 우선) |
| **SSOT 링크** | `docs/specs/dashboard/01-daily-dashboard.md`, `app/contexts/insights/application/daily_dashboard.py` |
| **구현 위치** | `app/web/static/dashboard.css`, `app/web/static/dashboard.js`, `app/web/templates/dashboard/partials/zone_a_kpi.html`, `app/web/templates/dashboard/partials/_macros.html`, `tests/test_dashboard_viewport.py` (신규 AC) |

## 1. 개요

### 1.1 목적

`SPEC-UI-004` Premium Light 구현 후 실사용·스크린샷 검토에서 드러난 **정보 위계 붕괴**(히어로 타이틀 소실, 시스템 정체성 미가시, 카드 내 빈 공간 과다, 상태 단조로움)를 한 번에 교정한다.

목표: **5초 안에** (1) 오늘 전체 상태, (2) 주의가 필요한 시스템, (3) 각 시스템의 모듈 진행을 스캔할 수 있는 **Editorial clarity** 수준의 랜딩 대시보드.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `operator` | 일반 사용자 — 본 Spec의 주 소비자 |
| `admin` | `/` 리다이렉트 정책 불변 (`SPEC-UI-001`) |

### 1.3 범위

**In scope:**

- Zone A 히어로 레이아웃·카피·타이포 재설계
- Zone B KPI 스트립 가시성·라벨 강화
- Zone C 시스템 카드 2행 구조·높이 모델 변경·진행 세그먼트 바
- Attention strip 노출 정책 완화·인박스 연결
- 모듈 칩 상태 글리프·타이포 하한선
- 카드 elevation·chevron·미점검 CTA
- Density tier 임계값·`micro` 축소 범위 조정
- Playwright·단위 테스트 보강

**Out of scope:**

- `/api/dashboard/daily` 응답 스키마·집계 규칙 (`daily_dashboard.py` 불변)
- 사이드바·`base.html` 전역 리디자인
- 다크 모드
- Cytoscape 복원

### 1.4 우선순위 매핑 (구현 체크리스트)

| ID | 항목 | Spec 절 |
| --- | --- | --- |
| **P0-1** | 히어로 타이틀·메타·통과율 라벨 항상 가시 | §3.1, FR-001 |
| **P0-2** | 시스템 카드 Identity(아이콘·이름·N/M) 최소 가독성 보장 | §3.3, FR-003 |
| **P0-3** | KPI 4타일 항상 노출·라벨 대비 강화 | §3.2, FR-002 |
| **P1-1** | 카드 균등 늘리기 제거 → 콘텐츠 기반 높이 + Zone C 내부 스크롤 | §3.4, FR-004 |
| **P1-2** | 카드 2행 레이아웃(헤더 / 모듈) | §3.3 |
| **P1-3** | 모듈 세그먼트 진행 바(`comfortable`~`dense`) | §3.3, FR-003 |
| **P1-4** | 타이포 하한선(12px 칩 / 13px 본문) | §2.2 |
| **P2-1** | 예외 시스템 시각 강조(좌측 액센트·정렬 유지) | §3.3, FR-003 |
| **P2-2** | Attention strip 우선 노출·인박스 링크 | §3.5, FR-005 |
| **P2-3** | 카드 hover elevation·chevron·전체 미점검 CTA | §3.3, FR-006 |
| **P2-4** | 모듈 칩 상태 글리프(색맹 보조) | §3.6, FR-003 |

---

## 2. 디자인 시스템 변경

### 2.1 원칙 (SPEC-UI-004 보강)

| 원칙 | 변경 |
| --- | --- |
| **Editorial clarity** | 통과율 숫자 단독 노출 금지 — 반드시 `통과율` 라벨 + 맥락 문장 동반 |
| **Identity first** | 시스템명이 모듈 칩보다 시각적으로 우위 (weight·size) |
| **Exceptions first** | attention·error·anomaly·running 시스템은 카드 좌측 3px 액센트 + 상단 고정(기존 정렬 유지) |
| **Scroll with dignity** | 문서 스크롤은 금지 유지; **Zone C만** `overflow-y: auto` 허용 (fade mask) |

### 2.2 색상·토큰 (추가)

```text
--pl-accent:       #6366f1          /* 사이드바 선택 톤과 동일 indigo — 히어로 링·CTA */
--pl-shadow-sm:    0 1px 3px rgb(0 0 0 / 0.06), 0 1px 2px rgb(0 0 0 / 0.04)
--pl-shadow-md:    0 8px 30px -8px rgb(0 0 0 / 0.12)
--pl-accent-bar:   3px solid       /* 시스템 카드 좌측, tone별 --st-* */
```

기존 `--st-*` 팔레트·`--pl-text*` 는 `SPEC-UI-004` §2.2 유지.

### 2.3 타이포그래피 하한선 (신규 — `cqh` clamp에도 적용)

| 역할 | 최소 크기 | 최대·fluid | 비고 |
| --- | --- | --- | --- |
| Page title | **16px** (`1rem`) | `clamp(1rem, 3cqh, 2rem)` | `dash-hero__title` |
| Hero meta | **12px** | `clamp(0.75rem, 1.4cqh, 0.875rem)` | 날짜·갱신 시각 |
| Pass rate label | **11px** | `0.6875rem` 고정 uppercase | `통과율` eyebrow |
| Pass rate value | **40px** | `clamp(2.5rem, 5cqh, 4rem)` | micro에서만 축소 |
| Stat value | **20px** | `clamp(1.25rem, 2.5cqh, 2rem)` | KPI 숫자 |
| Stat label | **12px** | `clamp(0.75rem, 1.2cqh, 0.8125rem)` | |
| System name | **14px** | `clamp(0.875rem, 1.8cqh, 1rem)` | **절대 숨기지 않음** (`micro`에서도 표시) |
| System meta | **12px** | `clamp(0.75rem, 1.2cqh, 0.8125rem)` | |
| Module chip | **12px** | `clamp(0.75rem, 1.4cqh, 0.8125rem)` | |
| Badge | **12px** | `clamp(0.75rem, 1.2cqh, 0.8125rem)` | |

**규칙:** `font-size`에 `clamp()`를 쓸 때 **두 번째 인자(cqh)가 하한선보다 작아져도** CSS `max()`로 하한을 강제한다.

```css
font-size: max(0.75rem, clamp(0.6rem, 1.4cqh, 0.8125rem));
```

### 2.4 모션 (변경 없음 + 보강)

- `prefers-reduced-motion`: 기존 `SPEC-UI-004` §2.4 준수
- Zone C 스크롤 fade mask: 정적 그라데이션 (애니메이션 없음)

---

## 3. 레이아웃

### 3.1 Zone A — Hero (재설계)

**레이아웃:** 3열 그리드 폐기 → **2행 스택 + 우측 통과율 블록**

```text
┌──────────────────────────────────────────────────────────────┐
│ Row 1: [오늘의 점검 현황]                    [통과율]          │
│        [date · N/M 모듈 정상 · 갱신 HH:MM]   [  0  %]        │
│        [맥락 한 줄 요약 — 조건부]              [새로고침]      │
├──────────────────────────────────────────────────────────────┤
│ Row 2: Zone B stats (4 tiles)                                │
│ Row 2b: Attention strip (조건부)                             │
└──────────────────────────────────────────────────────────────┘
```

**Grid CSS (데스크톱):**

```text
grid-template-columns: 1fr auto;
grid-template-rows: auto auto;
```

- 좌측 `dash-hero__text`: `min-width: 0`, `grid-column: 1`, `grid-row: 1 / 3` (통과율 블록과 세로 정렬)
- 우측 `dash-hero__rate-block`: `grid-column: 2`, `grid-row: 1` — 라벨 `통과율` + 숫자 + `%`
- `dash-hero__actions`: `grid-column: 2`, `grid-row: 2`, `justify-self: end`

**필수 DOM (`zone_a_kpi.html`):**

```html
<div class="dash-hero__rate-block">
  <span class="dash-hero__rate-label">통과율</span>
  <div class="dash-hero__rate-wrap">…</div>
</div>
<p class="dash-hero__summary" data-empty-state>…</p>  <!-- 조건부 -->
```

**맥락 한 줄 요약 (`dash-hero__summary`) — 서버 렌더 조건:**

| 조건 | 문구 |
| --- | --- |
| `totals.not_inspected === totals.modules` && `totals.modules > 0` | `오늘 아직 점검이 시작되지 않았습니다.` |
| `totals.error > 0` | `점검실패 {error}건 — 우선 확인이 필요합니다.` |
| `totals.anomaly > 0` | `이상징후 {anomaly}건이 감지되었습니다.` |
| `totals.running > 0` | `{running}개 모듈이 진행 중입니다.` |
| 그 외 (전부 정상) | `오늘 점검이 정상적으로 완료되었습니다.` |
| `totals.modules === 0` | 요소 미렌더 (`hidden`) |

우선순위: `error > anomaly > running > all_not_inspected > all_passed`.

**가시성 AC:** 뷰포트 1280×720·사이드바 표시 시 `오늘의 점검 현황` 텍스트 bounding box 높이 ≥ 16px, 너비 ≥ 120px (Playwright assert).

### 3.2 Zone B — Stats strip (강화)

- 4타일 **항상 렌더** (`이상징후` 값 0이어도 숨기지 않음)
- 타일 구조: **라벨 위 · 숫자 아래** → **숫자 위 · 라벨 아래** (현행 유지) + 라벨 `font-weight: 700`
- 값 0인 타일도 tone 색 유지 (회색으로 뭉개지 않음)
- 타일 `min-height: 56px` (micro tier에서만 `44px`)

### 3.3 Zone C — 시스템 카드 (2행 구조)

**행 높이 모델 변경 (`SPEC-UI-004` §3.2 폐기):**

```text
.dash-sys-row {
  flex: 0 0 auto;              /* 균등 분할 금지 */
  min-height: var(--dash-row-min-h);
}
.dash__systems {
  flex: 1 1 auto;
  overflow-y: auto;            /* 유일한 세로 스크롤 허용 영역 */
  overflow-x: hidden;
  mask-image: linear-gradient(...);  /* 하단 fade — 스크롤 가능 시만 */
}
```

**`--dash-row-min-h` by density:**

| tier | min-height |
| --- | --- |
| comfortable | 88px |
| compact | 76px |
| dense | 64px |
| minimal | 56px |
| micro | 48px |

**카드 내부 그리드 (데스크톱):**

```text
┌─ accent bar ─────────────────────────────────────────────┐
│ Row A: [icon + name + meta]              [badge] [›]   │
│ Row B: [segment bar ────────────────────]  (optional)   │
│ Row C: [module chips ─ scroll/clamp ────]               │
└────────────────────────────────────────────────────────┘
```

| 영역 | 표시 tier | 설명 |
| --- | --- | --- |
| Row A | 전 tier | Identity + badge + chevron |
| Row B segment bar | comfortable · compact · dense | §3.3.1 |
| Row C chips | comfortable · compact (`dense`는 chips+bar 병행) | `minimal`·`micro`는 chips→dots (`UI-004` 유지) |

**Identity 열 최소 너비:** `minmax(11rem, 18rem)` (기존 7rem 상향).

**좌측 tone 액센트 바 (P2-1):**

```css
.dash-sys-row[data-priority="attention"] {
  border-left: 3px solid var(--accent-tone);
  padding-left: calc(... - 3px);
}
```

`data-priority="attention"` 조건: 시스템 대표 badge tone ∈ `{error, anomaly, running, waiting_input, blocked}`.

**Chevron (P2-3):**

- `.dash-sys-row__chevron` — `›` 또는 SVG, `opacity: 0.35` 기본 → hover `0.7`
- `aria-hidden="true"` (행 전체가 이미 button 역할)

**전체 미점검 CTA (P2-3):**

- 조건: 해당 시스템 `badge.tone === 'not_inspected'` && `inspected === 0`
- Row A badge 옆 링크: `점검 실행` → `/runs/execute` (클릭 시 `stopPropagation`)

#### 3.3.1 모듈 세그먼트 진행 바

**매크로:** `module_segment_bar(sys)` in `_macros.html`

- `sys.modules` 순서대로 1px gap 없는 flex segment
- 각 segment `flex: 1`, `height: 4px` (compact `3px`), `border-radius: 2px`
- segment `data-tone` = module tone
- `title` = `{module.name} · {status_label}`
- segment 클릭: `run_id` 있으면 `/runs/{id}` (`stopPropagation`)

**표시:** `data-density` ∈ `{comfortable, compact, dense}`.

### 3.4 Density tier (수정)

**임계값:** Zone C **콘텐츠 높이 합**과 **가용 높이** 비교로 전환 (행 균등 높이 기반 폐기).

```javascript
const contentH = container.scrollHeight;
const availH = container.clientHeight;
const needsScroll = contentH > availH + 1;
container.dataset.scrollable = needsScroll ? "true" : "false";

// tier는 "가장 작은 tier부터 시도" → scrollHeight <= clientHeight 될 때까지
// 또는 viewport 높이 기반 단일 계산:
const tier = computeTierFromViewport(root.clientHeight, systemCount);
```

**권장 알고리즘 (`dashboard.js`):**

1. `systemCount` = N
2. 뷰포트 높이·고정 Zone A+B(+attention) 높이를 빼서 `zoneCAvail` 계산
3. `requiredH = N * rowMinH[tier] + gaps` 를 tier `comfortable`→`micro` 순으로 검사
4. `requiredH <= zoneCAvail` 인 **가장 큰(여유 있는) tier** 선택
5. 그래도 초과 시 선택 tier 유지 + `data-scrollable="true"`

| tier | rowMinH |
| --- | --- |
| comfortable | 88 |
| compact | 76 |
| dense | 64 |
| minimal | 56 |
| micro | 48 |

**`micro` 변경:** `dash-sys-row__name` **숨기지 않음**. 대신 meta·segment bar·chip label만 축소.

### 3.5 Attention strip (노출 정책 완화)

**기존 (`UI-004` FR-004):** 남는 공간 < 80px → 숨김.

**변경:**

1. `data.attention.length > 0` 이면 **기본 표시** (`hidden` attribute 제거)
2. 공간 부족 시: KPI strip 하단 **고정 1행**으로 유지; overflow는 **말줄임 + "+N건"** (스크롤 없음)
3. `micro` tier에서도 attention **숨기지 않음** (대신 1건만 + "+N건")
4. strip 우측 링크: `전체 보기` → `/anomalies` (이상징후 인박스)
5. 각 item 클릭 시: `run_id` 있으면 Run 상세, 없으면 해당 시스템 드로어 open

**JS:** `toggleAttentionStrip()` — 높이 부족 시 숨김 로직 **삭제**. 대신 `dash-attention--compact` 클래스로 패딩·폰트만 축소.

### 3.6 모듈 칩 상태 글리프 (P2-4)

칩 텍스트 앞 1글자 아이콘 (Unicode, 추가 요청 없음):

| tone | 글리프 | aria |
| --- | --- | --- |
| passed | `✓` | `aria-label`에 기존 status 유지 |
| anomaly | `!` | |
| error | `×` | |
| running / waiting_input | `●` (pulse) | |
| not_inspected / pending | `○` | |
| blocked / skipped / cancelled | `—` | |

`.dash-mod__glyph` — `font-size: 0.85em`, `opacity: 0.9`. 색상은 tone 유지.

---

## 4. 기능 요구사항 (FR)

### FR-001: 히어로 맥락 복구 (P0)

**설명:** 통과율·제목·요약이 항상 함께 보인다.

**비즈니스 규칙:**

1. `통과율` 라벨 필수 (한국어, uppercase optional)
2. `generated_at` 은 meta 줄에 항상 표시 (없으면 생략)
3. `dash-hero__summary` 우선순위는 §3.1 표 준수
4. 카운트업 대상: `.dash-hero__rate[data-target]` 만 (라벨·summary 제외)

### FR-002: KPI 4타일 가시성 (P0)

**설명:** 이상징후 0건이어도 타일 제거 금지.

### FR-003: 시스템 카드 정체성·진행 (P0 + P1 + P2)

**설명:** 2행 카드 + segment bar + accent + chevron + CTA.

**비즈니스 규칙:**

1. 정렬: `sort_systems_attention_first` 결과 순서 유지 (API 불변)
2. 시스템명 ellipsis 허용, **display:none 금지**
3. 모듈 pill overflow: Row C `overflow-x: auto` **금지** — `overflow: hidden` + ellipsis; 넘친 수는 segment bar hover로 보완
4. `minimal`/`micro`: segment bar 숨김, module dots 유지

### FR-004: Zone C 스크롤 (P1)

**설명:** 문서 무스크롤 유지, Zone C만 내부 스크롤.

**비즈니스 규칙:**

1. `html`, `body`, `.dash` — `overflow: hidden` 유지
2. `.dash__systems` — `overflow-y: auto`, `-webkit-overflow-scrolling: touch`
3. `data-scrollable="false"` 일 때 fade mask 비활성
4. 키보드: Zone C에 `tabindex="0"` + focus 시 스크롤 가능 (선택)

### FR-005: Attention strip (P2)

**설명:** §3.5.

### FR-006: 인터랙션 보강 (P2)

**설명:**

1. 카드 hover: `box-shadow: var(--pl-shadow-md)`, `translateY(-1px)` (reduced-motion 제외)
2. 카드 기본: `box-shadow: var(--pl-shadow-sm)`
3. 모듈 링크 hover: `filter: brightness(0.95)` 또는 배경 10% 어둡게
4. 행 클릭·pill 클릭·CTA·segment 클릭 분리 (`stopPropagation` 기존 패턴 유지)

---

## 5. API 계약

**변경 없음.** `SPEC-UI-001` / `SPEC-UI-004` §5 동일.

**템플릿 전용 파생 필드 (클라이언트 계산 금지):**

| 필드 | 위치 | 계산 |
| --- | --- | --- |
| `dash-hero__summary` | `zone_a_kpi.html` | §3.1 Jinja 조건 |
| `data-priority` | `_macros.html` `system_row` | badge tone |
| segment bar | `_macros.html` | `sys.modules` |

---

## 6. `SPEC-UI-004` 명시적 폐기 항목

| UI-004 조항 | UI-005 처리 |
| --- | --- |
| §3.1 "모든 뷰포트 무스크롤" (절대) | **문서** 무스크롤; Zone C 내부 스크롤 허용 |
| §3.2 Zone C "N등분 flex 행" | 콘텐츠 높이 + min-height |
| §3.4 `micro` attention 숨김 | 항상 1행 compact 표시 |
| §3.4 `micro` system name 숨김 | **폐기** — 항상 표시 |
| FR-004 공간 < 80px attention 숨김 | **폐기** → compact 1행 |

---

## 7. 수용 기준 (AC)

### AC-001: 히어로 가시성 (P0)

```gherkin
Given viewport 1280×720 and sidebar visible
  And daily dashboard loaded with 6 systems
Then element ".dash-hero__title" is visible
  And its text is "오늘의 점검 현황"
  And element ".dash-hero__rate-label" is visible
  And its text is "통과율"
  And element ".dash-hero__meta" contains data.date_label
```

### AC-002: 빈 점검일 맥락 문구 (P0)

```gherkin
Given totals.pass_rate is 0
  And totals.not_inspected equals totals.modules
  And totals.modules > 0
When kpi fragment rendered
Then ".dash-hero__summary" text contains "아직 점검이 시작되지 않았습니다"
```

### AC-003: 시스템 정체성 (P0)

```gherkin
Given system card for "hom" in matrix fragment
Then ".dash-sys-row__name" is visible
  And its computed font-size >= 14px
  And ".dash-sys-row__icon" is visible
```

### AC-004: KPI 4타일 (P0)

```gherkin
Given totals.anomaly is 0
When kpi fragment rendered
Then "#dash-zone-stats .dash-stats__tile" count is 4
  And first tile label is "이상징후"
```

### AC-005: Zone C 내부 스크롤·문서 무스크롤 (P1)

```gherkin
Given viewport 1280×720 and 6 systems
When dashboard loaded
Then document.documentElement.scrollHeight <= window.innerHeight
  And element ".dash__systems" has overflow-y auto
When all system cards total height exceeds zone C client height
Then ".dash__systems" dataset.scrollable is "true"
  And document still has no scrollbar
```

### AC-006: 카드 빈 공간 (P1)

```gherkin
Given viewport 1920×1080 and 6 systems at comfortable tier
When measuring any ".dash-sys-row"
Then row clientHeight is less than or equal to 120px
  And row clientHeight is greater than or equal to 88px
  And unused vertical space inside row (clientHeight - contentHeight) is less than 24px
```

### AC-007: Segment bar (P1)

```gherkin
Given density is comfortable
  And system has 3 modules
Then ".dash-sys-row__segment" exists
  And it has 3 child segments
```

### AC-008: Attention 노출 (P2)

```gherkin
Given data.attention has 4 items
  And viewport 320×568
When dashboard loaded
Then "#dash-zone-attention" is visible
  And it contains link to anomaly inbox
  And at most 1 attention item row is fully expanded (others +N건)
```

### AC-009: 예외 accent (P2)

```gherkin
Given system with representative badge tone "error"
Then its ".dash-sys-row" has data-priority "attention"
  And border-left-width is 3px
```

### AC-010: 접근성 (P2)

```gherkin
Given prefers-reduced-motion: reduce
When dashboard loads
Then module chips contain ".dash-mod__glyph" visible without hover
  And status is not conveyed by color alone (glyph + text)
```

### AC-011: 집계 불변 (회귀)

```gherkin
Given SPEC-UI-001 AC-001, AC-002
When UI-005 dashboard rendered
Then API responses and module tones unchanged
```

---

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | PII-free 불변 |
| NFR-002 | 추가 JS < 2KB gzip (density 알고리즘 교체) |
| NFR-003 | HTMX fragment 호환 — zone ID·endpoint 불변 |
| NFR-004 | 한국어 UI 문자열 |
| NFR-005 | `prefers-reduced-motion` 준수 |
| NFR-006 | Playwright: `320×568`, `1280×720`, `1920×1080` — AC-001·005·008 assert |

---

## 9. 테스트 요구사항

| 유형 | 파일 | 내용 |
| --- | --- | --- |
| 단위 | `tests/test_daily_dashboard.py` | 불변 |
| HTTP fragment | `tests/test_dashboard_fragments_http.py` | kpi에 summary·4 tiles; matrix에 segment·chevron DOM |
| Viewport | `tests/test_dashboard_viewport.py` | AC-001, AC-005, AC-006 추가 |
| 수동 | §10 체크리스트 | 실제 브라우저 스크린샷 회귀 |

---

## 10. 구현 파일 맵

| 구성요소 | 파일 | 변경 요약 |
| --- | --- | --- |
| Hero+summary | `zone_a_kpi.html` | rate-block, summary Jinja, 레이아웃 |
| Macros | `_macros.html` | `module_segment_bar`, `system_row` 2행, chevron, CTA, glyph |
| Matrix | `zone_b_matrix.html` | 변경 없거나 macro 호출만 |
| Style | `dashboard.css` | hero grid, row 2-line, tokens, scroll, accent, shadows |
| Logic | `dashboard.js` | density 알고리즘, attention toggle 단순화, scrollable flag |
| Cache bust | `dashboard.html` | `dashboard.css?v=2`, `dashboard.js?v=15` |

### 10.1 CSS 스케치 (핵심)

```css
.dash-hero {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  align-items: end;
  gap: 0.5rem 1.25rem;
}

.dash-hero__rate-label {
  display: block;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--pl-text-muted);
}

.dash-sys-row {
  flex: 0 0 auto;
  min-height: var(--dash-row-min-h, 88px);
  display: grid;
  grid-template-columns: 1fr auto auto;
  grid-template-rows: auto auto auto;
  box-shadow: var(--pl-shadow-sm);
}

.dash-sys-row__identity { grid-column: 1; grid-row: 1; }
.dash-sys-row__badge { grid-column: 2; grid-row: 1; }
.dash-sys-row__chevron { grid-column: 3; grid-row: 1; }
.dash-sys-row__segment { grid-column: 1 / -1; grid-row: 2; }
.dash-sys-row__modules { grid-column: 1 / -1; grid-row: 3; }

.dash__systems {
  overflow-y: auto;
  scrollbar-gutter: stable;
}
.dash__systems[data-scrollable="true"] {
  mask-image: linear-gradient(to bottom, #000 92%, transparent);
}
```

### 10.2 수동 QA 체크리스트

- [ ] 1920×1080: 히어로 타이틀·통과율·4 KPI·6카드 한 화면 또는 Zone C만 스크롤
- [ ] 1280×720: 시스템명 14px 이상, 카드 내부 빈 공간 과다 없음
- [ ] 320×568: attention 1행 + micro tier에서도 시스템명 보임
- [ ] 전체 미점검: CTA → execute 페이지 이동
- [ ] error 시스템: 좌측 빨간 accent + attention strip 상단
- [ ] reduced-motion: pulse·count-up 없음

---

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 초안 — P0~P2 통합 폴리시 Spec | AI |
