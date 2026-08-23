# 일간 대시보드 관제탑화 (Dashboard Mission Control) — Design

**작성일:** 2026-08-23
**상태:** 초안 (사용자 리뷰 대기)
**대상:** `app/web/templates/dashboard.html`, `app/web/templates/dashboard/partials/`, `app/web/frontend/styles/dashboard.css`, `app/web/static/dashboard.js`, `app/contexts/insights/application/daily_dashboard.py`, `app/api/routes_daily.py`, `app/contexts/insights/application/insights_charts.py`, `app/contexts/insights/application/stats_charts.py`, `scripts/check_frontend_gates.py`

---

## 0. 요약

`2026-08-19-frontend-elevation-design.md` §1.1 이 정의한 문제 — **"이 도구를 처음 보는 사람이 감탄하지 않는다"** — 는 아직 해결되지 않았다. P1~P3-4 는 전부 **강제력**(SSOT · CI 게이트 · CDN 제거 · Vite 툴체인)을 세우는 작업이었고, 그 위에 올릴 **시각적 페이오프**가 이 문서의 범위다.

목표 장면을 **일간 대시보드 `/` 하나**로 좁힌다. 감탄의 정체는 세 가지이고, 각각 다른 장치가 담당한다.

| 감탄 | 담당 장치 |
| --- | --- |
| "살아있네" | 라이브 활동 피드 + morph 교체 + 상태 전이 모션 |
| "다 보이네" | 3열 넌스크롤 관제탑 레이아웃 |
| "예쁘다" | 지배 상태 대형 타이포 + 진행 링 + 타입 스케일 정비 |

**독립 배포 가능한 3단계로 나눈다.**

| 단계 | 내용 | 절 |
| --- | --- | --- |
| **1** | 3열 레이아웃 + 활동 피드 + 모션 + 밀도 JS 철거 | §3.1~3.6 · §4 · §6 |
| **2** | 타입 스케일 + 표면 품질 | §3.7 |
| **3** | 차트 통합 (plotly 2종 제거) | §3.8 · §5 |

1단계가 감탄의 본체다. 2단계는 정돈이고, 3단계는 속도이자 부채 청산이다.

---

## 1. 문제

### 1.1 뼈대는 이미 좋다 — 재건축이 아니라 증축이다

`dashboard.css:65` 의 `.dash` 는 이미 `container-type: size` 기반의 **높이 100% · 넌스크롤 · 유동 레이아웃**이다. `cqh`/`cqi` 단위가 20곳 넘게 쓰여 뷰포트가 줄면 폰트·간격·라운딩이 함께 줄어든다. 관제탑의 절반은 이미 지어져 있다.

부족한 것은 구조 세 가지다.

### 1.2 결함 1 — 세로 2단 구조가 정보를 압축한다

현재 `.dash` 는 세로로 KPI 존(`#dash-host-kpi`, 최대 42%) + 매트릭스 존(`.dash-host-matrix`, 나머지)이다. 매트릭스 안에서 시스템 6행이 각각 헤더·세그먼트바·모듈필 3단으로 쌓이므로, **6 시스템 / 총 31 모듈**(실측: `app/systems/*/manifest.yaml` — HOM 10 · MHM 8 · HRP 4 · CHBOT 3 · FP 3 · HWTC 3)이 세로 공간을 전부 소진한다. 남는 가로 공간이 버려진다.

### 1.3 결함 2 — "살아있음"이 가짜다

`dashboard.js:7` 의 `REFRESH_MS = 30000` 이 30초마다 프래그먼트를 `hx-swap="innerHTML"` 로 **통째로** 갈아끼운다. 결과:

- 화면이 부드럽게 흐르는 것이 아니라 **30초마다 한 번 툭 점프**한다.
- `dashboard.css:330` 의 `.dash-sys-row { animation: dash-row-in 0.35s ... both; }` + `:nth-child` 지연(`:443`~`:448`, 0~200ms)이 **교체마다 재생**된다. 첫 로드에서 세련된 연출이, 상시 띄워두면 30초 주기의 깜빡임이 된다.
- 스크롤 위치·포커스·진행 중인 CSS 애니메이션이 매번 소실된다.

Run/Suite 에는 이미 진짜 WebSocket(`app/api/ws_runs.py:19`)이 있으나 대시보드에는 없다.

### 1.4 결함 3 — 밀도 시스템이 이중이다

`dashboard.js` 의 `applyDensityLayout()` · `updateDashboardDensity()` · `ResizeObserver`(약 90줄)가 밀도 티어를 계산해 `data-density` 를 찍고, `dashboard.css:594` 이하의 `[data-density="compact|dense|minimal|micro"]` 블록(약 50줄)이 그것을 받는다.

