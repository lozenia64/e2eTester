# 점검 실행 승격 (Execute Promotion) — Design

**작성일:** 2026-08-24
**상태:** 초안 (사용자 리뷰 대기)
**대상:** `app/web/templates/execute.html`, `app/web/static/app.js`, `app/web/frontend/styles/app.css`, `app/web/frontend/entries/`, `scripts/check_frontend_gates.py`, 로그 팔레트를 든 템플릿 6개

---

## 0. 요약

대시보드(`2026-08-23`)와 상황판(`2026-08-24`)은 승격됐다. **나머지 화면은 그대로다.** 대시보드를 보고 감탄한 사람이 두 번째 메뉴를 누르면 인상이 깨진다 — 이 문서가 다루는 문제다.

해결을 **화면 하나당 한 사이클**로 쪼갠다(사용자 결정). 각 사이클은 설계 → 계획 → TDD 구현 → AC Spec 갱신을 돌고 독립 배포된다. 순서는 **점검 실행 → 수트 상세 → 런 상세 → Run 이력 → 프리셋 관리 → 예약 관리**(사용자 결정)이며, 이 순서는 우연이 아니라 레거시 모놀리스 `app.js` 3,263줄의 해체 순서와 일치한다(§1.2).

그 앞에 **Cycle 0** 하나를 얇게 둔다. 템플릿 6개가 SSOT 상태 토큰을 같은 이름·다른 값으로 재정의하고 있다(§1.1). 이것은 디자인 과제가 아니라 버그이고 화면 순서와 무관하므로 먼저 지운다.

이 문서는 **프로그램 전체 구조 + Cycle 0 + Cycle 1(점검 실행)** 을 정의한다. Cycle 2~6 은 각각 자기 설계 문서를 갖는다.

---

## 1. 문제

### 1.1 같은 상태가 화면마다 다른 색이다

상태 색의 SSOT 는 `app/core/status_labels.py` 이고, `scripts/gen_frontend_tokens.py` 가 `tokens.generated.css` 로 내보낸다. 그런데 템플릿 6개가 인라인 `<style>` 에서 **같은 토큰 이름에 다른 값**을 얹는다.

| 출처 | passed | anomaly | error |
| --- | --- | --- | --- |
| `tokens.generated.css` (SSOT) | `#10b981` | `#f59e0b` | `#ef4444` |
| `admin/index.html:8` · `admin/runs.html:8` · `anomalies.html:9`<br>`insights.html:9` · `schedules.html:9` · `self_healing.html:9` | `#0ca30c` | `#fab219` | `#d03b3b` |

`--st-passed` 라는 **같은 이름**을 쓰기 때문에 각 화면 안에서는 일관돼 보이고, 화면을 넘어갈 때만 어긋난다. 대시보드에서 "정상"을 본 사람이 이상징후 인박스로 이동하면 녹색이 바뀐다.

새지 않아야 할 곳이 새는 이유는 게이트의 스캔 범위다. `check_frontend_gates.py:179` 의 FG-002(하드코딩 hex 금지)는 `FRONTEND_DIR`(`app/web/frontend/`)만 순회한다. `app/web/templates/` 와 `app/web/static/*.js` 는 **어떤 색 게이트도 보지 않는다.**

그 사각지대의 크기:

| 위치 | 규모 |
| --- | --- |
| 템플릿 인라인 `<style>` | 1,258줄 (`admin/runs` 624 · `admin/index` 272 · `schedules` 117 · `insights` 57 · `self_healing` 52 · `presets` 49 · `mobile_trigger` 48 · `anomalies` 39) |
| 레거시 JS 안의 `class="…"` 리터럴 | 420개 (`schedules.js` 129 · `healing.js` 93 · `admin-runs.js` 85 · `insights.js` 53 · `presets.js` 31 · `admin-dashboard.js` 29) |

### 1.2 네 화면이 레거시 모놀리스 하나에 얹혀 있다

