# 프론트엔드 고도화 P3-1 (Run 상세 라이브) — Design

**작성일:** 2026-08-20
**상태:** 초안 (사용자 리뷰 대기)
**상위 설계:** `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§4 Step 4)
**선행:** P1 기반 · P2 일간 현황 (둘 다 `main` 병합 완료)
**대상:** `app/web/templates/run.html`, `app/web/templates/suite.html`, `app/web/frontend/components/status-badge/`, `app/web/frontend/styles/app.css`, `scripts/check_frontend_gates.py`, `scripts/ci/gates.py`, `app/contexts/healing/service.py`, `app/api/routes_healing.py`

---

## 0. P3 는 하나가 아니다 — 분할

상위 설계 §4 의 Step 4~7 을 실측한 결과 **독립 서브시스템 4개**였다. 단일 스펙으로 담을 수 없으므로 각각 독립 사이클(스펙 → 계획 → 구현)로 나눈다.

| 조각 | 성격 | 실측 규모 | 순서 |
| --- | --- | --- | --- |
| **Step 4** Run 상세 라이브 | 기존 화면 개선 + 실사용 버그 수정 | `run.html` 155줄 · `suite.html` 83줄 | **이 문서 (1순위)** |
| **Step 5** 상황판 `/wall` | 신규 화면 (라우트 없음) | 신규 | 2순위 |
| **Step 6** 일간 리포트 메일 | **신규 기능** — 일간/주간 리포트가 존재하지 않음 (Run 완료 메일만 있음) | 기존 렌더러 2,689줄 | 3순위 |
| **Step 7** 잔여 화면 이관 | 기계적 대량 이관 | 13파일 8,909줄 | 4순위 |

상위 설계 §4 의 Step 6 서술("같은 KPI 를 메일 인라인으로")은 실제와 다르다. `app/notifications/` 에는 Run 완료 메일만 있고 **일간·주간 리포트 자체가 없다.** 3순위 스펙에서 정정한다.

---

## 1. 문제

### 1.1 상위 설계의 과소평가 정정

상위 설계 §1.5 는 `recovered` 플래그와 AI 실패 분석이 "Run 상세 한 줄"로 취급된다고 적었다. **틀렸다.** `run.html` 을 실제로 읽으면 둘 다 온전한 패널이다.

- `recovered`(91~95행): 재시도 횟수 + 복구 등급 체인을 `title` 로 노출
- AI 분석(96~110행): 카테고리 · 사용자 요약 · 권장 조치 · 개발자 상세(`<details>`)

아키텍처 문서만 보고 쓴 오류다. **따라서 Step 4 는 이 둘을 재작성하지 않는다.**

### 1.2 근본 문제 — 서버 최초 렌더가 컴포넌트 경계 밖에 있다

P1 이 상태 토큰을, P2 가 `StatusBadge` 를 만들었지만 **Run/Suite 상세의 서버 렌더는 그 경계를 통과하지 않는다.** 각 템플릿이 자체 상태 색 맵을 들고 있다.

| 위치 | 맵 | 키 개수 | 누락 |
| --- | --- | --- | --- |
| `app/web/templates/run.html:6` | `status_pill` | 9 | **`anomaly` · `error`** |
| `app/web/templates/suite.html:6` | `status_pill` | 7 | **`anomaly` · `error` · `blocked`** |

`ModuleStatus` 는 11개 값(`PENDING QUEUED RUNNING WAITING_INPUT PASSED ANOMALY ERROR FAILED BLOCKED SKIPPED CANCELLED`)을 가진다. 맵에는 레거시 `failed` 만 있고 현행 `anomaly`/`error` 가 없다.

### 1.3 실측한 증상 — 버그 3건

`run.html:6` 의 맵을 그대로 재현해 렌더한 결과:

| 상태 | 렌더된 색 | 렌더된 텍스트 | 기대 |
| --- | --- | --- | --- |
| `PASSED` | emerald | **"PASSED"** | 정상 |
| `ANOMALY` | **기본 회색** | **"ANOMALY"** | 이상징후 · amber |
| `ERROR` | **기본 회색** | **"ERROR"** | 점검실패 · red |
| `FAILED`(레거시=이상징후) | **red** | **"FAILED"** | 이상징후 · **amber** |
| `RUNNING` | blue | **"RUNNING"** | 실행 중 |
| `BLOCKED` | orange | **"BLOCKED"** | 차단 |

**버그 1 — 배지 텍스트가 전부 영문 enum 값이다.** `{{ run.status }}` / `{{ module.status }}` 는 `StrEnum` 을 그대로 렌더한다. `RunView` 는 `status_label` 을 이미 제공하는데 템플릿이 쓰지 않는다. `AGENTS.md` 의 "UI·로그·README 문자열 한국어" 제약 위반이 Run/Suite 상세에 상주한다.

**버그 2 — `ANOMALY`·`ERROR` 배지가 회색이다.** 점검 도구에서 가장 중요한 두 상태가 중립색으로 표시된다.

**버그 3 — 레거시 `FAILED` 가 빨강이다.** `status_labels.py` 는 `FAILED` 를 이상징후(amber)로 분류하지만 템플릿은 red 를 준다.

**노출 조건:** `.node-card.status-*` CSS(`app/web/frontend/styles/app.css:383~390`)는 `anomaly`·`error` 를 **정상적으로 덮는다.** 그리고 `app/web/static/app.js:1913-1915` 의 런타임 갱신은 P2 이후 `window.__statusBadge`(SSOT 파생)를 쓴다. 따라서

- **진행 중인 Run**: 첫 WS 업데이트가 오면 배지가 고쳐진다 (초기 프레임만 잘못)
- **완료된 Run**: WS 업데이트가 오지 않으므로 **끝까지 회색·영문**

즉 **"왜 실패했는지 보려고 완료된 Run 을 여는" 가장 흔한 동작에서 깨진다.** 카드 왼쪽 테두리는 빨간데 배지만 회색이라 오히려 더 혼란스럽다.

### 1.4 왜 CI 가 못 잡았나 — 게이트 틈

`scripts/check_frontend_gates.py:149` `check_fg003_status_source` 는 `app/web/frontend/**/*.ts` 만 스캔한다. **`app/web/templates/**/*.html` 은 어떤 FG 규칙도 상태 표현을 검사하지 않는다.**

템플릿에 상태 색 리터럴이 남아 있는 파일은 현재 7개다: `run.html` · `suite.html` · `execute.html` · `self_healing.html` · `admin/base.html` · `admin/users.html` · `base.html`.

### 1.5 부차 문제 — 치유 사실이 Run 화면에 없다

`recovered` 배지는 *"재시도 N회 후 통과"* 만 알린다. **무엇이 깨져서 무엇으로 고쳐졌는지는 Run 상세에 전혀 없다** — `/self-healing` 으로 따로 가야 보인다.

`HealingEvent` 는 `run_id` 를 가지지만 `app/contexts/healing/service.py:195` `list_events` 는 `system_code` 필터만 지원한다.

### 1.6 부차 문제 — 상태 전이가 눈에 남지 않는다

WS 업데이트가 오면 배지가 즉시 교체된다. 전이 표현이 없어 "지금 무엇이 돌고 있는가"의 감각이 없다. 상위 설계 §3.3 이 *"`waiting_input` 은 유일하게 깜빡이는 상태"* 로 정했으나 아직 실현되지 않았다.

---

## 2. 목표 / 비목표

### 2.1 목표

1. Run/Suite 상세의 **서버 최초 렌더를 `StatusBadge` 컴포넌트 경계 안으로** 넣어 버그 3건을 근절한다.
2. 템플릿의 상태 표현 하드코딩을 **게이트로 차단**해 재발을 막는다.
3. 파이썬 SSOT · TS 생성물 · 서버 렌더의 **3자 일치를 테스트가 강제**한다.
4. 상태 전이를 **보이게** 한다 (점등 · `waiting_input` 깜빡임).
5. 치유 사실을 **Run 화면에서** 보이게 한다.

### 2.2 비목표

| 항목 | 자르는 이유 |
| --- | --- |
| **로그 심각도 색상** | 로그는 `app/runner/step_logging.py:37` `log(message: str)` 순수 문자열이고 severity 필드가 없다. 도입하려면 `app/automation/` 의 호출부 **459곳**을 손대야 하고, `AGENTS.md` 가 automation 변경 시 짝 시나리오 문서 동시 갱신을 요구한다. Step 4 의 가치 대비 과도하다 |
| **`recovered` · AI 분석 패널 재작성** | 이미 온전하다(§1.1). 배지 클래스를 토큰 기반으로 정리하는 선에서 끝낸다 |
| **Run 상세 JS 를 `frontend/` 로 이관** | `app.js` 3,255줄이 여러 화면 공용이라 Run 부분만 분리하기 어렵다. Step 7 에서 통째로 |
| **자동 화면 스모크 테스트** | P1·P2 에서 두 번 미룬 항목. **세 번째 연기다.** Step 5(`/wall`)가 인증 불필요 읽기 경로를 만들 때 반드시 붙인다 |
| 다크모드 · 테마 | 라이트 단일 팔레트 확정 (상위 설계 §2.2) |

### 2.3 성공 기준

| 기준 | 측정 |
| --- | --- |
| 배지 텍스트 한국어 | 렌더된 Run/Suite 상세 HTML 에 배지 텍스트로서의 `PASSED`·`ANOMALY`·`ERROR` 등 영문 enum 값 0건 |
| 상태 색 정확성 | 9개 톤 전부 `data-tone` 이 `STATUS_TONE_MAP` 과 일치 |
| 하드코딩 제거 | `run.html`·`suite.html` 에 `status_pill` 0건 |
| 재발 차단 | FG-006 이 두 템플릿을 allowlist 밖에서 검사 |
| 3자 일치 | 파이썬 SSOT ↔ `status.generated.ts` ↔ 서버 렌더 일치 테스트 통과 |
| 접근성 | `prefers-reduced-motion: reduce` 에서 점등·깜빡임 정지 |
| 치유 가시성 | 치유가 발생한 Run 의 모듈 카드에 복구 건수·셀렉터 표시 |

---

## 3. 설계

### 3.1 `status_pill` 제거 → `status_badge` 매크로

P2 가 만든 `app/web/frontend/components/status-badge/macro.jinja` 를 쓴다. 시그니처는 이미 필요한 것을 받는다:

```jinja
{% macro status_badge(status, label, size="md") %}
```

교체 지점:

| 위치 | 현재 | 이후 |
| --- | --- | --- |
| `run.html:6` | `status_pill` 정의 | **삭제** |
| `run.html:22` | Run 상태 배지 | `status_badge(run.status_tone, run.status_label, size="md")` |
| `run.html:85` | 모듈 상태 배지 | `status_badge(module.status_tone, module.status_label, size="sm")` |
| `suite.html:6` | `status_pill` 정의 | **삭제** |
| `suite.html:20` | Suite 상태 배지 | `status_badge(...)` |
| `suite.html:67` | Step 상태 배지 | `status_badge(...)` |

**필요한 읽기 모델 필드:** 뷰가 `status_tone` 과 `status_label` 을 제공해야 한다. `RunView` 는 `status_label` 을 이미 만든다(`view.py:93`). `status_tone`(= `*_badge_tone()` 결과)을 뷰에 추가한다 — 템플릿이 톤 계산을 하지 않는 것이 요점이다. 모듈/스텝 뷰도 동일하게 추가한다.

`.node-card.status-{{ module.status|lower }}` 클래스는 **그대로 둔다.** `app.css:383~390` 이 이미 9톤을 올바르게 덮고 있어 배지만 고치면 테두리와 색이 일치한다.

### 3.2 FG-006 — 템플릿의 상태 표현 하드코딩 금지

`FG-003` 을 확장하지 않고 **별 규칙**으로 신설한다. 스캔 대상(`.html`)과 예외 목록이 다르고, `FG-005` 와 같은 **축소형 allowlist** 를 갖기 때문이다.

| 규칙 | 내용 |
| --- | --- |
| **FG-006** | `app/web/templates/**/*.html` 에서 **상태→표현 매핑의 중복** 금지 |

**어휘가 아니라 구조를 탐지한다.** 초안은 상태 색 쌍(`bg-red-100 text-red-700`)과 한국어 라벨 리터럴을 탐지했으나, 구현 후 실측에서 **위반 70건 중 약 50건이 오탐**이었다 — `<body>` 레이아웃 클래스, 네비 활성 표시 색, "취소" 버튼 문구, 히어로 산문(P2 가 설계한 `점검실패 N건 — 우선 확인이 필요합니다`), 페이지 이름(`이상징후 인박스`), 부분 문자열 충돌(`무인 실행 중 …`). 그 결과 allowlist 가 16개로 불어 게이트가 `run.html`·`suite.html` 2개만 지키는 규칙이 되고, 영구히 못 지울 항목이 섞여 아래 "비면 완성" 전제가 깨졌다.

실제 병은 어휘가 아니라 **상태→표현 매핑의 중복**이다. 두 규칙만 남긴다.

| 규칙 | 탐지 대상 | 잡는 실례 |
| --- | --- | --- |
| **MAP** | 한 줄에 상태 키(`passed`·`error`·…)가 콜론과 함께 **2개 이상** | `run.html:6` `status_pill`, `_macros.html` 글리프 맵, `mobile_trigger.html` 인라인 JS 맵 |
| **PAIR** | 같은 줄에 enum 값(`PASSED`…) + 도메인 전용 라벨(`이상징후`·`점검실패`·`입력 대기`·`정상`) | `<option value="PASSED">정상</option>` |

`취소`·`제외`·`차단`·`실행 중` 은 일반 한국어로 흔해 라벨 목록에서 제외한다. enum 과 같은 줄이라는 조건이 문맥을 대신 준다.

**검증된 결과:** 두 규칙은 P3-1 이 고친 `run.html:6`·`suite.html:6` 의 `status_pill` 을 **둘 다 잡고**, 위 오탐 6종을 모두 통과시킨다. 실측 **16건 / 4파일, 오탐 0**.

**allowlist 운용:** `FG006_ALLOWLIST` 는 상태→표현 매핑을 아직 중복으로 들고 있는 4개다 — `dashboard/partials/_macros.html` · `mobile_trigger.html` · `admin/runs.html` · `schedules.html`. `run.html`·`suite.html` 은 P3-1 이 고쳤으므로 처음부터 없다. Step 7 이 이관할 때마다 한 줄씩 지운다. **오탐이 섞이지 않으므로 "allowlist 가 비면 FG-006 이 완성된다" 는 전제가 실제로 성립한다** — `FG-005` 와 동일한 점진 완성 패턴이다.

**놓치는 것(의도적):** 색 쌍 규칙이 잡던 `execute.html:6` 의 `tone_pill` 은 키가 색명(`'red'`·`'orange'`)이라 MAP 규칙에 걸리지 않는다. `analyzer_status.color` 를 받는 색→클래스 맵이라 `status_pill` 과 같은 병은 아니며, Step 7 이 `execute.html` 을 이관할 때 정리된다.

`scripts/ci/gates.py` 의 `frontend_gates` 게이트가 이미 Tier 0 에 있으므로 **새 게이트 등록은 필요 없다.**

### 3.3 3자 일치 테스트

이 문제의 본질은 "같은 상태를 두 경로가 다르게 그린다"이다. 세 정의가 일치하는지 테스트가 검사한다.

| 축 | 출처 |
| --- | --- |
| 파이썬 SSOT | `app/core/status_labels.py` — `STATUS_TONES` · `*_badge_tone()` · `*_STATUS_LABELS` |
| TS 생성물 | `app/web/frontend/lib/status.generated.ts` — `STATUS_TONE_MAP` · 라벨 맵 |
| 서버 렌더 | `status_badge` 매크로가 낳은 `data-tone` + 텍스트 |

검사 내용:

1. 모든 `ModuleStatus`/`RunStatus`/`SuiteStatus` 값에 대해 서버 렌더 `data-tone` == 파이썬 `*_badge_tone()`
2. 서버 렌더 배지 텍스트 == 파이썬 `*_status_label()`
3. `status.generated.ts` 를 파싱한 `STATUS_TONE_MAP` == 파이썬 톤 매핑
4. 렌더된 Run/Suite 상세 HTML 에 배지 텍스트로서의 영문 enum 값 0건

3번이 핵심이다 — **어느 한쪽만 바뀌면 CI 가 막는다.**

### 3.4 점등 — 상태 전이를 보이게

`data-tone` 이 이미 배지에 붙으므로 **순수 CSS 로 처리**한다. JS 변경을 최소화한다.

| 상태 | 표현 |
| --- | --- |
| 전이 발생 | `data-tone` 변경 시 색 transition + **1회 pulse** |
| `running` | 은은한 지속 pulse — 지금 무엇이 진행 중인지 한눈에 |
| `waiting_input` | **유일하게 눈에 띄게 깜빡임** — 사람의 OTP 입력을 기다리는 상태 (상위 설계 §3.3 결정의 실현) |
| 그 외 | 정적 |

**접근성 (필수):** `@media (prefers-reduced-motion: reduce)` 에서 pulse·깜빡임을 모두 정지한다. P2 에서 내가 이 가드를 빠뜨려 접근성 회귀를 만들었으므로(원본 `dashboard.js` 에 `if (REDUCED)` 가 있었다), 구현 계획의 스텝과 검증 항목에 못 박는다.

애니메이션은 `status-badge/styles.css` 와 `.node-card` 규칙에 둔다. 토큰만 참조한다(FG-002).

### 3.5 치유 이력 인라인

`HealingService.list_events` 에 `run_id` 필터를 추가한다(가산적 변경, 기존 호출자 무영향).

```python
async def list_events(
    self, *, allowed_system_codes=None, system_code=None,
    run_id: str | None = None,          # 신규
    limit=_EVENT_LIST_LIMIT,
) -> dict[str, Any]
```

Run 상세가 이 Run 의 치유 이벤트를 모듈별로 묶어 카드에 한 줄 추가한다:

```
🔧 셀렉터 2건 자동 복구 · #login-btn → [data-testid=login] · 상세 →
```

- "상세" 는 `/self-healing#patches`(P2 가 만든 앵커)로 이동
- 치유 이벤트가 없는 모듈에는 아무것도 표시하지 않는다
- `HealingAction` 3분류를 구분한다 — `AUTO_HEALED` 만 "자동 복구", `SUGGESTED` 는 "제안됨", `NO_CANDIDATE` 는 표시하지 않음

