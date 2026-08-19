# 프론트엔드 고도화 (Frontend Elevation) — Design

**작성일:** 2026-08-19
**상태:** 초안 (사용자 리뷰 대기)
**대상:** `app/web/templates/`, `app/web/static/`, `app/core/status_labels.py`, `scripts/ci/gates.py`, `scripts/check_frontend_gates.py`(신규), `app/api/routes_daily.py`, `app/api/routes_healing.py`, `app/api/routes_admin.py`

---

## 1. 문제

### 1.1 증상

이 도구를 처음 보는 사람(사내 동료·경영진)이 감탄하지 않는다. 원인은 기능 부족이 아니다.

### 1.2 백엔드와 프론트엔드의 비대칭

| 축 | 백엔드 | 프론트엔드 |
| --- | --- | --- |
| 구조 | 바운디드 컨텍스트 · Decider · 이벤트 소싱 | `app/web/static/app.js` 단일 파일 3,283줄 |
| 정적 검증 | AG-001~009 아키텍처 게이트 (CI 강제) | 린트·타입·테스트 전무 |
| 빌드 | `pyproject.toml` · ruff · pyright · 커버리지 게이트 | 툴체인 없음 (`package.json` 부재) |
| SSOT | 상태 라벨 SSOT (`app/core/status_labels.py`) | 하드코딩 hex 244개 (`app/web/static/*.css`) |
| 배포 | — | 외부 CDN 4종에 런타임 의존 |

프론트엔드는 실력 부족의 산물이 아니라 **도구 없이 맨손으로 지은 것**에 가깝다. `app/web/static/app.js:190` 의 `buildModuleGraphLayout`, `app.js:152` 의 `computeModuleDepth` 는 의존성 그래프 레이아웃 알고리즘을 직접 구현한 것이다. 문제는 실력이 아니라 **강제력의 부재**다.

### 1.3 근본 원인 1 — 상태 정의가 3중이고 이미 어긋나 있다

같은 개념("정상은 무슨 색이고 뭐라 부르는가")이 세 곳에 독립적으로 정의돼 있다.

| 위치 | 정의 내용 | 커버 범위 |
| --- | --- | --- |
| `app/core/status_labels.py:86,102` `*_badge_tone()` | 톤 분류 (백엔드 SSOT) | 9개 톤 |
| `app/web/static/app.js:1` `STATUS_BADGE_CLASSES` | Tailwind 유틸리티 클래스 | 11개 키 |
| `app/web/static/dashboard.css:14` `--st-*` | CSS 커스텀 프로퍼티 | **6개** |

`app/web/static/app.js:15` 의 `STATUS_DISPLAY_LABELS` 는 `status_labels.py` 의 `MODULE_STATUS_LABELS` 를 **한국어 문자열까지 그대로 복제한 사본**이다 (`"이상징후"`, `"점검실패"`, `"제외"`).

이미 발생한 드리프트:

- `dashboard.css` 는 `skipped` / `cancelled` 톤을 정의하지 않아 `--st-idle` 로 흡수된다. 백엔드는 두 상태를 구분하지만 일간 대시보드는 구분하지 못한다.
- `--st-*` 토큰은 `dashboard.css` 에만 존재한다. 나머지 화면 8개 JS 파일(`healing`, `insights`, `anomalies`, `schedules`, `presets`, `admin-*`)은 각자 `bg-emerald-100` 류 리터럴을 별도로 박아두었다.

**상태가 하나 추가되면 프론트가 조용히 어긋난다. 이를 막는 장치가 없다.**

### 1.4 근본 원인 2 — 외부 CDN 런타임 의존

```
app/web/templates/base.html:11   Pretendard      (cdn.jsdelivr.net)
app/web/templates/base.html:12   @tailwindcss/browser@4  (cdn.jsdelivr.net)
app/web/templates/dashboard.html:53  htmx 2.0.4  (unpkg.com)
app/web/templates/dashboard.html:54  alpinejs 3.14.8 (unpkg.com)
```