`execute.html` · `run.html` · `suite.html` · `runs_history.html` 은 `{% block scripts %}` 가 **비어 있다.** 전부 `base.html` 이 싣는 `app.js`(3,263줄)와 `app.css`(1,411줄) 하나에 의존한다. 이 둘이 `FG004_ALLOWLIST` · `FG005_ALLOWLIST` 에 남은 가장 큰 항목이다.

`app.js:3245` 의 `DOMContentLoaded` bind 목록이 그 내부 경계를 그대로 드러낸다.

| bind 함수 | 담당 화면 | 대략 위치 |
| --- | --- | --- |
| `bindModuleSelectors` · `bindSystemCardExpand` · `bindSystemButtons` · `bindSuiteForm` · `bindPresetPanels` · `loadPresets` | ① 점검 실행 | 1~620(모듈 그래프) · 621~1160(프리셋 패널) · 2227~2400 · 2570~2630 |
| `bindSuiteActions` · `bindSuiteOtpForm` · `bindSuiteSocket` | ② 수트 상세 | 2405~3120 |
| `bindLogControls` · `startRuntimeTicker` · `bindRunActions` · `bindOtpForm` · `bindRunSocket` | ③ 런 상세 | 1898~2400 · 3122~3263 |
| `bindRunsOverview` · `bindRunsHistory` | ④ Run 이력 | 1163~1800 |
| (없음 — `presets.js` 가 별도 파일) | ⑤ 프리셋 관리 | — |
| `bindSchedulesOverview` | ⑥ 예약 관리 | 1808~1897 |

`app.js:621~1160` 의 프리셋 코드는 **프리셋 관리 화면(⑤)이 아니라 `execute.html` 의 시스템별 프리셋 칩**을 위한 것이다(`app.js:654` 가 `[data-role="preset-panel"]` 이 없으면 즉시 반환한다). 따라서 Cycle 1 몫이고, Cycle 5 는 `presets.js` 421줄만 다룬다.

사용자가 고른 화면 순서가 이 표의 순서다. **프로그램의 부산물로 `app.js` 가 소멸한다.**

### 1.3 이 화면의 지배 요소는 이미 만들어져 있고, 숨겨져 있다

`app.js:23~520` 에 모듈 의존성 DAG 렌더러가 있다. `computeModuleDepth` 가 열을, `computeModuleSubtreeHeight` 가 행을 계산하고, `drawModuleGraph:363` 이 베지에 곡선 SVG 엣지를 그린다. 엣지는 양끝 노드의 선택 상태에 따라 `is-active` / `is-muted` 로 갈린다. 스타일은 `app.css:427~570` 에 140줄 — 호버 · 잠금 · 포커스 링 · compact 티어까지 있다.

이것이 놓인 자리는 `execute.html:317` — `<details>` 아코디언 안, 2열 카드 그리드의 한 칸 안, `sm:col-span-2` 폭이다. **펼치기 전에는 존재 자체가 보이지 않는다.**

승격의 본체는 새로 만드는 것이 아니라 이것을 꺼내 주인공 자리에 놓는 것이다.

### 1.4 화면 구조가 "다 보이네"의 반대다

`execute.html` 은 세로 스택이다. 헤더 → SUITE 카드 → 6개 시스템 카드(2열 `<details>`). 접힌 상태에서는 시스템 이름만 보이고, 무엇을 실행할 수 있는지·오늘 상태가 어떤지·실행 버튼이 어디 있는지 전부 감춰져 있다. 실행 버튼은 카드를 펼친 뒤 스크롤해야 나온다 — **데모에서 "누르는 순간"이 화면에 없다.**

---

## 2. 프로그램 구조