**왜 가치 있나:** 경영진 데모에서 *"AI 가 스스로 고쳤다"* 를 Run 화면에서 바로 보여줄 수 있는 유일한 지점이다. 지금은 메뉴 7번째로 들어가야 한다.

### 3.6 백엔드 변경 요약

| 작업 | 성격 |
| --- | --- |
| `RunView`/모듈 뷰/`SuiteView`/스텝 뷰에 `status_tone` 필드 추가 | 기존 `*_badge_tone()` 노출 |
| `HealingService.list_events` 에 `run_id` 필터 | 가산적 |
| Run 상세 라우트가 치유 이벤트를 함께 조회 | 조립 |

**신규 도메인 로직 0건.** 전부 노출과 조립이다.

---

## 4. 검증

| 대상 | 방법 |
| --- | --- |
| 3자 일치 (§3.3) | pytest — 전 상태값 순회 |
| 배지 텍스트 한국어 | pytest — **배지 엘리먼트의 텍스트 노드**에 영문 enum 값 0건. `class="… status-error"` 같은 클래스 값은 정당하므로 검사 대상이 아니다 (HTML 파싱 후 `.status-badge` 텍스트만 확인) |
| `status_pill` 제거 | pytest 또는 grep 가드 — 두 템플릿에 0건 |
| FG-006 | `scripts/check_frontend_gates.py` 단위 테스트 + allowlist 축소 검증 |
| `run_id` 필터 | pytest — 다른 Run 의 이벤트가 섞이지 않음 |
| 치유 표시 | pytest — `AUTO_HEALED` 만 "자동 복구"로 표시, `NO_CANDIDATE` 는 미표시 |
| **reduced-motion** | Vitest 또는 CSS 검사 — `prefers-reduced-motion: reduce` 블록에 pulse 정지 규칙 존재 |
| 기존 화면 무회귀 | 기존 `tests/test_run_*`·`tests/test_suite_*` 통과 |