**그런데 §1.1 의 컨테이너 쿼리가 이미 같은 일을 하고 있다.** 두 시스템이 겹쳐 있고, 겹친다는 사실이 어느 쪽 코드를 읽어도 드러나지 않는다.

### 1.5 결함 4 — 타입 스케일이 없다

`app/web/frontend/styles/app.css` 의 고정 `font-size` 리터럴 실측:

```
0.6 · 0.625 · 0.68 · 0.6875 · 0.7 · 0.75 · 0.78 · 0.8125 · 0.82 · 0.875 · 0.9375 · 1 · 1.125 rem
```

13단계이며 `0.68` · `0.78` · `0.82` 는 어떤 스케일에도 속하지 않는 눈대중 값이다. 색 토큰은 SSOT 3층으로 잘 정리돼 있는데(FG-002 가 강제) **타입만 체계 밖에 있다.**

또한 Pretendard Variable 을 self-host 해두고 `font-weight` 만 쓴다. `font-variant-numeric: tabular-nums` 가 **어디에도 없어**, `kpi-card/index.ts` 의 카운트업 중 자릿수 폭이 흔들려 옆 요소가 떨린다.

### 1.6 결함 5 — 차트 라이브러리 3종이 5.8MB

`app/web/static/dist` 실측:

| 파일 | 크기 |
| --- | --- |
| `vendor-plotly-*.js` | 4,572 KB |
| `vendor-echarts-*.js` | 1,016 KB |
| `vendor-chart-*.js` | 200 KB |
| `main-*.css` | 140 KB |
| `htmx.esm-*.js` | 59 KB |
| `main-*.js` | 55 KB |
| **dist 전체** | **9.1 MB** |

이 5.8MB 가 그리는 차트는 전부 합쳐 **13개**이며 타입은 **4종**(line · bar · pie · heatmap)뿐이다.

| 위치 | 타입 | 개수 |
| --- | --- | --- |
| `insights_charts.py` | Scatter 3 · Heatmap 1 · Pie 1 · Bar 1 | 6 |
| `stats_charts.py` | Pie 1 · Bar 4 | 5 |
| `admin-runs.js:649` | Chart.js 라인 | 1 |
| `admin-runs.js:774` | ECharts 히트맵 | 1 |

근본 원인은 **파이썬 시절의 잔재**다. 서버가 `plotly.graph_objects` 로 figure JSON 을 만들어 내려보내므로(`to_plotly_json()`, 11곳) 클라이언트가 `plotly.js` 를 버릴 수 없다. `2026-08-22-frontend-elevation-p3-4-enforcement-design.md` D1 이 이 구속을 기록해 두었다.

---

## 2. 목표 / 비목표 / 성공 기준

### 2.1 목표

1. 일간 대시보드가 **한 화면에서 전체 상황을 말하고, 스스로 움직이고, 잘 만들어 보이게** 한다.
2. 중복된 밀도 시스템을 **하나로** 줄인다(CSS 컨테이너 쿼리 단일화).
3. 타입 스케일을 색 토큰과 **동등한 수준의 체계**로 올린다.
4. 차트 라이브러리를 **3종 → 1종**으로 줄이고 파이썬 `plotly` 의존을 제거한다.
5. 진행 중인 FG-004 · FG-005 allowlist 를 **줄인다**(부산물).

### 2.2 비목표 (명시적 YAGNI)

- **다크모드 · 테마 시스템** — `2026-08-19` §2.2 의 결정을 그대로 유지한다. 라이트 단일 팔레트. 사용자 재확인 완료.
- **대시보드 WebSocket 채널** — 폴링 + morph 로 체감의 대부분을 얻는다(D3). 백엔드 실시간 경로를 신설하지 않는다.
- **7일 추이 · 스파크라인** — 당일 데이터만 존재한다. 신규 read model 을 만들지 않는다.
- **모션 라이브러리(GSAP · Motion One)** — §3.5 의 4계층이 전부 네이티브 CSS 로 된다.
- **SPA 전환 · React/Vue** — `2026-08-19` §3.1 의 결정 유지.
- **ROI 헤드라인(절감 시간) 승격** — 이번 범위 밖. §9 에 후보로 남긴다.
- **`tokens.generated.css` 의 `color-mix()` 파생 전환** — 검토 후 기각(D6).
- **레거시 JS 13파일 전면 이관** — P4 의 몫. 이 문서는 `dashboard.js` 하나만 이관한다.

### 2.3 성공 기준