| 사이클 | 화면 | 잘라낼 레거시 | 완료 신호 |
| --- | --- | --- | --- |
| **0** | (없음 — 팔레트 통일) | 템플릿 7벌의 로그 토큰 정의 · `admin-runs.js` 차트 색 4개 | `legacy-aliases.css` 신설 · FG-002 스캔 범위에 `templates/` · `static/*.js` 포함 |
| **1** | 점검 실행 | `app.js` 약 1,400줄(모듈 그래프 620 + 프리셋 패널 540 + 폼 바인딩 약 240) · `app.css` 프리셋(846~1086) · 모듈그래프(427~570) 절 | `entries/execute.ts` 신설 |
| **2** | 수트 상세 | `app.js` 약 700줄 | `entries/suite.ts` 신설 |
| **3** | 런 상세 | `app.js` 약 700줄 | `entries/run.ts` 신설 |
| **4** | Run 이력 | `app.js` 약 640줄 | `app.js` **삭제** · `FG005_ALLOWLIST` 에서 제거 · `main.ts:32` 의 `window.__statusBadge` 다리 제거 |
| **5** | 프리셋 관리 | `presets.js` 421줄 | `FG005_ALLOWLIST` 한 줄 삭제 |
| **6** | 예약 관리 | `schedules.js` 1,188줄 | 〃 |

각 사이클은 `docs/superpowers/specs/` 설계 → `docs/superpowers/plans/` 계획 → TDD 구현 → `docs/specs/` AC Spec 갱신을 돈다. 사이클 1 은 `SPEC-UI-002`(점검 실행)의 §2 구성을 대체한다 — `SPEC-UI-004` 가 `SPEC-UI-001` §3 을 대체한 방식과 같다. 동작 규칙(AC-001 Suite preset 검증 · AC-002 depends_on)은 불변이다.

**사이클은 독립 배포된다.** 중간에 순서를 바꾸거나 멈춰도 각 사이클이 완결된 화면을 남긴다(사용자 확인).

---

## 3. 목표 / 비목표 / 성공 기준

### 3.1 목표

1. 상태 색이 **모든 화면에서 SSOT 값 하나**가 된다.
2. 색 게이트의 사각지대(`templates/` · `static/*.js`)를 닫고, 사이클마다 allowlist 를 줄인다.
3. 점검 실행이 **한 화면에서 전체를 말하고, 실행 버튼이 항상 보이는** 마스터-디테일 화면이 된다.
4. 모듈 의존성 그래프가 이 화면의 지배 요소가 된다.
5. `app.js` 에서 점검 실행 몫을 떼어 `entries/execute.ts` 로 옮긴다.

### 3.2 비목표 (명시적 YAGNI)

- **다크모드 · 테마 축** — `2026-08-19` §2.2 유지. 상황판 스코프 다크는 예외로 이미 격리돼 있다.
- **컴포넌트 라이브러리 선(先)구축** — 화면 하나를 승격해보기 전에 인터페이스를 정하지 않는다(D4).
- **SPA · React/Vue** — `2026-08-19` §3.1 유지.
- **모션 · 차트 라이브러리 신규 도입** — 이 화면에 차트가 없고, 모션은 네이티브 CSS 로 된다.
- **예약 등록 폼 이전** — `execute.html:165~245` 의 cron 빌더는 이번 사이클에서 옮기지 않는다(D7).
- **`/admin/*` 6개 화면 승격** — 임원·사용자는 `user` 역할이라 `/admin` 을 보지 않는다(사용자 확인). Cycle 0 의 팔레트 통일만 적용받는다.
- **`SPEC-UI-002` 의 동작 규칙 변경** — 정보구조만 바꾼다.
- **레거시 JS 전면 이관** — 사이클 1 은 점검 실행 몫만 떼어낸다.

### 3.3 성공 기준

