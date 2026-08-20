# 프론트엔드 고도화 P3-2 (상황판 /wall) — Design

**작성일:** 2026-08-20
**상태:** 초안 (사용자 리뷰 대기)
**상위 설계:** `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§4 Step 5)
**선행:** P1 기반 · P2 일간 현황 · **P3-1 Run 상세 라이브** (PR #133, 병합 전 — 이 브랜치는 P3-1 위에 쌓여 있다)
**대상:** `app/api/routes_wall.py`(신규), `app/web/templates/wall.html`(신규), `app/web/frontend/entries/wall.ts`(신규), `app/web/frontend/styles/wall.css`(신규), `app/contexts/insights/application/wall_view.py`(신규), `vite.config.ts`, `app/core/settings.py`, `app/composition/container.py`, `docs/INSTALL.md`, `.env.example`

---

## 1. 문제

### 1.1 상황판이 없다

상위 설계 §2.1 목표 5 — *"같은 컴포넌트가 4개 장면(회의실 데모 · 매일 쓰는 화면 · 자동 리포트 · 상황판)에 재사용되게 한다"*. 이 중 **상황판만 라우트가 존재하지 않는다.** `app/api/routes_dashboard.py` 에 `/wall` 계열 경로가 없다.

### 1.2 근본 제약 — 상황판은 로그인을 유지할 수 없다

`app/contexts/identity/jwt.py:11`

```python
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7일
```

그리고 `app/contexts/identity/dependencies.py:37` 은 비인증 상태에서 `/api/` 가 아닌 경로를 **`/login` 으로 리다이렉트**한다.

키보드 없는 상시 디스플레이에서 이 조합의 결과:

- 7일마다 사람이 걸어가서 다시 로그인해야 한다
- 만료되는 순간 **사무실 벽에 로그인 폼이 떠 있는다**

즉 기존 인증 구조를 그대로 쓰는 선택지는 실질적으로 없다.

### 1.3 선례는 이미 있다

`app/api/routes_trigger.py:45` `GET /m/{trigger_token}` 이 URL 토큰 기반 비로그인 페이지다. 모바일 즉시 점검용으로 이 패턴이 이미 운영되고 있다.

### 1.4 P3-1 스펙의 가정 정정

P3-1 스펙 §2.2 는 *"Step 5 의 `/wall` 이 인증 불필요 읽기 경로를 만들 때 (자동 스모크 테스트를) 반드시 붙인다"* 고 적었다. 이는 **결과를 미리 단정한 서술**이었다. `/wall` 의 인증 모델은 이 문서에서 비로소 결정되며(§2 D1), 스모크 테스트의 실현 범위도 CI 정책에 의해 제한된다(§3.6).

---

## 2. 결정

| # | 결정 | 이유 |
| --- | --- | --- |
| D1 | **인증 없이 전사 공개.** `/wall` 은 로그인을 요구하지 않는다 | 상시 디스플레이에 로그인 만료가 치명적이고(§1.2), 사내망 도구이며 상황판의 성질(누구나 지나가며 본다)에 맞다. 토큰 URL(§1.3)보다 단순하고 자동 스모크가 가능해진다 |
| D2 | **`E2E_WALL_ENABLED` 로 끌 수 있게 한다. 기본값 `true`** | D1 의 대가로 즉시 차단 스위치를 둔다. 기본값 `false` 는 배포 시 켜는 것을 잊어 "왜 안 되지" 사고를 만든다 |
| D3 | **JSON API 를 새로 만들지 않는다.** 페이지·프래그먼트 모두 서버 렌더 HTML | 비인증 표면을 최소화한다. 새 JSON 계약은 필드가 실수로 새는 경로를 하나 더 만든다 |
| D4 | **단일 화면 + 상태에 따라 지배 요소가 바뀐다** | 상황판의 직분은 "지금 정상인가" 하나다. 뷰 회전은 회의실에서 "그 숫자 어디 갔지"를 만들고 이상을 놓치게 한다 |
| D5 | **`dashboard.js` 의 밀도 시스템을 재사용하지 않는다** | 그 시스템은 다양한 창 크기·사이드바·모바일을 위한 것이다. 상황판은 고정 디스플레이 하나이고 사이드바가 없어 순수 CSS 로 충분하다. Step 7 이관 대상 파일에 의존을 늘리지 않는다 |
| D6 | **두 번째 Vite 엔트리를 만든다** | P1 §3.2 가 설계한 다중 엔트리 구조에 아직 소비자가 없었다. 상황판 전용 CSS 를 일반 페이지 번들에 얹지 않으면서, 그 구조를 처음으로 검증한다 |

---

## 3. 설계

### 3.1 라우트 — GET 2개, 부수효과 없음

```text
GET /wall              상황판 페이지 (전체 렌더)
GET /wall/fragment     갱신용 HTML 프래그먼트 (htmx)
```

- 둘 다 **비인증**. `get_current_user` 의존을 걸지 않는다
- `E2E_WALL_ENABLED=false` 면 둘 다 **404**
- POST/PUT/DELETE 없음. 페이지에 링크·버튼을 두지 않는다 (조작하지 않는 화면)
- `app/api/routes_wall.py` 로 분리한다 — `routes_dashboard.py` 는 전부 인증 경로이므로, 비인증 라우트를 그 안에 섞으면 다음 사람이 실수로 인증 의존을 빼먹거나 반대로 붙일 위험이 생긴다

### 3.2 데이터 — P2 것을 그대로 재사용, 신규 쿼리 0건

`app/orchestrator/queries/daily_summary_queries.py:32` `get_daily_summary` 를 다음 인자로 호출한다.

| 인자 | 값 | 이유 |
| --- | --- | --- |
| `user_id` | `None` | 상황판에 "내 기여분"은 의미가 없다 |
| `allowed_system_codes` | `None` | 전사 상황판이므로 전 시스템 |
| `is_admin` | `False` | 절감 카드의 관리자 링크를 비운다 — 클릭하지 않는 화면 |

**계약: 상황판 렌더는 `my_seconds` 를 사용하지 않는다.** `user_id=None` 이면 값이 0 이 되지만, 값이 아니라 **사용 금지**를 테스트로 강제한다 — 나중에 누가 `user_id` 를 채우면 조용히 노출되기 때문이다.

### 3.3 지배 요소 판정 — 순수 함수

`app/contexts/insights/application/wall_view.py` (I/O 없음, `build_daily_summary` 와 같은 순수 빌더 패턴):

```python
def build_wall_view(summary: dict[str, Any]) -> dict[str, Any]
# → {"dominant": {...}, "systems": [...], "strip": [...]}
```

우선순위:

| 순위 | 조건 | 지배 요소 |
| --- | --- | --- |
| 1 | `attention` 중 `tone == "waiting_input"` 이 하나라도 있음 | **OTP 입력 대기** — 사람이 지금 움직여야 한다 |
| 2 | `totals.error > 0` | 점검실패 |
| 3 | `totals.anomaly > 0` | 이상징후 |
| 4 | `totals.running > 0` | 진행 중 (지배가 아니라 히어로 부제로 표시) |
| 5 | 그 외 | **거대한 "정상"** |

**1순위를 `attention[0]` 로 쓰지 않는 이유:** `app/contexts/insights/application/daily_dashboard.py:51` 의 `_ATTENTION_RANK` 는 `error`(50) > `anomaly`(40) > `running`(30) 이므로, OTP 대기가 실패와 겹치면 `attention[0]` 이 되지 못한다. 상황판 기준으로는 **이미 끝난 실패보다 지금 막혀서 사람을 기다리는 Run 이 더 급하다.** 공유 `_ATTENTION_RANK` 를 바꾸면 일간 대시보드까지 영향을 받으므로, 상황판이 `attention` 을 훑어 `waiting_input` 을 직접 찾는 **로컬 규칙**으로 처리한다.

`WAITING_INPUT` 은 `daily_dashboard.py:35` `_module_bucket` 에서 `running` 버킷에 합쳐지지만, `attention` 항목의 `tone` 에는 `module_status_badge_tone` 을 거쳐 살아 있다. **따라서 새 백엔드 필드가 필요 없다.**

### 3.4 화면 3층

```text
┌──────────────────────────────────────┐
│                                      │
│          오늘 점검  정상             │  ← 히어로 = 지배 요소
│           34/36 모듈                 │
│                                      │
│  HOM  MHM  FP   HRP  HWTC  CHBOT     │  ← 매트릭스 (대형)
│  ███  ███  ███  ███  ███   ███       │
│                                      │
│  복구 7 · 대기 2 · 이번 달 310h      │  ← 성과 스트립
└──────────────────────────────────────┘
```

이상 발생 시 히어로가 그 건에 자리를 넘긴다:

```text
│  ⚠  HOM · 로그인                     │
│     점검실패                         │
│     09:14 · 3분 전                   │
```

매트릭스와 성과 스트립은 두 상태에서 동일하다 — 지배 요소만 교체된다.

### 3.4.1 매트릭스는 재사용하지 않고 새로 만든다

기존 `app/web/templates/dashboard/partials/zone_b_matrix.html` 은 11줄이며 `_macros.html` 의 `system_row` 매크로를 임포트한다. 재사용이 싸 보이지만 하지 않는다.

| 재사용의 대가 | 내용 |
| --- | --- |
| **알려진 위반을 끌어들인다** | `_macros.html` 은 `FG006_ALLOWLIST` 에 있다 — 상태→글리프 맵(`'passed': '✓', 'anomaly': '!', …`)을 들고 있기 때문이다. 갓 만든 파일이 그 중복에 의존하게 된다 |
| **`dashboard.css` 에 묶인다** | `system_row` 의 마크업은 `.dash-sys-row` 계열 규칙으로 스타일링되고, 그 규칙은 `.dash__systems[data-density=…]` 밀도 선택자와 얽혀 있다. D5 에서 밀도 시스템을 쓰지 않기로 했는데 CSS 는 따라온다 |
| **Step 7 영역에 의존이 늘어난다** | `_macros.html`·`dashboard.css` 는 이관 대상이다. 상황판이 그 위에 서면 이관이 더 어려워진다 |

대신 `wall.html` 안에 상황판 전용 매트릭스 마크업(약 40줄)을 둔다. 상태 표현은 `status_badge_view` 를 쓰므로 **FG-006 을 처음부터 통과**하고, 스타일은 `wall.css` 가 단독으로 책임진다.

**정직하게:** 마크업 중복이 하나 생긴다. 다만 상황판의 매트릭스는 3~5m 거리용이라 시각 요구가 달라(모듈 라벨 없음, 큰 블록) 실제로 같은 마크업을 쓰기 어렵다. Step 7 이 `_macros.html` 의 글리프 맵을 정리한 뒤 공통화를 재검토할 여지로 남긴다.

### 3.5 `kpi_card` 재사용 — P2 약속의 정직한 평가

P2 가 B안(밴드 교체)을 택한 근거 중 하나가 *"KpiCard 가 상황판에서 대형 모드로 재사용된다"* 였다. **부분만 실현된다.**

| 카드 | 상황판에서 |
| --- | --- |
| 스스로 복구 | ✅ `size="lg"` 로 재사용 |
| 내 승인 대기 | ✅ `size="lg"` 로 재사용 |
| 이번 달 절감 | ✅ `size="lg"` 로 재사용 |
| 통과율 | ❌ **쓰지 않는다** — 히어로가 "정상 · 34/36 모듈"로 흡수해 중복이다 |

4장 중 3장 재사용이다. 약속이 거짓은 아니지만 "그대로 재사용"은 과장이었다. `kpi-card/styles.css` 에 `data-size="lg"` 분기를 추가하는 확장이 필요하다.

### 3.6 스모크 테스트 — 세 번 미룬 항목을 정직하게 좁힌다

P1·P2·P3-1 이 모두 "인증 불필요 경로가 없다"는 이유로 미뤘다. `/wall` 이 그 경로를 만들지만, **`docs/CI.md:3` 이 "라이브 Playwright E2E 는 CI 밖" 을 정책으로 못 박고 있다.** 브라우저가 필요한 "콘솔 에러 0" 은 CI 게이트가 될 수 없다.

| 항목 | 수단 | CI 게이트 |
| --- | --- | --- |
| `/wall` 이 200 으로 렌더되고 기대 구조를 담는지 | pytest + TestClient | ✅ |
| `E2E_WALL_ENABLED=false` → 404 | pytest | ✅ |
| `my_seconds` 미사용 | pytest | ✅ |
| 지배 요소 판정 5경로 | pytest (순수 함수) | ✅ |
| **브라우저 콘솔 에러 0** | `scripts/` 의 수동 Playwright 스크립트 | ❌ 정책상 불가 |

**따라서 이 항목은 "절반 해소" 로 기록한다.** 렌더 스모크는 CI 에 들어가고, 콘솔 에러 검증은 실행 가능한 스크립트로 남지만 게이트는 아니다. 해결됐다고 적지 않는다.

### 3.7 두 번째 Vite 엔트리

`vite.config.ts:17-19` 는 현재 `main` 단일 엔트리다. P1 §3.2 가 페이지별 엔트리 구조를 설계하고 `app/web/templates/_assets.html` 매크로가 `entry` 인자를 이미 받지만, **소비자가 없어 검증되지 않은 상태**였다.

```text
app/web/frontend/entries/wall.ts     htmx + wall.css 만
app/web/frontend/styles/wall.css     상황판 전용 레이아웃·타이포
```

- `wall.html` 은 `asset_styles("entries/wall.ts")` / `asset_script("entries/wall.ts")` 로 참조
- Alpine 과 `status-badge` TS 동작은 로드하지 않는다 — 조작이 없으므로 불필요하다
- **부수 효과:** P1 의 다중 엔트리 구조가 처음으로 실제 검증된다. 동작하지 않으면 P1 설계에 결함이 있다는 뜻이고, 지금 드러나는 편이 낫다

### 3.8 대형 스케일링 — 순수 CSS

- `clamp()` + `vmin` 기준 타이포로 1080p·1440p·4K 에서 비율 유지
- `base.html` 을 상속하지 않는 독립 레이아웃 (사이드바·모바일 네비 없음)
- `overflow: hidden` + `100dvh` — 넌스크롤
- 색은 전부 P1 토큰 (FG-002)

`dashboard.js` 의 밀도 시스템(`syncRowPartition`·`fitAndPartition`·`data-density`)을 재사용하지 않는다(D5).

### 3.9 갱신

`app/web/static/dashboard.js:284` 의 패턴 — `setInterval` + `document.hidden` 가드 + 커스텀 이벤트 → htmx 재요청 — 을 `wall.ts` 에 상황판 전용 간소 버전으로 구현한다(약 15줄). 복사가 아니라 같은 형태의 최소 구현이다.

주기는 **15초**로 둔다 — 일간 대시보드보다 짧게, 상황판의 존재 이유가 "살아있음" 이기 때문이다. 부하가 문제되면 늘릴 수 있게 상수 하나로 노출한다(env 는 만들지 않는다 — 조절 필요가 확인되지 않았다).

### 3.10 점등

P3-1 이 만든 `status-badge` 의 `running` 숨쉬기·`waiting_input` 맥동과 `prefers-reduced-motion` 가드를 그대로 받는다.

상황판에서만 추가: **OTP 대기가 지배 요소일 때 히어로 전체가 맥동한다.** 3~5m 거리에서 배지 크기의 맥동은 보이지 않는다. 이 애니메이션도 `prefers-reduced-motion: reduce` 에서 정지한다.

### 3.11 게이트는 처음부터 적용된다

`wall.html` 은 FG-001~006 아래에서 태어난다. 특히 **FG-006** 이 상태→표현 매핑 중복을 막으므로 `run.html` 이 겪은 병(자체 `status_pill` 맵)을 애초에 만들 수 없고, `status_badge_view` 와 `status-badge` 매크로를 쓰게 된다. `FG006_ALLOWLIST` 에 추가하지 않는다.

---

## 4. 목표 / 비목표

### 4.1 성공 기준

| 기준 | 측정 |
| --- | --- |
| 로그인 없이 접근 | 인증 쿠키 없이 `/wall` 200 |
| 차단 스위치 | `E2E_WALL_ENABLED=false` → 404 |
| 프라이버시 | 렌더 결과에 `my_seconds`·사용자 식별자 0건 |
| 지배 요소 | 5경로(OTP 대기 / 실패 / 이상 / 진행 / 정상) 각각 올바른 히어로 |
| OTP 우선 | 실패와 OTP 대기가 동시일 때 **OTP 대기가 지배** |
| 넌스크롤 | 1080p 에서 스크롤바 없음 |
| 접근성 | `prefers-reduced-motion: reduce` 에서 히어로 맥동 정지 |
| 다중 엔트리 | `npm run build` 가 `wall` 엔트리를 manifest 에 낳고, 일반 페이지 번들에 `wall.css` 가 섞이지 않음 |
| 게이트 | `wall.html` 이 FG006 allowlist 밖에서 통과 |

### 4.2 비목표

| 항목 | 이유 |
| --- | --- |
| 뷰 회전 (N초마다 전환) | D4 — 단일 화면 + 상태 기반 지배 |
| WS 실시간 갱신 | 비인증 WS 표면을 늘리지 않는다. 폴링으로 충분(§3.9) |
| 상황판에서의 조작 | GET 전용, 링크·버튼 없음(§3.1) |
| 토큰 URL 인증 | D1 에서 전사 공개를 택했다 |
| **브라우저 콘솔 에러 CI 게이트** | `docs/CI.md:3` 정책상 불가(§3.6) |
| 통과율 KPI 카드 | 히어로와 중복(§3.5) |

Step 6(일간 리포트 메일)·Step 7(잔여 이관)은 각각 독립 사이클로 진행한다 — P3-1 스펙 §0 참조.

---

## 5. 검증

| 대상 | 방법 |
| --- | --- |
| `build_wall_view` 지배 요소 5경로 | pytest — 순수 함수, `summary` dict 조합 |
| OTP 대기 우선순위 | pytest — 실패 + OTP 대기 동시 입력에서 OTP 가 지배 |
| 비인증 접근 | pytest — 쿠키 없이 200 |
| 차단 스위치 | pytest — `E2E_WALL_ENABLED=false` 에서 404 |
| `my_seconds` 미사용 | pytest — 렌더 HTML 과 컨텍스트에 없음 |
| 프래그먼트 | pytest — `/wall/fragment` 가 히어로·매트릭스·스트립을 담음 |
| 다중 엔트리 | pytest — manifest 에 `wall` 엔트리 존재 / `main` CSS 에 `wall.css` 미포함 |
| 매트릭스 독립성 | pytest — `wall.html` 이 `_macros.html`·`zone_b_matrix.html` 을 임포트하지 않음 |
| reduced-motion | pytest — `wall.css` 에 `prefers-reduced-motion` 가드 + `animation: none` |
| 콘솔 에러 | **수동** Playwright 스크립트 (CI 아님, §3.6) |

P1 이 배선한 게이트 6종이 자동 적용된다. **새 CI 게이트를 추가하지 않는다.**

---

## 6. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| **비인증 노출** | 링크를 아는 사람은 사내 시스템 이름·실패 상태·절감 수치를 본다 | D1 은 트레이드오프를 제시한 뒤의 결정이다. `E2E_WALL_ENABLED`(D2)로 즉시 차단 가능하고, `docs/INSTALL.md`·`.env.example` 에 "외부 접근 가능한 배포에서는 `false`" 를 명시한다. PII 는 P2 계약이 이미 배제한다 |
| P3-1 미병합 의존 | 이 브랜치는 PR #133 위에 쌓여 있다 | #133 병합 후 `main` 으로 리베이스한다. `status_badge_view`·점등 CSS·`status-badge` 매크로가 선행 자산이다 |
| 다중 엔트리 미검증 | P1 이 만든 구조를 처음 쓴다 — 동작하지 않을 수 있다 | 그것이 드러나는 것 자체가 이 작업의 이득이다(§3.7). 실패 시 대안은 `wall.css` 를 `main` 번들에 넣는 것(무게 증가를 감수) |
| 15초 폴링 부하 | 상시 디스플레이가 계속 요청한다 | `document.hidden` 가드가 있고, 프래그먼트는 이미 P2 가 쓰는 읽기 경로다. 부하가 문제되면 주기를 늘린다 |
| 스모크 절반 해소 | 콘솔 에러 검증이 게이트가 아니다 | §3.6 에 기록. 네 번째 이월이 아니라 **범위 축소로 종결**한다 — CI 정책이 바뀌지 않는 한 이 항목은 게이트가 될 수 없다 |

---

## 7. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md`
- P2: `docs/superpowers/specs/2026-08-19-frontend-elevation-p2-design.md`
- P3-1: `docs/superpowers/specs/2026-08-20-frontend-elevation-p3-1-run-live-design.md` (§0 P3 분할)
- 비로그인 페이지 선례: `app/api/routes_trigger.py:45`
- CI 정책: `docs/CI.md`
- 프론트 게이트 SSOT: `scripts/check_frontend_gates.py`