`@tailwindcss/browser` 는 **브라우저에서 런타임에 CSS 를 생성하는 개발 전용 빌드**다. 실제 손해:

- 매 페이지 로드마다 CSS 생성 → FOUC(스타일 없는 화면이 번쩍임). 회의실 데모에서 가장 먼저 눈에 띄는 결함이다.
- 사내망 정책 변경·CDN 장애 시 **화면이 통째로 깨진다.** 폰트까지 같은 CDN 에 걸려 있어 단일 장애점이다.

### 1.5 근본 원인 3 — 자산이 이미 있는데 화면에 없다

필요한 계산은 이미 구현돼 있다. 문제는 **배치**다.

| 자산 | 구현 위치 | 현재 노출 |
| --- | --- | --- |
| 이번 달 자동 복구 건수 · 무인 통과율 · MTTR · 30일 추이 · 만성 지점 | `app/contexts/healing/metrics.py:build_healing_metrics()` | `/self-healing` 하위 |
| `manual_seconds_saved` (수동 대비 절감 시간) | `app/core/stats_models.py` + `ModuleSettings.estimated_manual_seconds` | `/admin/stats` — **관리자 권한 한정** |
| `HealingPatch` — 자동 생성 셀렉터 수정 diff + 사람 승인 게이트 | `app/contexts/healing/patch_builder.py` | 자가 치유 센터 하위 탭 |
| `recovered` 플래그 (RecoveryTier 재시도로 통과한 모듈) | `SPEC-RUN-006` 루프 | Run 상세 한 줄 |
| AI 실패 분석 | `app/ai/failure_analyzer.py` | Run 상세 한 줄 |

특히 `manual_seconds_saved` 는 경영진 대상 핵심 지표인데 **관리자 메뉴 안에 잠겨 있어 경영진이 볼 수 없다.**

---

## 2. 목표 / 비목표

### 2.1 목표

1. 프론트엔드에 백엔드와 동등한 **강제력**(빌드·타입·게이트)을 부여한다.
2. 상태 정의를 `app/core/status_labels.py` **단일 SSOT** 로 수렴시키고, 어긋남을 CI 가 막는다.
3. 외부 CDN 런타임 의존을 **0** 으로 만든다.
4. 이미 계산되는 자산(자동 복구·절감 시간·승인 대기)을 **일간 현황 메인 화면**에 올린다.
5. 같은 컴포넌트가 4개 장면(회의실 데모 · 매일 쓰는 화면 · 자동 리포트 · 상황판)에 재사용되게 한다.

### 2.2 비목표 (명시적 YAGNI)

- SPA 전환 · React/Vue 도입
- **다크모드 · 테마 시스템** — 라이트 단일 팔레트로 확정. 테마 축 자체를 만들지 않는다.
- Storybook 등 디자인 시스템 문서 사이트
- 시각 회귀 스냅샷 전면 도입
- 국제화 — UI 문자열은 한국어 고정 (`AGENTS.md` 제약)

### 2.3 성공 기준

| 기준 | 측정 |
| --- | --- |
| 외부 CDN 의존 | 템플릿 내 외부 `<script>`/`<link>` 0건 (FG-001 이 강제) |
| 상태 정의 중복 | `status_labels.py` 외 상태 라벨·색 정의 0건 (FG-003 이 강제) |
| 하드코딩 hex | `frontend/` 내 0건 (FG-002 가 강제) |
| 절감 시간 가시성 | 비관리자 계정으로 일간 현황에서 확인 가능 |
| FOUC | CSS 가 빌드 산출물로만 제공(런타임 생성 0). FG-001 + manifest 경유(FG-005)로 기계 검증 |

---

## 3. 설계

### 3.1 스택 — 프레임워크를 도입하지 않는다

`app/web/templates/dashboard.html` 이 이미 htmx + Alpine + 서버 프래그먼트 방식을 검증했다(`hx-get="/api/dashboard/daily/fragments/kpi"`). 이를 우연이 아니라 **선택**으로 승격한다.