P1 이 배선한 게이트 6종이 자동 적용된다. **새 게이트를 추가하지 않는다** (FG-006 은 기존 `frontend_gates` 안의 규칙 추가).

---

## 5. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| 뷰에 `status_tone` 추가 | `RunView`/`SuiteView` 계약 변경이라 WS payload 도 넓어진다 | 가산적 필드이므로 기존 소비자 무영향. `app.js` 는 여전히 `window.__statusBadge` 로 자체 계산하므로 충돌 없음 |
| `app.js` 와 서버 렌더의 이중 경로 | Step 4 는 서버 렌더만 고친다 — 런타임 갱신은 여전히 `app.js` | 둘 다 SSOT 파생이므로 결과가 같다. §3.3 테스트가 이를 강제. 코드 통합은 Step 7 |
| FG-006 allowlist 5개 잔존 | Step 7 까지 5개 템플릿이 오염 상태로 남는다 | 정직하게 allowlist 에 기록. 축소가 진행 지표가 된다 |
| 점등이 과할 위험 | 깜빡임이 산만해질 수 있다 | `waiting_input` 만 눈에 띄게, `running` 은 은은하게. reduced-motion 존중 |
| 자동 스모크 3번째 연기 | P1·P2·P3-1 모두 미룸 | Step 5 에서 반드시 처리. 그때 인증 불필요 경로가 생긴다 |

---

## 6. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md`
- P1: 독립 스펙 없음 — 상위 설계 §3.1~§3.7 이 그 역할을 했다. 계획: `docs/superpowers/plans/2026-08-19-frontend-elevation-p1.md`
- P2: `docs/superpowers/specs/2026-08-19-frontend-elevation-p2-design.md` · `plans/2026-08-19-frontend-elevation-p2.md`
- 프론트 게이트 SSOT: `scripts/check_frontend_gates.py`, `docs/CI.md`
- 상태 SSOT: `app/core/status_labels.py`