| 기준 | 측정 |
| --- | --- |
| 3열 넌스크롤 | 1366 · 1920 · 2560 px 에서 세로 스크롤바 0, 활동 피드만 내부 스크롤 |
| 교체가 통짜가 아님 | 세 존 모두 `hx-swap="morph"`, 템플릿 렌더 테스트가 단언 |
| stagger 재생 없음 | 폴링 갱신 후 `.dash-sys-row` 에 `animation` 재시작 없음(morph 가 노드 보존) |
| 밀도 시스템 단일화 | `dashboard.js` 의 밀도 코드 0줄, `[data-density=...]` CSS 블록 0개 |
| 타입 스케일 | `app.css`·`dashboard.css` 의 고정 `font-size` 리터럴이 전부 `--fs-*` 토큰 경유 |
| 번들 | `entries/vendor-plotly.ts`·`entries/vendor-chart.ts` **부재**, echarts 엔트리 350KB 이하 |
| allowlist | `FG005_ALLOWLIST` 에서 `dashboard.js` 한 줄 삭제 |

---

## 3. 설계

### 3.1 레이아웃 — 세로 2단에서 3열로

```
                    ← main (사이드바 16rem 제외) →
┌──────────────────┬─────────────────────────────┬──────────────────┐
│ ① 지배 상태       │ ② 시스템 × 모듈 매트릭스      │ ③ 라이브 활동 피드 │
│                  │                             │                  │
│    ◜◝            │ HOM ▓▓▓▓▓▓▓░░░  7/10        │ 09:14 HOM 로그인  │
│   ◟ 86% ◞        │ MHM ▓▓▓▓▓▓▓▓    8/8         │       ● 통과      │
│                  │ HRP ▓▓▓▒        3/4         │ 09:13 FP 결제     │
│  27/31 모듈 정상  │ FP  ▓▓▒         2/3         │       ● 이상징후 ⟳│
│                  │ CHB ▓▓▓         3/3         │ 09:11 HRP 급여    │
│  ┌────┐┌────┐   │ HWT ▓▓░         2/3         │       ● 진행 중    │
│  │KPI ││KPI │   │                             │ 09:08 …           │
│  └────┘└────┘   │  행 클릭 → 드릴다운 드로어    │  ↑ 새 항목이 위로  │
└──────────────────┴─────────────────────────────┴──────────────────┘
   minmax(260,320)            1fr                  minmax(280,340)
```

`.dash` 의 `container-type: size` · `height: 100%` · `overflow: hidden` 은 그대로 두고, `flex-direction: column` 을 `display: grid` + 3열로 바꾼다. 유동 단위(`cqh`/`cqi`)는 전부 유지한다 — 이것이 §1.1 의 자산이다.

**반응형 붕괴 순서**

| 폭 | 레이아웃 |
| --- | --- |
| ≥ 1440px | 3열 |
| 1024 ~ 1440px | 2열 — 활동 피드가 좌측 열 하단으로 이동 |
| < 768px | 1열 스택 — 활동 피드는 `max-height` + 내부 스크롤로 높이 제한 |

`dashboard.css:23`·`:36` 의 `body:has(.dash) main` 미디어쿼리를 그대로 이어쓴다.

**넌스크롤 예산:** 활동 피드 열 **하나만** 내부 스크롤을 허용한다. 나머지 두 열은 `overflow: hidden` 을 유지한다.

> **정정(구현 중 확인):** 초안은 모바일에서 활동 피드를 `<details>` 로 접는다고 적었으나
> 구현하지 않았다. `<details>` 는 morph 교체 대상(`#dash-host-activity`) **안**에 들어가는데,
> 열림/닫힘은 순수 DOM 상태이고 서버는 그것을 모른다. 서버가 `open` 없이 렌더하면 사용자가
> 펼쳐둔 피드가 **갱신될 때마다 닫힌다.** 막으려면 열림 상태를 클라이언트에 보관했다가 swap
> 후 복원해야 하는데, 이는 §3.5 의 "변한 것만 움직인다" 원칙에 반하는 상태 복제다.
> `max-height` + 내부 스크롤이 같은 목적을 상태 없이 달성한다.

### 3.2 ① 지배 상태 — 문장에서 숫자와 링으로

현재 `dash-hero` 는 상황을 한국어 문장으로 요약한다(`zone_a_kpi.html` — "점검실패 3건 — 우선 확인이 필요합니다"). 이를 **대형 숫자 + 진행 링**으로 바꾸고, **기존 문장은 링 아래 서브텍스트로 남긴다**(정보 손실 없음).