**근거:** 백엔드가 CQRS 로 읽기 모델(`RunView`/`SuiteView`)을 서버에서 이미 완성한다. 클라이언트에 상태를 한 벌 더 복제할 이유가 없다. SPA 프레임워크를 넣으면 서버 읽기 모델과 클라이언트 스토어가 같은 개념을 두 번 모델링하게 되어 — §1.3 의 3중 정의와 동일한 병을 구조 레벨에서 재발시킨다.

결정:

- **마크업 SSOT = Jinja 매크로.** 서버 최초 렌더와 htmx/WS 갱신이 같은 매크로를 통과한다. 현재 `dashboard/partials/_macros.html` 과 `app.js:createRunListItem()` 이 서로 다른 DOM 을 생성하는 이중 구조가 근본 소멸한다.
- **TypeScript 담당 영역:** Alpine 컴포넌트, WS 클라이언트, 순수 로직(ModuleGraph 레이아웃 · 포맷터).
- **CDN 4종 전부 npm self-host:** Tailwind, htmx, Alpine, Pretendard.

### 3.2 빌드 — Vite 다중 엔트리 (SPA 아님)

Jinja 서버 렌더를 유지한다. 현재 페이지마다 전용 JS 하나를 로드하는 형태가 Vite multi-entry 와 1:1 로 대응한다.

```text
app/web/
  frontend/                 # 신규 — 소스
    entries/                # 페이지별 엔트리 (dashboard.ts, schedules.ts, ...)
    components/             # 재사용 단위 (§3.5)
    lib/                    # api 클라이언트 · ws 클라이언트 · 포맷터
    styles/
      tokens.generated.css  # ← status_labels.py 에서 생성 (§3.4)
      base.css
  static/dist/              # 빌드 산출물 (해시 파일명) — gitignore
  static/                   # 기존 파일: 이관 완료분부터 삭제
```

`vite.config.ts` 에 `build.manifest: true` 를 켜고, Jinja 에 `{% asset "dashboard" %}` 매크로를 두어 manifest 로 해시 파일명을 해석한다.

현재 `base.html:13` 의 `app.css?v=16` 수동 캐시버스팅이 사라진다 — **`v=` 를 올리는 것을 잊어 옛 CSS 가 배포되는 사고가 구조적으로 불가능해진다.**

### 3.3 토큰 3층

```text
primitive   --c-emerald-500: #10b981;          팔레트. 의미 없음
    ↓
semantic    --st-passed: var(--c-emerald-500);  ★ status_labels.py 가 생성
            --st-passed-surface / -text / -border / -solid
    ↓
component   .badge[data-tone] { ... }           토큰만 참조. hex 금지(FG-002)
```

라이트 단일 팔레트. 테마 전환 기제를 만들지 않는다.

**톤 축 (9개, `status_labels.py` 의 `*_badge_tone()` 반환값과 1:1):**

`passed` · `anomaly` · `error` · `running` · `waiting_input` · `blocked` · `skipped` · `cancelled` · `pending`

현재 `dashboard.css` 가 `waiting_input` 을 `running` 과 같은 파랑으로 뭉개고 있으나, 이는 **사람의 OTP 입력을 기다리는 상태**로 상황판에서 가장 눈에 띄어야 한다. 독립 톤으로 분리하고 유일하게 깜빡이는 상태로 표현한다.

### 3.4 상태 토큰은 파이썬이 생성한다

빌드 스텝을 추가해 `app/core/status_labels.py` 로부터 두 파일을 **생성**한다.

| 생성물 | 내용 |
| --- | --- |
| `frontend/styles/tokens.generated.css` | 9개 톤 × `surface`/`text`/`border`/`solid` semantic 변수 |
| `frontend/lib/status.generated.ts` | `type StatusTone = "passed" \| ...` union + 라벨 맵 |

생성물은 커밋하되 **CI 가 재생성 후 diff 를 검사**한다 — `docs_consistency` 게이트와 동일한 패턴이다.