| 기준 | 측정 |
| --- | --- |
| 팔레트 단일화 | 템플릿 7개에 `--st-*` · `--ease-spring` 정의 0건. 7개 화면의 상태 색이 `tokens.generated.css` 값으로 해석됨. `admin-runs.js` 차트에 상태 hex 0건 |
| 게이트 사각지대 폐쇄 | FG-002 가 `templates/` · `static/*.js` 를 스캔. 파일 allowlist 는 사이클마다 감소 |
| 실행 버튼 상시 노출 | 1366 · 1920 · 2560 px 에서 스크롤 없이 실행 버튼이 보인다 |
| 스크롤 소유권 | `body` 세로 스크롤 0. 내부 스크롤을 갖는 영역이 정확히 하나(우측 조건 열) |
| 그래프 승격 | 모듈 그래프 노드 크기가 현행 대비 확대되고, 시스템 선택 즉시 보인다(아코디언 펼침 불필요) |
| 이관 | `entries/execute.ts` 존재. `app.js` 에서 점검 실행 몫 제거. Vitest 가 그래프 레이아웃 계산을 단언 |
| 동작 불변 | `SPEC-UI-002` AC-001 · AC-002 기존 테스트 통과 |

---

## 4. 설계

### 4.1 Cycle 0 — 팔레트 통일

> **정정(계획 작성 중 실측):** 초안은 "지우기만 하면 `tokens.generated.css` 값이 상속된다"고 적었으나 **틀렸다.** 로그 블록이 정의하는 것은 `--st-passed` 같은 **짧은 이름**이고, SSOT 가 생성하는 것은 `--st-passed-solid` 등 **접미사 있는 이름**이다. 짧은 이름은 `tokens.generated.css` 에 존재하지 않으므로, 지우기만 하면 `var(--st-passed)` 가 미정의가 되어 색이 상속되는 것이 아니라 **사라진다.** 따라서 Cycle 0 은 삭제가 아니라 **별칭 치환**이다.

**대응 관계 실측.**

| 짧은 이름 | 로그 값 | SSOT 대응 | 처리 |
| --- | --- | --- | --- |
| `--st-passed` · `--st-anomaly` · `--st-error` · `--st-running` · `--st-cancelled` · `--st-blocked` | `#0ca30c` `#fab219` `#d03b3b` `#2a78d6` `#9ca3af` `#ec835a` | `--st-*-solid` 존재 | SSOT `-solid` 로 별칭 |
| `--st-idle` | `#b6b4ad` (4벌) · `#e5e7eb` (`admin/index`) | **없음** — `STATUS_TONES` 에 `idle` 이 없다 | `--st-pending-solid` 로 별칭(D10) |
| `--st-track` | `#ecebe6` | **없음** — 링·바의 트랙 배경이지 상태색이 아니다 | `--c-gray-200` primitive(D10) |
| `--st-active` | `#4f46e5` | 없음 — 선택 강조이지 상태색이 아니다 | `--c-indigo-600` primitive(D10) |
| `--ease-spring` | `cubic-bezier(.22, 1, .36, 1)` | `--ease-out` 이 **같은 곡선** | `--ease-out` 로 별칭. 사용처 51곳은 무변경(D9) |

`--ease-spring` 은 위 6개 파일에 더해 `presets.html:9` 까지 **7벌**이다(`presets.html` 은 상태색은 재정의하지 않는다).

**별칭의 거처.** `app/web/frontend/styles/legacy-aliases.css` 를 신설하고 `base.css` 가 `tokens.generated.css` 다음에 `@import` 한다(D9). `primitives.css` 에 넣지 않는 이유는 그 파일이 "중립 팔레트, 상태색은 `tokens.generated.css` 담당"을 명시하고 있어서다. 새 파일은 **소멸 조건을 자기 안에 적는다** — 화면별 사이클이 컴포넌트로 이관할 때마다 별칭이 한 줄씩 줄고, 마지막 화면이 끝나면 파일과 `base.css` 의 `@import` 한 줄이 함께 사라진다.

**템플릿 변경.** 7개 파일의 인라인 `<style>` 에서 위 토큰 **정의만** 지운다. `var(--st-passed)` 를 쓰는 51곳의 사용처와 마크업은 한 줄도 건드리지 않는다.