- 진행 링: `conic-gradient` 하나로 그린다. **SVG 도 차트 라이브러리도 쓰지 않는다.** 각도 = `pass_rate` × 3.6deg. `totals.pass_rate` 는 `daily_dashboard.py` 가 이미 계산한다.
- 링 색: 지배 톤의 `--st-{tone}-solid`. 트랙은 `--pl-border`.
- 대형 숫자: `{passed}/{modules}` — `--fs-display`(§3.7)와 `tabular-nums`.
- 하단: 기존 `kpi_card` 매크로 호출을 세로 스택으로. **매크로 시그니처를 건드리지 않는다**(D2).

### 3.3 ② 시스템 매트릭스 — 3단 행을 1행으로 압축

`dashboard/partials/_macros.html` 의 `system_row` 를 재설계한다. **이 매크로의 소비자는 `zone_b_matrix.html` 하나뿐임을 확인했다** — 상황판(`wall_fragment.html`)은 주석에 적힌 대로 이 매크로를 의도적으로 가져오지 않으므로, 자유롭게 바꿔도 다른 화면에 영향이 없다.

한 행의 구성:

```
[코드 뱃지] [시스템 이름]  [모듈 셀 × N]                    [n/m]
```

- 모듈 셀은 정사각 타일. 상태색으로 채우고, 셀 안 하단에 `duration_ms` 미세 바를 얹어 "빠른 모듈 / 느린 모듈"이 눈으로 읽히게 한다. 이 값은 `DailyStatusRow.duration_ms` 에 이미 있다.
- 셀 라운딩은 행 라운딩과 **별도 스케일**(작은 값)을 쓴다 — 큰 라운딩을 작은 타일에 쓰면 형태가 뭉개진다.
- 기존 `module_pill`(라벨 포함 필)은 셀 방식으로 대체된다. `module_segment_bar` 는 셀 자체가 그 역할을 하므로 제거한다.
- 상태 글리프(`tone_glyph`)는 유지한다 — 색에만 정보를 싣지 않기 위한 기존 결정이다.
- 행 클릭 → 기존 드릴다운 드로어(`dashboard.html` 의 Alpine `drawerOpen`) 그대로.

### 3.4 ③ 라이브 활동 피드 — 신설

**"우와"의 엔진이며, 현재 대시보드에 완전히 없는 축이다.**

핵심 사실: **신규 프로젝션 · 신규 쿼리 · 스키마 변경이 전부 불필요하다.** `DailyStatusRow` 가 이미 `updated_at` · `last_status` · `last_run_id` · `recovered` 를 들고 있다.

각 항목의 구성:

```
09:14  HOM · 로그인      ● 통과
09:13  FP · 결제        ● 이상징후  ⟳
```

- 시각: `updated_at` 의 시:분
- 시스템 · 모듈 이름: `SystemDefinition` 에서 join
- 상태 점 + 라벨: **`status_labels.py` SSOT 경유만**(FG-006 이 템플릿 리터럴을 막는다)
- `recovered == True` 면 `⟳` — 자동 복구가 일어났다는 뜻이며, 이 도구의 가치를 가장 직접적으로 보여주는 기호다
- `last_run_id` 가 있으면 항목 전체가 `/runs/{id}` 링크

빈 상태(오늘 점검 이력 없음)에는 **열 높이만큼 차지하는** 플레이스홀더를 둔다 — 3열이 무너지지 않게 하기 위함이다.

### 3.5 모션 언어

**원칙: 변한 것만 움직인다.** 30초마다 화면 전체가 움직이면 그것은 생명이 아니라 노이즈다.

| 계층 | 장치 | 구현 |
| --- | --- | --- |
| **교체** | 바뀐 DOM 만 diff 교체 | `idiomorph` + `hx-swap="morph"`. 스크롤·포커스·진행 중 애니메이션 생존 |
| **전이** | 셀 상태 변화 시에만 wipe (0.4s) | `@starting-style` + `transition-behavior: allow-discrete`. 라이브러리 0 |
| **지속** | `running` = shimmer, `waiting_input` = 맥동 | `wall.css` 의 결정 승계 — **맥동은 `waiting_input` 하나만** |
| **진입** | 피드 새 항목 슬라이드 인 + 1.2s 하이라이트 페이드 | CSS only |

**첫 로드 stagger 는 살린다.** 단 `sessionStorage` 플래그로 최초 1회만 — morph 도입 후에는 애초에 재생될 신규 노드가 없으므로 §1.3 의 반복 재생 결함이 구조적으로 소멸한다.