`app.js:15` 의 `STATUS_DISPLAY_LABELS` 복제본은 삭제되고 생성물로 대체된다. 한국어 상태 라벨의 SSOT 가 `status_labels.py` 하나가 된다.

**효과 연쇄:** `status_labels.py` 에 상태를 추가하면 →
1. 생성 스텝이 토큰·타입을 갱신, 누락 시 `frontend_gates` 가 diff 로 차단
2. `status.generated.ts` union 이 넓어져 스위치 누락을 `tsc` 가 차단
3. 컴포넌트는 토큰만 쓰므로 hex 추가 경로가 없음 (FG-002)

### 3.5 컴포넌트 경계 — Jinja 매크로 ↔ TS 동작 페어

```text
components/status-badge/
  macro.jinja      # 마크업 (서버 최초 렌더 · htmx 프래그먼트 공용)
  index.ts         # 동작 (WS 갱신 시 클라이언트 렌더)
  styles.css       # 토큰만 참조
```

1차 컴포넌트 (기존 코드에서 이미 중복되는 것만):

| 컴포넌트 | 현재 중복 위치 |
| --- | --- |
| `StatusBadge` | `_macros.html` + `app.js:1,15` + 8개 JS 파일 |
| `KpiCard` | `dashboard/partials/zone_a_kpi.html` + `app.css` `.status-metric-card` |
| `SystemMatrix` | `dashboard/partials/zone_b_matrix.html` + `dashboard.js` |
| `RunTimeline` | `app.js:createSuiteStripRow` + `createRunChip` |
| `ModuleGraph` | `app.js:152,190,363` (레이아웃 알고리즘 약 400줄) |
| `LiveLog` | `run.html` + WS 핸들러 |

`ModuleGraph` 는 순수 레이아웃 계산과 DOM 렌더가 섞여 있다. 순수 계산만 분리하면 **프론트엔드에서 최초로 단위 테스트 가능한 로직**이 된다 — 백엔드가 domain 을 I/O 에서 분리한 것과 동형의 수술이다.

### 3.6 프론트 게이트 (FG-001~005)

`scripts/check_frontend_gates.py` 를 신규 추가한다. `scripts/check_architecture_gates.py` 의 AG 규칙과 동형.

| 규칙 | 내용 | 차단하는 재발 |
| --- | --- | --- |
| FG-001 | 템플릿에 외부 CDN `<script>`/`<link>` 금지 | §1.4 |
| FG-002 | `frontend/` 내 하드코딩 hex 금지 (토큰만) | 244개 재발 |
| FG-003 | 상태 색·라벨은 `status.generated.ts` 경유만 | §1.3 |
| FG-004 | 엔트리·컴포넌트 파일 400줄 상한 | `app.js` 3,283줄 재발 |
| FG-005 | `static/` 직접 참조 금지 (manifest 경유) | 캐시버스팅 사고 |

`scripts/ci/gates.py` 의 `GATE_COMMANDS` 에 `frontend_gates`, `typecheck_web`(`tsc --noEmit`), `eslint`, `stylelint` 를 추가하고 **Tier 0** 에 배치한다. `ci_config_valid` 가 경로 실재성을 이미 검사하므로 그 보호를 자동으로 받는다.

### 3.7 TypeScript 이관 — 빅뱅 없이

`tsconfig` 를 `allowJs: true`, `checkJs: false` 로 시작한다. 기존 15개 JS 파일은 그대로 동작하고, 이관한 화면만 `.ts` 로 승격한다. `typecheck_web` 게이트는 첫날부터 통과하며 이관에 따라 커버 범위가 늘어난다 — 백엔드의 `pyright_decider` 가 전체가 아닌 decider 만 검사하는 전략과 동일하다.

### 3.8 일간 현황 화면 구조 (B안 확정)