**레거시 JS.** `admin-runs.js:657~675` 의 Chart.js 데이터셋 색 4개가 로그 팔레트 hex 를 직접 들고 있다(`#0ca30c` · `#fab219` · `#d03b3b` · `#9ca3af`). CSS 별칭이 닿지 않는 유일한 자리이므로, 같은 파일 계열이 이미 쓰는 방식(`admin-dashboard.js:23` 의 `toneVar`)대로 `var(--st-*)` 문자열을 `getComputedStyle` 로 해석해 넘긴다.

**게이트 확장.** `check_frontend_gates.py:179` 의 FG-002 순회 대상에 `TEMPLATE_DIR` 과 `app/web/static/*.js` 를 추가한다. 두 곳에 하드코딩 hex 가 대량으로 남아 있으므로(§1.1) **파일 단위 allowlist** 를 함께 도입하고, 사이클마다 한 줄씩 지운다 — FG-004 · FG-005 가 이미 쓰는 방식이다.

**검증.** 6개 화면의 상태 색이 SSOT 값과 일치함을 단언하는 테스트. 색이 실제로 바뀌므로(`#0ca30c` → `#10b981`) 성공 기준은 "화면 불변"이 아니라 **"화면이 SSOT 로 수렴"** 이다.

**여기서 하지 않는 것:** 컴포넌트 추출 · 타입 스케일 · 인라인 `<style>` 제거. 전부 화면별 사이클의 몫이다.

### 4.2 승격 규격 — 매 사이클이 답하는 5문항

6사이클이 따로 놀지 않도록 각 설계 문서가 같은 질문에 답한다.

| # | 질문 | 대시보드의 답 | 상황판의 답 |
| --- | --- | --- | --- |
| 1 | **지배 정보** — 가장 큰 글자는 무엇인가 | `27/31` + 진행 링 | 상태 헤드라인 |
| 2 | **스크롤 소유권** — `body` 스크롤 0, 내부 스크롤 영역은 정확히 하나 | 활동 피드 열 | 없음(완전 고정) |
| 3 | **살아있음** — 무엇이 스스로 갱신되고 morph 대상은 무엇인가 | 3존 `hx-swap="morph"` | `#wall-body` 15초 morph |
| 4 | **추출할 컴포넌트** — 이 화면이 실제로 두 번 이상 요구한 것만 | `kpi-card` · `status-hero` | 재사용만, 신규 0 |
| 5 | **완료 신호** — 엔트리 신설 + allowlist 감소 + Vitest + 넌스크롤 회귀 | `entries/dashboard.ts` | `entries/wall.ts` |

4번이 안전장치다. **한 화면에서만 쓰이는 것은 `components/` 로 올리지 않는다.** 화면 폴더에 두고, 두 번째 화면이 같은 것을 요구할 때 승격한다.

### 4.3 Cycle 1 레이아웃 — 아코디언 6개에서 마스터-디테일 2열로

```text
              ← main (사이드바 16rem 제외) →
┌────────────────────┬──────────────────────────────────────────────┐
│ ① 무엇을 점검할까    │ ② 어떻게 점검할까                              │
│                    │                                              │
│ ▣ 전체 순차 점검     │  HOM · 대표홈             [프리셋 ▾ 홍길동폰인증] │
│   6개 시스템         │                                              │
│                    │   ┌────┐   ┌────┐   ┌────┐                   │
│ ○ HOM   ● 정상 7/10 │   │로그인│──▶│조회 │──▶│상세 │   ← 지배 요소     │
│ ● MHM   ● 정상 8/8  │   └────┘ ╲ └────┘   └────┘                   │
│ ○ HRP   ● 이상 3/4  │           ╲┌────┐                            │
│ ○ FP    ● 정상 2/3  │            ▶│결제 │        10개 중 8개 선택     │
│ ○ CHBOT ● 정상 3/3  │             └────┘                           │
│ ○ HWTC  ○ 미점검     │  ─────────────────────────────────────────   │
│                    │  인증 수단 · 계정 · 비밀번호 …                   │
│                    │                                              │
│                    │        ┏━━━━━━━━━━━━━━━━━━┓                   │
│                    │        ┃   점검 시작       ┃                   │
│                    │        ┗━━━━━━━━━━━━━━━━━━┛                   │
└────────────────────┴──────────────────────────────────────────────┘
   minmax(240,300)                    1fr
                                 ↑ 이 열만 내부 스크롤
```