**카운트업:** `kpi-card/index.ts` 에 이미 있고 `entries/main.ts` 가 `htmx:afterSwap` 에 재바인딩을 걸어두었다. idiomorph 도 같은 이벤트를 발화하므로 그대로 동작한다. morph 는 노드를 보존하므로 **값이 바뀌지 않은 카드는 카운트업이 재생되지 않는다** — 이것이 정확히 원하는 동작이다.

**접근성:** `prefers-reduced-motion: reduce` 에서 전이·지속·진입을 전부 정지하고 교체는 즉시로 한다. `wall.css` 의 기존 패턴을 그대로 쓴다.

**하지 않는 것:** 페이지 전환 View Transitions(단일 화면이라 얻을 것이 없다) · 패럴랙스 · 3D · 글로우(관제 화면에서 오독을 유발한다).

### 3.6 밀도 시스템 철거

| 삭제 대상 | 규모 |
| --- | --- |
| `dashboard.js` 의 `applyDensityLayout` · `updateDashboardDensity` · `scheduleDensityUpdate` · `bindDensityObserver` · `ResizeObserver` | 약 90줄 |
| `dashboard.css` 의 `[data-density="compact\|dense\|minimal\|micro"]` 블록 | 약 50줄 |
| `#dash-host-kpi[data-kpi-compress="true"]` 관련 분기 | 소수 |

3열 레이아웃에서는 각 열의 폭이 그리드로 고정되므로 컨테이너 쿼리만으로 충분하다. 세로 맞춤은 `grid-template-rows` + 셀 `aspect-ratio` + `min()` 으로 처리한다.

**검증:** 1366 · 1920 · 2560 px 세 해상도에서 수동 확인한다(§6.3).

### 3.7 타입 스케일과 표면 — 2단계

**타입 스케일 (8단계, 비율 1.125)**

```css
/* primitives.css */
--fs-3xs: 0.6875rem;  --fs-2xs: 0.75rem;   --fs-xs: 0.8125rem;
--fs-sm:  0.875rem;   --fs-md:  1rem;      --fs-lg: 1.125rem;
--fs-xl:  1.375rem;   --fs-2xl: 1.75rem;
--fs-display: clamp(2rem, 9cqh, 4.5rem);   /* 지배 상태 숫자 전용 */
```

§1.5 의 고정 리터럴 13개를 여기로 흡수한다. **컨테이너 쿼리 유동값(`clamp(min, Ncqh, max)`)은 그대로 둔다** — 그것은 눈대중이 아니라 의도된 유동성이다.

**가변 폰트 활용**

```css
.dash-hero__value, .kpi-card__value, .dash-cell__ms {
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
}
```

**표면**

| 항목 | 결정 |
| --- | --- |
| 테두리 | `inset 0 0 0 1px var(--pl-border)` 유지 — 레이아웃 이동이 없는 옳은 선택 |
| 그림자 | 2단계 → **3단계**. 히어로 링 · 매트릭스 · 피드가 서로 다른 고도에 있어야 3열이 평면으로 보이지 않는다 |
| 라운딩 | 행은 기존 유동값, **셀은 별도 작은 스케일** |

`primitives.css` 의 79개 hex 는 **정리하지 않는다** — accent 램프(sky · cyan · rose · emerald · amber)를 `execute.html:75` 의 시스템 카드가 살아서 쓰고 있음을 확인했다.

### 3.8 차트 통합 — 3단계

**전제:** 차트 통합은 대시보드의 감탄에 **직접 기여하지 않는다.** 3열 설계에 차트가 하나도 없기 때문이다(§2.2 — 스파크라인 제외). 기여하는 것은 **첫 로드 속도**이며, 데모에서 링크를 열었을 때 화면이 즉시 뜨는 것은 감탄의 전제조건이다. 그래서 가치는 있으나 **본체가 아니므로 마지막 단계**다.

**방식:** 파이썬이 `to_plotly_json()` 대신 **ECharts option dict 을 직접 만든다.**

```python
# before — plotly 를 거쳐 dict 를 얻는다
fig = go.Figure(go.Bar(x=..., y=...))
return fig.to_plotly_json()

# after — dict 을 바로 만든다
return {"xAxis": {...}, "yAxis": {...}, "series": [{"type": "bar", "data": [...]}]}
```

서버가 차트 스펙을 만드는 **구조는 유지한다**(P3-4 D1 존중). 라이브러리 의존만 사라진다. 11개 figure 빌더 함수의 본문만 바뀌고 호출부 · 라우터 · 반환 타입 계약은 그대로다.

`admin-runs.js` 의 Chart.js 라인차트 1개는 ECharts line 으로 옮긴다. 히트맵은 이미 ECharts 다.