```text
┌─────────────────────────────────────────────────────────┐
│ 오늘 점검은 정상입니다                      ← 결론 한 문장 │
│ 8월 19일 · 34/36 모듈 정상 · 이상징후 2건 · 갱신 09:14    │
├──────────┬──────────┬──────────────┬────────────────────┤
│ 통과율    │ 스스로    │ 내 승인 대기  │ 이번 달 절감 [추정] │
│ 94%      │ 복구 7건  │ 2건          │ 310h               │
│ ▲+3%p    │ 무인 82%  │ diff 보기 →  │ 1,240회 × 추정치    │
├──────────┴──────────┴──────────────┴────────────────────┤
│ 시스템 매트릭스 (6)                                       │
└─────────────────────────────────────────────────────────┘
```

설계 의도:

- **맨 위 한 문장이 결론.** 경영진이 3초 안에 판단한다.
- **각 KPI 에 근거 한 줄이 붙는다.** §3.9 정직성 규율의 레이아웃 구현.
- **"내 승인 대기" 만 색을 분리한다.** 나머지 3개는 *보고하는* 숫자지만 이것은 *행동을 요구하는* 숫자다. 매일 쓰는 담당자에게 이 화면의 존재 이유가 이 카드다.
- **`KpiCard` 가 그대로 상황판(대형 모드)·메일 리포트(인라인)로 재사용된다.** 이것이 A안(히어로 종속)·C안(사이드 레일 폭 종속) 대신 B안을 택한 결정적 이유다.

### 3.9 정직성 규율 — 추정치를 부풀리지 않는다

`manual_seconds_saved` 는 `ModuleSettings.estimated_manual_seconds`(사람이 입력한 추정치)에서 파생된 **추정값**이다. 이를 단독 수치로 제시하면 "그 숫자의 근거는?" 이라는 질문 한 번에 신뢰가 무너진다.

규칙:

1. 절감 시간 옆에 **산출 근거를 항상 병기** — "1,240회 × 모듈별 수동 추정치" + 추정치 기준일
2. **실측값과 추정값을 시각적으로 구분** — 실측: 실행 횟수 · 복구 건수 · MTTR · 통과율 / 추정: 절감 시간
3. 추정 근거 화면으로 가는 링크를 숫자에 직접 연결

이는 최근 커밋 `104c714 docs(run): tier 2 가 아직 로그인 재주행이 아님을 정직하게 명시` 가 보여준 프로젝트 문화를 UI 에 적용한 것이다. **한계를 먼저 말하는 대시보드가 더 오래 신뢰받는다.**

### 3.10 백엔드 변경 (최소)

| 작업 | 이유 |
| --- | --- |
| `manual_seconds_saved` 집계를 관리자 밖으로 여는 읽기 엔드포인트 | 현재 관리자 권한 한정 (§1.5) |
| `build_healing_metrics` 요약본을 일간 대시보드 API 에 합류 | 이미 계산됨, 노출만 |
| 추정 산출 근거 응답 필드 | §3.9 |

**백엔드 신규 도메인 로직 0건.** 전부 노출 · 권한 · 조립이다.

---

## 4. 이관 계획

각 스텝은 독립 배포 가능하며, 어느 지점에서 중단해도 그때까지의 이득이 남는다.

| Step | 내용 | 화면 변화 | 중단 시 남는 이득 |
| --- | --- | --- | --- |
| **0** | Vite multi-entry · npm self-host · manifest 매크로 · **CDN 제거** | 없음 (픽셀 동등) | 외부 CDN 장애 리스크 제거 |
| **1** | 토큰 생성기 + FG 게이트 + hex 244개 치환 | 거의 없음 | 상태 드리프트 영구 봉인 |
| **2** | `StatusBadge` 컴포넌트화 · `STATUS_DISPLAY_LABELS` 삭제 | 미세 통일 | 중복 10군데 제거 |
| **3** | `KpiCard` + **일간 현황 B안** | 큼 | 회의실 데모 장면 해결 |
| **4** | Run 상세 라이브 — 모듈 점등 · `recovered` 배지 · AI 분석/치유 이력 인라인 | 큼 | 매일 쓰는 화면 장면 해결 |
| **5** | 상황판 `/wall` — `KpiCard` 대형 모드 재사용 | 신규 | 상황판 장면 해결 |
| **6** | 메일 리포트 — 동일 KPI 를 인라인으로 | 신규 | 리포트 장면 해결 |
| **7** | 잔여 화면 이관 (schedules · presets · anomalies · admin) | 통일 | `app.js` 3,283줄 소멸 |