**반응형 붕괴.** `< 1024px` 에서 1열로 스택하고, 좌측 목록이 가로 스크롤 칩 행이 된다. 좌측 항목 수는 `current_user.allowed_system_codes` 로 필터되므로 **1~7개**로 변한다(`routes_dashboard.py:67`) — 1개일 때도 레이아웃이 무너지지 않아야 한다.

**5문항 답**

| # | 답 |
| --- | --- |
| 1 지배 정보 | 모듈 의존성 그래프. 우측 열 상단 약 60%를 차지하고 노드가 현행보다 커진다 |
| 2 스크롤 소유권 | 우측 조건 열 하나. 좌측 목록과 실행 버튼은 고정 |
| 3 살아있음 | 좌측 목록의 오늘 상태 배지(§4.5) + 그래프 엣지 `is-active`/`is-muted` 전이(이미 구현됨) |
| 4 추출 컴포넌트 | `module-graph` 를 `app.js`/`app.css` 에서 떼어 **화면 폴더**로. `status-badge` 는 재사용. `components/` 승격 없음(D4) |
| 5 완료 신호 | `entries/execute.ts` · Vitest(그래프 레이아웃 계산) · Playwright 넌스크롤 회귀 |

### 4.4 왜 싼가 — 렌더 경로가 아니라 표시 규칙만 바뀐다

`execute.html:256` 은 지금도 **6개 시스템 폼을 전부 서버 렌더해 DOM 에 넣는다.** `<details>` 가 접고 있을 뿐이고, 각 폼은 `system.run_form` 으로 필드를 렌더하며 `execute.html:286` 이 `systems_payload` 를 JSON 으로 심는다.

따라서 마스터-디테일 전환은 **표시 규칙 변경**이다. 선택된 폼 하나만 보이면 되고, 폼 마크업 · `data-role` 속성 · 기존 폼 바인딩은 그대로 산다. 새 API 도, 클라이언트 템플릿도 필요 없다.

사라지는 것: `<details>`/`open` 상태 관리(`app.js:530` `bindSystemCardExpand`)와 아코디언 CSS. 6개의 열림 상태가 `selectedSystem` 문자열 **하나**로 줄어든다.

### 4.5 데이터 경로 — 새 read model 없이 오늘 상태를 얻는다

`routes_dashboard.py:56` 의 `run_execute` 는 `systems` · `systems_payload` · `analyzer_status` · `email_status` 만 내려준다. 좌측 목록의 상태 배지에 필요한 오늘 상태는 없다.

`daily_dashboard.py` 가 이미 시스템별 상태를 계산해 `/api/dashboard/daily` 로 내보내고 있으므로 **클라이언트가 그 엔드포인트를 재사용한다**(D6, 사용자 결정). 라우트 컨텍스트 · 뷰모델 · 새 read model 모두 변경 0이다.

배지 렌더는 `components/status-badge` 를 쓴다 — 상태 라벨·톤이 서버 SSOT 를 거치므로 FG-003 · FG-006 을 자동으로 만족한다.

**실패 처리:** 이 호출이 실패해도 화면의 주 기능(실행)은 살아야 한다. 배지 영역만 비우고 나머지는 정상 동작한다.

---

## 5. 결정