> 대안 "파이썬은 데이터만 내려보내고 차트 구성은 TS 가 한다" 를 검토했다. 더 깨끗하지만 라우터 · 뷰모델 · JS 3층을 동시에 바꾸는 일이므로 **P4 로 넘긴다**(D5).

---

## 4. 백엔드 변경

**변경 지점은 두 곳뿐이다.**

### 4.1 활동 피드 — `daily_dashboard.py`

`build_daily_dashboard()` 의 반환 dict 에 항목 하나를 추가한다.

```python
"activity": build_activity_feed(status_rows, systems, limit=20),
```

`build_activity_feed()` 는 순수 함수 약 25줄이다.

- `status_rows` 를 `updated_at` 내림차순 정렬
- 상위 `limit` 개
- `system_code` → `SystemDefinition` 으로 시스템·모듈 이름 join
- 상태 라벨·톤은 `app/core/status_labels.py` 경유
- `recovered` · `last_run_id` 보존

`limit=20` 고정. 열 높이를 넘치는 분량은 CSS 가 자른다 — 서버가 뷰포트를 알 필요는 없다.

### 4.2 프래그먼트 존 신설 — `routes_daily.py`

`/daily/fragments/{zone}` 에 `activity` 존을 추가한다.

```
#dash-host-hero      → /api/dashboard/daily/fragments/kpi        (기존)
#dash-host-matrix    → /api/dashboard/daily/fragments/matrix     (기존)
#dash-host-activity  → /api/dashboard/daily/fragments/activity   (신규)
```

**별도 존으로 두는 이유:** morph 단위가 작을수록 "변한 것만 움직인다"가 정확해진다. 피드를 매트릭스에 묶으면 새 항목 하나가 들어올 때마다 매트릭스 전체가 diff 대상이 된다.

세 존 모두 `hx-swap="morph"` 로 전환한다.

### 4.3 하지 않는 것

- WebSocket 대시보드 채널(D3)
- 7일 추이 read model
- `manual_seconds_saved` 승격(§9 후보)

---

## 5. 의존성 변화

### 5.1 제거

| 대상 | 근거 | 회수 |
| --- | --- | --- |
| Python `plotly>=6.9.0,<7.0` | `insights_charts.py` · `stats_charts.py` 가 `to_plotly_json()` 만 쓴다. §3.8 이 dict 직접 생성으로 대체 | requirements.txt 한 줄 |
| `plotly.js-dist-min` + `entries/vendor-plotly.ts` | 위 제거의 종속 결과 | **−4,572 KB** |
| `chart.js` + `entries/vendor-chart.ts` | 라인차트 1개를 ECharts 가 흡수 | −200 KB |

`vite.config.ts` 의 `rollupOptions.input` 에서 두 줄이 사라진다 — P3-4 §3.1 이 명시한 **만료 조건이 충족되는 것**이다.

### 5.2 유지·최적화

- `echarts` — 단독 생존. `entries/vendor-echarts.ts` 를 트리셰이킹 빌드로 교체(사용하는 4종 차트 + Canvas 렌더러만 import) → **1,016 KB → 약 300 KB**

### 5.3 추가 — 하나

- `idiomorph` (약 4 KB). htmx 공식 확장. npm self-host 후 Vite 엔트리로 번들 → FG-001 통과

### 5.4 네이티브로 해결 (라이브러리 0)

| 필요 | 수단 |
| --- | --- |
| 상태 전이 애니메이션 | `@starting-style` + `transition-behavior: allow-discrete` |
| 진행 링 | `conic-gradient` |
| 밀도 대응 | `@container` (이미 도입돼 있음) |
| 헤드라인 줄바꿈 | `text-wrap: balance` |
| 숫자 정렬 | `font-variant-numeric: tabular-nums` |

### 5.5 총계

차트 라이브러리 **5,788 KB → 약 300 KB (−95%)**. dist 전체로는 **9,249 KB → 약 3,761 KB (−59%)** — 남는 3.1MB 는 Pretendard 동적 서브셋 woff2 92개이며 이것은 폰트 self-host 의 정상 비용이다.

새 차트 의존성 0개, 새 모션 의존성 0개, 신규 의존성은 4KB 하나다.

### 5.6 제거 검토 후 유지하기로 한 것

직접 `import` 가 없어 후보로 올랐으나 확인 결과 실제로 필요했다.

| 패키지 | 실제 소비자 |
| --- | --- |
| `websockets` | uvicorn 의 WS 프로토콜 구현. `app/api/ws_runs.py` 가 이것 없이는 동작하지 않는다 |
| `bcrypt` | `pwdlib.hashers.bcrypt.BcryptHasher` (`app/contexts/identity/service.py:8`) — 레거시 해시 검증 경로 |
| `python-multipart` | `Form(...)` (`app/contexts/identity/router.py:31`) |