**Step 0~2 는 화면이 바뀌지 않는 것이 성공 기준이다.** 기반 공사와 화면 개선을 같은 스텝에 섞지 않는다 — 섞으면 "예뻐졌는데 무언가 깨졌다" 가 되어 롤백 단위가 사라진다.

### 4.1 구현 계획 분할

Step 0~7 은 단일 구현 계획으로 담기에 크다. 계획 문서를 3개로 나눈다.

| 계획 | 범위 | 성격 |
| --- | --- | --- |
| **P1 — 기반** | Step 0~2 | 화면 불변. 빌드·토큰·게이트만. 이 스펙의 §3.1~§3.7 |
| **P2 — 일간 현황** | Step 3 (+ §3.10 백엔드 노출) | 첫 가시적 변화. 이 스펙의 §3.8~§3.10 |
| **P3 — 확장 표면** | Step 4~7 | Run 상세 · 상황판 · 리포트 · 잔여 이관 |

P1 완료 전에는 P2 를 시작하지 않는다 — P2 의 `KpiCard` 가 P1 의 토큰·컴포넌트 규약에 의존한다. P3 은 P2 의 `KpiCard` 를 재사용하므로 마찬가지로 순차다.

---

## 5. 검증

| 대상 | 방법 |
| --- | --- |
| 순수 로직 (ModuleGraph 레이아웃 · 포맷터) | **Vitest** — 프론트엔드 최초 단위 테스트 |
| 토큰·타입 생성물 | CI 재생성 후 diff 게이트 (`docs_consistency` 동일 패턴) |
| 규칙 위반 | `frontend_gates` (FG-001~005) |
| 타입 | `tsc --noEmit` (`allowJs`, 이관분 한정) |
| 화면 스모크 | 각 페이지가 **콘솔 에러 0** 으로 렌더되는지 (기존 Playwright 자산 활용) |

**DoD:** Step 0/1 은 "이전과 픽셀 동등", Step 3 이후는 "명시적 개선 + 스모크 통과".

---

## 6. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| Step 7 이 길다 | 잔여 화면 5개 이관은 지루하며 "우와" 에 기여하지 않는다 | 미이관 화면은 구 스타일로 계속 동작한다. 무기한 연기 가능 |
| htmx+Alpine 선택은 되돌리기 어렵다 | 향후 SPA 가 필요해지면 Step 3~7 결과물 상당수를 폐기하게 된다 | 현 시점에 SPA 필요성의 근거가 없다 (§3.1). 재평가 시점은 "서버 프래그먼트로 표현 불가능한 상호작용이 등장할 때" |
| 절감 시간은 끝까지 추정치다 | §3.9 의 정직한 표기가 임팩트를 다소 깎는다 | 의도된 절충. 신뢰가 임팩트보다 오래간다 |
| 생성물 커밋 방식 | `tokens.generated.*` 를 커밋하면 diff 노이즈가 생긴다 | 생성물을 커밋하지 않으면 빌드 없이 코드를 읽을 수 없다. `docs_consistency` 와 같은 트레이드오프를 이미 수용 중이므로 일관되게 커밋 |

---

## 7. 참조

- 브레인스토밍 산출 와이어프레임: `.superpowers/brainstorm/1712-1787066624/content/daily-layout.html` (gitignore 대상, 참고용)
- 기존 아키텍처 SSOT: `docs/E2E_ARCHITECTURE.md`
- CI 게이트 SSOT: `scripts/ci/gates.py`, `docs/CI.md`
- 문서 규칙: `docs/DOCS_GOVERNANCE.md`