| # | 결정 | 근거 |
| --- | --- | --- |
| **D1** | 화면 하나당 한 사이클(설계 → 계획 → 구현) | 6화면을 한 문서로 묶으면 첫 배포까지 아무것도 안 나온다. 사용자 결정 |
| **D2** | 순서는 **점검 실행 → 수트 → 런 → Run 이력 → 프리셋 → 예약** | 사용자 결정. 결과적으로 `app.js` 해체 순서와 일치하고(§1.2), 데모 동선(실행 → 진행 관찰 → 이력)과도 일치한다 |
| **D3** | Cycle 0 은 **팔레트 통일만.** 컴포넌트 추출은 화면별 | 로그 팔레트는 디자인 과제가 아니라 버그이고 화면 순서와 무관하다. 반면 컴포넌트 인터페이스는 화면 하나를 승격해보기 전에는 알 수 없다. **틀린 것만 먼저 고치고 모르는 것은 미룬다.** 사용자 결정 |
| **D4** | 한 화면에서만 쓰는 것은 `components/` 로 올리지 않는다 | 사이클 1 이 추측으로 컴포넌트 라이브러리를 짓는 것을 막는다. 두 번째 화면이 요구할 때 승격 |
| **D5** | 도착점은 **통일이 아니라 승격** — 모든 화면을 대시보드급 정보구조로 | 통일만으로는 "깨지지 않는" 데 그친다. 사용자 결정 |
| **D6** | 좌측 상태 배지는 `/api/dashboard/daily` **재사용** | 새 read model·라우트 변경 0. 대안(execute 컨텍스트에 상태 주입)은 라우트·뷰모델·템플릿 3층을 동시에 바꾼다. 사용자 결정 |
| **D7** | 예약 등록 폼(`execute.html:165~245`)을 이번 사이클에서 **옮기지 않는다** | 성격상 예약 관리(Cycle 6)의 것이지만 "실행하면서 바로 예약"이 의도된 동선일 수 있다. 우측 열 하단 접이식으로 유지하고 Cycle 6 에서 중복 여부를 판단한다. 사용자 결정 |
| **D8** | 마스터-디테일은 서버 렌더 폼 6개를 **유지한 채** 표시만 전환 | 렌더 경로를 바꾸지 않아 폼 바인딩·`data-role`·검증이 전부 산다(§4.4) |
| **D9** | 짧은 별칭은 **신설 `legacy-aliases.css`** 에 두고 사용처 51곳은 건드리지 않는다 | 사용처를 `-solid` 로 일괄 치환하면 Cycle 0 이 51곳 수정으로 부풀고, 화면별 사이클이 어차피 그 CSS 를 컴포넌트로 옮기며 지운다. `primitives.css` 는 "상태색은 `tokens.generated.css` 담당"을 명시하므로 거처가 아니다. 파일이 **소멸 조건을 자기 안에 적어** allowlist 와 같은 방식으로 줄어든다 |
| **D10** | `--st-idle` → `--st-pending-solid`, `--st-track` → `--c-gray-200`, `--st-active` → `--c-indigo-600` | `STATUS_TONES` 에 `idle` 은 없다. 의미상 "아직 점검 안 함" = `pending` 이다. `track`·`active` 는 애초에 상태색이 아니므로 `--st-` 이름을 떠나 중립 primitive 로 간다. 색이 미세하게 이동한다(`#b6b4ad` → `#a1a1aa`) — §4.1 의 "SSOT 로 수렴"과 같은 성격 |

---

## 6. 테스트와 게이트

| 대상 | 위치 | 단언 |
| --- | --- | --- |
| 팔레트 수렴 | 템플릿 렌더 테스트 | 6개 화면에 `--st-*` 재정의 0건 |
| FG-002 확장 | 게이트 테스트 | `templates/` · `static/*.js` 가 스캔 대상. allowlist 밖 파일의 hex 가 검출됨 |
| 그래프 레이아웃 | Vitest | `computeModuleDepth` · `computeModuleSubtreeHeight` 가 알려진 DAG 에 대해 기대 좌표를 낸다 |
| 넌스크롤 | Playwright | 1366 · 1920 · 2560 px 에서 `body` 세로 스크롤 0, 실행 버튼 가시 |
| 스크롤 소유권 | Playwright | 내부 스크롤을 갖는 요소가 우측 조건 열 하나 |
| 동작 불변 | 기존 `SPEC-UI-002` 테스트 | AC-001 Suite preset 검증 · AC-002 depends_on 통과 |
| 시스템 1개 | 템플릿 렌더 테스트 | `allowed_system_codes` 가 1개일 때 레이아웃이 성립 |