---

## 6. 게이트와 테스트

### 6.1 기존 게이트가 이 작업에 거는 제약

| 게이트 | 의미 |
| --- | --- |
| **FG-001** 외부 CDN 0 | idiomorph 는 반드시 npm self-host + Vite 엔트리 |
| **FG-002** frontend/ hex 0 | 새 그림자 3단계 · 타입 스케일 전부 토큰으로 |
| **FG-003** 상태 라벨 SSOT | 활동 피드 라벨은 `status.generated.ts` / 서버 주입 경유 |
| **FG-004** 400줄 상한 | `dashboard.css` 892줄을 **컴포넌트로 쪼갤 기회** |
| **FG-005** static 직접 참조 0 | `dashboard.js` → `entries/dashboard.ts` 이관 |
| **FG-006** 템플릿 상태 리터럴 0 | 활동 피드 항목의 라벨·톤은 서버 주입만 |

### 6.2 게이트 전진 (부산물)

- `dashboard.css` 를 `components/status-hero/` · `components/system-matrix/` · `components/activity-feed/` 3개 컴포넌트로 분할 → **FG004_ALLOWLIST 에서 `dashboard.css` 한 줄 삭제**
- `dashboard.js` → `entries/dashboard.ts` 이관 → **FG005_ALLOWLIST 에서 한 줄 삭제**

두 allowlist 는 "비면 완성"이 전제인 카운터다(P3-4 §7).

### 6.3 새로 붙일 검증

| 대상 | 도구 | 확인하는 것 |
| --- | --- | --- |
| `build_activity_feed()` | pytest | `updated_at` 내림차순 · `limit` 준수 · `recovered` 보존 · 빈 입력 · 이름 join 실패 시 방어 |
| 진행 링 각도 | Vitest | `0/31` → 0deg · `31/31` → 360deg · `modules == 0` 시 0 나눗셈 방어 |
| 활동 피드 시각 포맷 | Vitest | 자정 넘김 · 미래 시각 방어 |
| 번들 구성 | `tests/frontend/test_vendor_bundles.py` | plotly · chart 엔트리 **부재** 단언으로 전환, echarts 상한 500,000 → **350,000** |
| morph 배선 | pytest (템플릿 렌더) | 세 존이 `hx-swap="morph"` 이고 대상 ID 가 실재 |
| 넌스크롤 | 수동 | 1366 · 1920 · 2560 px 에서 세로 스크롤바 0 |

`test_vendor_bundles.py` 의 `("entries/vendor-plotly.ts", 500_000)` 줄이 **"이 엔트리는 존재하면 안 된다"로 뒤집히는 것**이 3단계의 완료 신호다.

---

## 7. 결정

| # | 결정 | 근거 |
| --- | --- | --- |
| **D1** | 목표 장면을 **일간 대시보드 하나**로 좁힌다 | 예산을 분산하면 어느 화면도 유료급에 도달하지 못한다. 상황판·Run 화면은 이미 P3-2 · P3-1 이 다뤘다 |
| **D2** | `kpi_card` 매크로 **시그니처 불변** | 상황판(`wall_fragment.html`)과 공유한다. 바꾸면 두 화면을 동시에 검증해야 한다 |
| **D3** | **폴링 유지 + morph**, WS 신설 안 함 | 체감의 대부분은 "교체가 통짜인가"에서 온다. 백엔드 실시간 경로는 비용 대비 회수가 낮다. 사용자 결정 |
| **D4** | 라이트 팔레트 **유지** | `2026-08-19` §2.2 의 명시적 비목표를 뒤집지 않는다. 승부처를 타이포·여백·모션·밀도로 옮긴다. 사용자 결정 |
| **D5** | 파이썬이 **ECharts option dict 을 직접** 만든다 | 서버가 차트 스펙을 만드는 구조(P3-4 D1)를 유지하면 변경 표면이 11개 함수 본문에 갇힌다. "데이터만 내려보내기"는 3층 동시 변경이라 P4 |
| **D6** | `tokens.generated.css` 를 `color-mix()` 파생으로 **바꾸지 않는다** | 같은 팔레트를 메일 템플릿(FG-007)이 쓰는데 메일 클라이언트는 `color-mix` 를 해석하지 못한다. 파이썬이 파생색을 미리 계산하는 현 구조가 옳다 |
| **D7** | 활동 피드는 **우측 고정 열**(하단 티커 아님) | 티커는 공간을 덜 먹지만 동시에 보이는 항목이 1~2개로 줄어 "살아있음"의 밀도가 사라진다. 사용자 결정 |
| **D8** | 지배 상태를 **숫자 + 링**으로, 기존 문장은 **서브텍스트로 존치** | 문장은 상황 판단에 실제로 유용하다. 대체가 아니라 계층화 |
| **D9** | `primitives.css` 79개 hex 를 **정리하지 않는다** | accent 램프를 `execute.html` 이 살려 쓴다. 죽은 토큰이 아니다 |