---

## 7. 리스크 · 한계

| 리스크 | 내용 | 대응 |
| --- | --- | --- |
| Cycle 0 이 화면 색을 실제로 바꾼다 | 6개 화면의 녹색·주황·빨강이 이동한다 | 의도된 결과다(§4.1). SSOT 를 로그 값으로 맞추는 반대 방향은 기각 — SSOT 는 `status_labels.py` 이고 메일 렌더러도 같은 값을 쓴다 |
| 그래프를 크게 하면 모듈 많은 시스템이 넘친다 | HOM 10 모듈이 최대 | `fitModuleGraphToViewport`(`app.js:332`)와 `data-graph-compact` 티어가 이미 있다. 우측 열 폭에 맞춰 재조정 |
| 마스터-디테일이 "여러 시스템 동시 준비"를 막는다 | 지금은 카드 여러 개를 펼쳐둘 수 있다 | 실측상 실행은 한 번에 하나다. SUITE 가 다중 실행을 담당한다. 잃는 것이 있으면 사이클 회고에서 되돌린다 |
| 사이클 6개가 길다 | 중간 이탈 시 절반만 승격된 상태 | 각 사이클이 독립 배포되고 완결된 화면을 남긴다(사용자 확인). Cycle 0 이 먼저 들어가 있어 최소한 색은 일관된다 |
| `app.js` 를 4회에 걸쳐 자른다 | 자르는 중간 단계에서 공용 함수가 양쪽에 필요 | 공용(`showToast` · `readErrorMessage` · `statusBadgeClassName`)은 마지막까지 `app.js` 에 남기고 Cycle 4 에서 정리한다 |

---

## 8. 이후 — 이 문서가 남기는 것

| 항목 | 비고 |
| --- | --- |
| Cycle 2~6 설계 문서 | 각 사이클 착수 시 작성. §4.2 의 5문항에 답해야 한다 |
| `/admin/*` 6화면 승격 | 임원·사용자가 `user` 역할이라 후순위. Cycle 0 의 팔레트만 적용받는다 |
| `/anomalies` · `/self-healing` · `/insights` 승격 | 이번 순서에 없다. 필요해지면 사이클을 추가한다 |
| 타입 스케일(`--fs-*`) | `2026-08-23-dashboard-mission-control-design.md` §3.7 (2단계) |
| 차트 통합(plotly 2종 제거, −5.5MB) | 같은 문서 §3.8 (3단계). `/insights` 승격과 함께 가는 것이 자연스럽다 |
| View Transitions | 페이지 전환 모핑. 네이티브 CSS + htmx `transition:true`, 신규 의존성 0 |
| `app.css` 1,411줄 분할 완료 | Cycle 1~6 이 절씩 떼어내면 `FG004_ALLOWLIST` 가 빈다 |

---

## 9. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§1.1 문제 정의 · §2.2 테마 축 비목표 · §3.1 스택 결정)
- 직전 작업: `docs/superpowers/specs/2026-08-23-dashboard-mission-control-design.md` · `docs/superpowers/specs/2026-08-24-wall-renewal-design.md`
- 이관 인계 목록: `docs/superpowers/specs/2026-08-22-frontend-elevation-p3-4-enforcement-design.md` §7
- 대체 대상 AC Spec: `docs/specs/dashboard/02-execute-page.md` (`SPEC-UI-002`)
- 게이트 SSOT: `scripts/check_frontend_gates.py` · `docs/CI.md`
- 상태 SSOT: `app/core/status_labels.py` → `app/web/frontend/styles/tokens.generated.css`