---

## 8. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| **idiomorph 가 Alpine 상태를 깨뜨림** | morph 는 DOM 을 보존하지만 Alpine 의 내부 바인딩과 충돌할 수 있다 | 드로어(`dashboard.html` 의 `x-data`)가 유일한 Alpine 지점이며 **morph 대상 3존 바깥**에 있다 — 구조적으로 안전. 그래도 구현 첫 단계에서 드로어 열림 상태로 갱신을 트리거해 확인한다 |
| **밀도 JS 철거 후 좁은 화면에서 넘침** | 컨테이너 쿼리가 잡지 못하는 케이스가 있을 수 있다 | 3해상도 수동 확인(§6.3). 넘치면 **JS 를 되살리지 않고** 붕괴 브레이크포인트를 조정한다 |
| **31 모듈이 늘어나면 매트릭스가 넘침** | HOM 이 10개다. 시스템 하나가 20개가 되면 셀이 읽을 수 없이 작아진다 | 셀에 `min-width` 하한을 두고 초과분은 행 내부 가로 스크롤. 현 규모에서는 발생하지 않는다 |
| **ECharts 트리셰이킹이 기대만큼 줄지 않음** | 실측 전에는 300KB 를 확신할 수 없다 | 3단계 착수 시 **먼저 측정**한다. 350KB 를 넘으면 그 시점에 보고하고 상한을 재설정한다 — 우회를 즉흥으로 만들지 않는다 |
| **파이썬 차트 dict 이 plotly 와 미세하게 다르게 렌더** | 축 서식·색·범례 기본값이 라이브러리마다 다르다 | 11개 figure 를 **하나씩** 옮기고 각각 실물 확인. 기존 테스트가 반환 구조를 잡아준다 |
| **`system_row` 재설계가 예상보다 큼** | 매크로 하나가 아니라 CSS 다수 선택자가 딸려 있다 | 소비자가 `zone_b_matrix.html` 하나임을 확인했다(§3.3). 회귀 표면이 그 파일에 갇힌다 |
| **1단계만 하고 멈출 가능성** | 2·3단계가 미뤄지면 타입 스케일 부채와 5.8MB 가 그대로 남는다 | 단계가 독립 배포 가능하도록 설계했다. 미뤄져도 1단계는 온전하다 |

---

## 9. 이후 — 이 문서가 남기는 것

| 항목 | 비고 |
| --- | --- |
| `manual_seconds_saved` 를 대시보드로 승격 | `2026-08-19` §1.5 가 "경영진 핵심 지표가 관리자 메뉴에 잠겨 있다"고 지적한 항목. 좌측 KPI 스택 3번째 칸이 자리다 |
| 7일 추이 read model + 스파크라인 | 신규 프로젝션이 필요하다. 데이터가 생기면 매트릭스 행 끝이 자리다 |
| 파이썬 차트 빌더 → 데이터만 내려보내기 | D5 가 P4 로 넘긴 것 |
| 대시보드 WebSocket 채널 | D3 가 미룬 것. 폴링 주기를 더 줄여야 할 필요가 확인되면 그때 |
| 나머지 레거시 JS 12파일 이관 | P4 의 몫. 이 문서는 `dashboard.js` 하나만 가져간다 |

---

## 10. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§1.1 문제 정의 · §2.2 다크모드 비목표 · §3.1 스택 결정 · §1.5 미노출 자산)
- 직전 단계: `docs/superpowers/specs/2026-08-22-frontend-elevation-p3-4-enforcement-design.md` (§3.1 vendor 브리지 만료 조건 · D1 plotly 구속 · §7 P4 인계 목록)
- 상황판: `docs/superpowers/specs/2026-08-20-frontend-elevation-p3-2-wall-design.md` (§3.10 맥동 결정)
- 게이트 SSOT: `scripts/check_frontend_gates.py` · `scripts/ci/gates.py` · `docs/CI.md`
- 상태 SSOT: `app/core/status_labels.py`
- 문서 거버넌스: `docs/DOCS_GOVERNANCE.md`
