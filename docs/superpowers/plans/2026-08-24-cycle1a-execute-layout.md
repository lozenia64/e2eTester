# Cycle 1a: 점검 실행 레이아웃 승격 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 점검 실행 화면을 `<details>` 아코디언 6개에서 넌스크롤 마스터-디테일 2열로 바꾸고, 아코디언 안에 숨어 있던 모듈 의존성 그래프를 화면의 지배 요소로 꺼낸다.

**Architecture:** `execute.html` 은 지금도 6개 시스템 폼을 **전부 서버 렌더해 DOM 에 넣는다** — `<details>` 가 접고 있을 뿐이다. 따라서 이 작업은 렌더 경로 변경이 아니라 **표시 규칙 변경**이다. `<details>/<summary>` 를 좌측 선택 목록 + 우측 패널로 바꾸고 Alpine `x-show` 로 선택된 폼 하나만 보인다. 폼 마크업 · `data-role` 속성 · `app.js` 의 기존 바인딩은 전부 그대로 산다. 대시보드가 이미 쓰는 `body:has(.dash)` 넌스크롤 셸 패턴을 `.exec` 에 그대로 적용한다.

**Tech Stack:** Jinja2, Alpine.js 3(이미 전역), Tailwind CSS v4, CSS Grid + 컨테이너 쿼리, Vite, pytest + Playwright

**Spec:** `docs/superpowers/specs/2026-08-24-execute-promotion-design.md` (§1.3 숨겨진 그래프 · §1.4 아코디언 문제 · §4.3 레이아웃 · §4.4 왜 싼가 · §4.5 데이터 경로 · D6 · D8)

**선행:** `docs/superpowers/plans/2026-08-24-cycle0-palette-unification.md` 완료(상태 색이 SSOT 로 수렴한 상태여야 좌측 배지 색이 대시보드와 일치한다)

**후속:** Cycle 1b — `app.js` 약 1,400줄을 `entries/execute.ts` 로 이관. 이 계획은 **레거시 `app.js` 를 그대로 둔 채** 레이아웃만 승격하므로 단독 배포 가능하다.

## Global Constraints

- **색 SSOT 는 `app/core/status_colors.py` 의 `PALETTE`.** 새 hex 를 적지 않는다. Cycle 0 이 FG-002 를 `templates/` 까지 확장했으므로 템플릿의 새 hex 는 **게이트가 막는다.**
- **상태 라벨·톤은 서버 주입만**(FG-003 · FG-006). 템플릿·TS 가 상태 키 맵이나 한국어 상태 라벨을 들지 않는다. 배지는 `app/web/frontend/components/status-badge` 를 쓴다.
- **`/static/` 직접 참조 금지**(FG-005). 자산은 `_assets.html` 매크로 경유.
- **엔트리·컴포넌트 파일 400줄 상한**(FG-004).
- **넌스크롤 예산:** `body` 세로 스크롤 0. 내부 스크롤을 갖는 영역은 **우측 조건 열 하나뿐.**
- **동작 불변:** `SPEC-UI-002` 의 AC-001(Suite preset 검증) · AC-002(depends_on)은 **서버측 규칙**이며 이 계획은 API 를 건드리지 않는다. 회귀 확인은 `tests/test_presets_http.py` · `tests/test_suite_aggregate.py` · `tests/test_suite_decider.py` 로 한다. 폼 `name` 속성과 `data-role` 값은 하나도 바꾸지 않는다 — `app.js` 가 그걸로 찾는다.
- **좌측 항목 수는 1~7개로 변한다**(`current_user.allowed_system_codes` 필터 + SUITE 1개). 1개일 때도 레이아웃이 성립해야 한다.
- **UI 문자열은 한국어**(AGENTS.md).
- **PR 전 필수:** `python3 scripts/ci/run_all_gates.py --profile full`

## File Structure

| 파일 | 책임 | 상태 |
| --- | --- | --- |
| `app/web/frontend/styles/execute.css` | 점검 실행 셸 · 2열 그리드 · 좌측 목록 · 우측 패널 | **신규** |
| `app/web/frontend/styles/base.css` | 전역 임포트 체인 | 수정(1줄) |
| `app/web/templates/execute.html` | 화면 마크업 | 수정(대폭 — 아코디언 → 2열) |
| `app/web/templates/execute/_system_list.html` | 좌측 선택 목록 | **신규**(포함 파일) |
| `app/web/static/app.css` → `execute.css` | 모듈 그래프 스타일 이사(`app.css:427~570`) | 이동 |
| `tests/test_execute_layout.py` | 템플릿 렌더 계약 | **신규** |
| `tests/test_execute_viewport.py` | 넌스크롤 · 스크롤 소유권 Playwright | **신규** |
| `docs/specs/dashboard/02-execute-page.md` | AC Spec | 수정(Task 6) |

---

### Task 1: 넌스크롤 셸과 2열 골격

아코디언을 없애고 좌우 2열을 세운다. **이 태스크가 끝나면 화면이 이미 바뀌어 있다.**

**Files:**
- Create: `app/web/frontend/styles/execute.css`
- Modify: `app/web/frontend/styles/base.css`
- Modify: `app/web/templates/execute.html`
- Test: `tests/test_execute_layout.py`

**Interfaces:**
- Consumes: `execute.html` 의 기존 컨텍스트 — `systems`(리스트), `systems_payload`(dict), `analyzer_status`, `email_status`, `current_user`. 라우트(`app/api/routes_dashboard.py:56`)는 **바꾸지 않는다.**
- Produces: `.exec` 루트 요소, `x-data="{ selected: '<첫 항목 키>' }"` Alpine 스코프, 좌측 항목의 `data-exec-target="{key}"`, 우측 패널의 `data-exec-panel="{key}"`. `key` 는 `suite` 또는 `system.system_code`. Task 2·3 이 이 계약 위에 얹힌다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_execute_layout.py` 를 만든다. 기존 템플릿 렌더 테스트의 방식을 따른다 — `TestClient` 로 `/runs/execute` 를 받아 HTML 을 문자열로 단언한다. 인증 의존성 오버라이드 방식은 `tests/test_dashboard_fragments_http.py` 를 참고한다.

```python
"""점검 실행 레이아웃 계약 — 아코디언이 아니라 마스터-디테일인지.

`app.js` 는 폼을 `data-role` 로 찾는다. 레이아웃을 바꾸면서 그 속성을 잃으면
화면은 멀쩡해 보이는데 실행 버튼이 아무 일도 하지 않는다 — 그것을 막는다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.api.dependencies import get_run_service
from app.api.routes_dashboard import router as dashboard_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from tests.test_dashboard_fragments_http import FakeRunService


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    user = User(
        user_id="u1",
        email="operator@example.com",
        name="점검자",
        role="user",
        allowed_system_codes=["hom", "mhm", "fp", "hrp", "hwtc", "chbot"],
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_run_service] = lambda: FakeRunService()
    return TestClient(app)


def _html(client: TestClient) -> str:
    response = client.get("/runs/execute")
    assert response.status_code == 200
    return response.text


def test_root_carries_the_exec_shell_class(client) -> None:
    """넌스크롤 셸은 body:has(.exec) 로 걸린다 — 클래스가 없으면 셸이 통째로 안 붙는다."""
    assert 'class="exec' in _html(client)


def test_accordion_is_gone(client) -> None:
    """<details> 가 남아 있으면 '펼치기 전에는 안 보이는' 문제가 그대로다."""
    html = _html(client)
    assert "<details" not in html
    assert "system-card--suite" not in html


def test_every_system_has_a_left_target_and_a_right_panel(client) -> None:
    html = _html(client)
    for key in ("suite", "hom", "mhm", "fp", "hrp", "hwtc", "chbot"):
        assert f'data-exec-target="{key}"' in html, key
        assert f'data-exec-panel="{key}"' in html, key


def test_suite_is_selected_first(client) -> None:
    """전체 순차 점검이 기본 선택 — 데모에서 가장 먼저 보여줄 화면이다."""
    assert "selected: 'suite'" in _html(client)


def test_form_contract_survives(client) -> None:
    """app.js 가 찾는 훅이 그대로여야 한다(Cycle 1b 이전까지 레거시가 계속 붙는다)."""
    html = _html(client)
    for hook in (
        'id="suite-form"',
        'id="suite-start-button"',
        'id="suite-section"',
        'class="system-form',
        'data-role="system-definition"',
        'data-role="preset-panel"',
        'data-role="module-selector"',
        'data-role="module-graph-canvas"',
        'data-role="module-graph-edges"',
        'data-role="module-graph-grid"',
        'data-role="suite-system-checkbox"',
        'data-role="suite-preset-list"',
    ):
        assert hook in html, hook


def test_single_system_user_still_gets_a_layout(client) -> None:
    """allowed_system_codes 가 1개인 사용자에게도 좌우 2열이 성립해야 한다."""
    app = client.app
    solo = User(
        user_id="u2",
        email="solo@example.com",
        name="단일",
        role="user",
        allowed_system_codes=["hom"],
    )
    app.dependency_overrides[get_current_user] = lambda: solo
    html = client.get("/runs/execute").text
    assert 'data-exec-target="suite"' in html
    assert 'data-exec-target="hom"' in html
    assert 'data-exec-target="mhm"' not in html
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_execute_layout.py -v`
Expected: FAIL — `test_root_carries_the_exec_shell_class` · `test_accordion_is_gone` · `test_every_system_has_a_left_target_and_a_right_panel` · `test_suite_is_selected_first` 4건. `test_form_contract_survives` 는 PASS(현행 마크업이 이미 만족).

`FakeRunService` 시그니처가 맞지 않으면 `tests/test_dashboard_fragments_http.py` 의 정의를 보고 `list_systems()` 가 필요한 형태를 돌려주도록 픽스처를 맞춘다.

- [ ] **Step 3: 셸 CSS 를 만든다**

`app/web/frontend/styles/execute.css`:

```css
/* 점검 실행 — 마스터-디테일 관제탑(설계 §4.3).
   색은 전부 토큰(FG-002). 대시보드의 넌스크롤 셸 패턴을 그대로 따른다. */

/* ── Viewport-fit shell ── dashboard.css 의 body:has(.dash) 와 같은 구조다.
   두 화면이 같은 규칙을 필요로 하므로, 세 번째 화면이 생기면 공통 셸로 뽑는다. */
body:has(.exec) {
  overflow: hidden;
  height: 100dvh;
  max-height: 100dvh;
  min-height: 0;
}

body:has(.exec) main,
body:has(.exec) main > div {
  max-width: none;
  padding-top: 0;
  padding-right: 0;
  padding-bottom: 0;
  height: 100dvh;
  overflow: hidden;
  box-sizing: border-box;
}

@media (min-width: 768px) {
  body:has(.exec) main { padding-left: 16rem; width: 100%; }
  body:has(.exec) main > div { padding-left: 0; width: 100%; max-width: none; }
}

@media (max-width: 767px) {
  body:has(.exec) { display: flex; flex-direction: column; }
  body:has(.exec) > header { flex-shrink: 0; }
  body:has(.exec) main { flex: 1 1 auto; min-height: 0; height: auto; overflow: hidden; }
  body:has(.exec) main > div { height: 100%; overflow: hidden; }
  body:has(.exec) main,
  body:has(.exec) main > div { padding-left: 0; width: 100%; }
}

/* ── 2열 그리드 ── */
.exec {
  display: grid;
  grid-template-columns: minmax(240px, 300px) 1fr;
  gap: 1.5rem;
  height: 100%;
  padding: 1.5rem;
  overflow: hidden;
  container-type: size;
  container-name: exec-shell;
}

/* < 1024px: 1열. 좌측 목록이 가로 스크롤 칩 행이 된다. */
@media (max-width: 1023px) {
  .exec {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    gap: 1rem;
    padding: 1rem;
  }
}

/* ── ① 좌측 — 무엇을 점검할까 ── */
.exec-master {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 0;
  overflow: hidden; /* 넌스크롤 예산: 이 열은 스크롤하지 않는다 */
}

.exec-master__title {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--pl-text-subtle);
}

.exec-master__list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-height: 0;
}

@media (max-width: 1023px) {
  .exec-master__list {
    flex-direction: row;
    overflow-x: auto;
    padding-bottom: 0.25rem;
  }
}

.exec-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 0.75rem;
  background: transparent;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--pl-text-muted);
  text-align: left;
  cursor: pointer;
  transition: background 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}

.exec-item:hover { background: var(--pl-bg); }

.exec-item[aria-selected="true"] {
  border-color: var(--pl-border);
  background: var(--pl-surface);
  color: var(--pl-text);
  box-shadow: var(--pl-shadow-sm);
}

.exec-item:focus-visible {
  outline: 2px solid var(--pl-accent);
  outline-offset: 2px;
}

.exec-item--suite { color: var(--c-violet-700); }

.exec-item__name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 환경 진단 3종(AI 분석·종료 메일·등록 시스템). 실행과 무관한 상태라
   좌측 열 바닥에 압축해 둔다 — 자리는 지키되 시선은 가져가지 않는다. */
.exec-env {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--pl-border);
}

.exec-env__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.6875rem;
  color: var(--pl-text-subtle);
}

@media (max-width: 1023px) { .exec-env { display: none; } }

/* ── ② 우측 — 어떻게 점검할까 ── */
.exec-detail {
  min-height: 0;
  overflow-y: auto; /* 넌스크롤 예산: 내부 스크롤은 여기 하나뿐 */
  overscroll-behavior: contain;
  border: 1px solid var(--pl-border);
  border-radius: 1rem;
  background: var(--pl-surface);
  box-shadow: var(--pl-shadow-sm);
}

.exec-panel { padding: 1.25rem; }
.exec-panel[hidden] { display: none; }
```

- [ ] **Step 4: base.css 에 임포트를 넣는다**

`app/web/frontend/styles/base.css` 의 `@import "./dashboard.css";` 다음 줄:

```css
@import "./execute.css";
```

- [ ] **Step 5: 좌측 목록 포함 파일을 만든다**

`app/web/templates/execute/_system_list.html`:

```jinja
{# 좌측 선택 목록. 오늘 상태 배지는 Cycle 1a Task 3 이 채운다(자리만 둔다). #}
<aside class="exec-master">
  <p class="exec-master__title">무엇을 점검할까</p>
  <div class="exec-master__list" role="tablist" aria-label="점검 대상">
    <button
      type="button"
      role="tab"
      class="exec-item exec-item--suite"
      data-exec-target="suite"
      :aria-selected="selected === 'suite'"
      @click="selected = 'suite'"
    >
      <span class="exec-item__name">전체 순차 점검</span>
      <span class="exec-item__meta">{{ systems|length }}개</span>
    </button>
    {% for system in systems %}
    <button
      type="button"
      role="tab"
      class="exec-item"
      data-exec-target="{{ system.system_code }}"
      :aria-selected="selected === '{{ system.system_code }}'"
      @click="selected = '{{ system.system_code }}'"
    >
      <span class="exec-item__name">{{ system.name }}</span>
      <span class="exec-item__badge" data-exec-badge="{{ system.system_code }}"></span>
    </button>
    {% endfor %}
  </div>

  <div class="exec-env">
    <div class="exec-env__row">
      <span>등록 시스템</span><span>{{ systems|length }}개</span>
    </div>
    <div class="exec-env__row">
      <span>AI 분석</span><span>{{ analyzer_status.title }}</span>
    </div>
    <div class="exec-env__row">
      <span>종료 메일</span><span>{{ email_status.title }}</span>
    </div>
  </div>
</aside>
```

- [ ] **Step 6: execute.html 을 2열로 바꾼다**

`{% block content %}` 의 구조를 바꾼다. **폼 내부는 손대지 않는다** — `<details>`/`<summary>` 껍데기만 벗기고 `<form>` 이하를 그대로 패널 안으로 옮긴다.

바깥 골격:

```jinja
{% block content %}
{% set system_visual = {
    'hom': {'accent': 'indigo', 'channel': 'pc'},
    'mhm': {'accent': 'sky', 'channel': 'mobile'},
    'fp': {'accent': 'amber', 'channel': 'pc'},
    'hrp': {'accent': 'rose', 'channel': 'pc'},
    'hwtc': {'accent': 'emerald', 'channel': 'pc'},
    'chbot': {'accent': 'cyan', 'channel': 'mobile'},
} %}
<div class="exec" x-data="{ selected: 'suite' }">
  {% include "execute/_system_list.html" %}

  <div class="exec-detail" id="suite-section">
    <section class="exec-panel" data-exec-panel="suite" x-show="selected === 'suite'" x-cloak>
      <form id="suite-form" class="grid gap-x-4 gap-y-5 sm:grid-cols-2">
        {# ... 기존 execute.html:93~253 의 SUITE 폼 내용을 그대로 옮긴다 ... #}
      </form>
    </section>

    {% for system in systems %}
    {% set visual = system_visual.get(system.system_code, {'accent': 'indigo', 'channel': 'pc'}) %}
    <section
      class="exec-panel exec-panel--accent-{{ visual.accent }}"
      data-exec-panel="{{ system.system_code }}"
      x-show="selected === '{{ system.system_code }}'"
      x-cloak
    >
      <form class="system-form grid gap-x-4 gap-y-5 sm:grid-cols-2" data-system-code="{{ system.system_code }}">
        {# ... 기존 execute.html:286~ 의 시스템 폼 내용을 그대로 옮긴다 ... #}
      </form>
    </section>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

주의할 점 셋:

1. **`id="suite-section"` 을 유지한다.** `app.js:531` 의 `bindSystemCardExpand` 가 이 id 를 찾는다. `details.system-card` 를 못 찾으면 조용히 아무 일도 안 하므로 안전하다.
2. **`{% set tone_pill = ... %}`(`execute.html:6`)을 지운다.** 색명 키 맵이며 P3-4 가 P4 로 넘긴 부채다. 유일한 사용처가 상태 카드 3종인데 Step 5 에서 텍스트로 대체했다.
3. **페이지 헤더(`execute.html:16~21`)를 지운다.** 넌스크롤 2열에서 헤더는 높이만 먹고, 좌측 열의 "무엇을 점검할까"가 그 역할을 한다. 사이드바가 이미 현재 위치를 표시한다.

- [ ] **Step 7: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_execute_layout.py -v`
Expected: PASS (6 passed)

- [ ] **Step 8: 빌드하고 눈으로 확인한다**

Run: `npm run build`

앱을 띄워 `/runs/execute` 를 연다. 확인 항목:
- 좌우 2열이고 세로 스크롤바가 없다
- 좌측 항목을 누르면 우측 패널이 바뀐다
- 전체 순차 점검이 처음부터 선택돼 있다
- 실행 버튼이 스크롤 없이 보인다(모듈 많은 시스템은 우측 열이 내부 스크롤)

- [ ] **Step 9: 커밋**

```bash
git add app/web/frontend/styles/execute.css app/web/frontend/styles/base.css app/web/templates/execute.html app/web/templates/execute/_system_list.html tests/test_execute_layout.py
git commit -m "feat(execute): 아코디언 6개를 넌스크롤 마스터-디테일 2열로"
```

---

### Task 2: 모듈 그래프를 지배 요소로

숨어 있던 DAG 렌더러를 우측 패널 상단의 주인공 자리로 꺼낸다. **로직은 건드리지 않는다** — 스타일과 자리만 바꾼다.

**Files:**
- Modify: `app/web/frontend/styles/app.css:427-570` (잘라내기)
- Modify: `app/web/frontend/styles/execute.css` (붙여넣기 + 크기 재조정)
- Modify: `app/web/templates/execute.html` (모듈 셀렉터 절을 폼 상단으로)
- Test: `tests/test_execute_layout.py` (추가)

**Interfaces:**
- Consumes: Task 1 의 `.exec-panel`. `app.js:332` 의 `fitModuleGraphToViewport` 가 `[data-role="module-graph-canvas"]` 의 실측 크기로 노드 크기를 정하므로, 캔버스에 더 큰 영역을 주면 그래프가 자동으로 커진다
- Produces: `.exec-graph` 래퍼. Cycle 1b 가 이 셀렉터를 그대로 이어받는다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_execute_layout.py` 에 추가한다.

```python
def test_module_graph_is_the_first_thing_in_the_panel(client) -> None:
    """그래프가 인증 폼 아래 묻히면 '지배 요소' 가 아니다."""
    html = _html(client)
    panel_start = html.index('data-exec-panel="hom"')
    graph_at = html.index('data-role="module-graph-canvas"', panel_start)
    auth_at = html.index('name="auth_method"', panel_start)
    assert graph_at < auth_at, "모듈 그래프가 인증 필드보다 뒤에 있다"


def test_graph_has_its_own_wrapper(client) -> None:
    assert "exec-graph" in _html(client)
```

`name="auth_method"` 가 없는 시스템이면 `system.run_form` 의 첫 필드 `name` 으로 바꾼다 — `docs/specs/systems/hom.md` 에서 확인한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_execute_layout.py -k graph -v`
Expected: FAIL — `exec-graph` 없음, 그래프가 폼 필드 뒤

- [ ] **Step 3: 그래프 스타일을 이사시킨다**

`app/web/frontend/styles/app.css` 의 `427~570` 구간(`.module-graph-viewport` 부터 `.module-graph-node.is-locked` 계열까지)을 **잘라내어** `execute.css` 끝으로 옮긴다. 선언은 한 줄도 바꾸지 않는다 — 이사만 한다.

옮긴 뒤 `execute.css` 에 크기 규칙을 덧붙인다:

```css
/* ── 지배 요소: 모듈 의존성 그래프 ──
   아코디언 안 좁은 칸에서 우측 패널 상단으로 나왔다. 높이를 컨테이너 기준으로
   주면 fitModuleGraphToViewport 가 실측해서 노드 크기를 키운다. */
.exec-graph {
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--pl-border);
}

.exec-graph .module-graph-viewport {
  min-height: 40cqh;
  max-height: 55cqh;
}

@media (max-width: 1023px) {
  .exec-graph .module-graph-viewport { min-height: 220px; max-height: 45vh; }
}
```

`app.css` 가 줄어 `FG004_ALLOWLIST`(400줄 상한) 에 한 걸음 가까워진다. 아직 비지는 않는다.

- [ ] **Step 4: 템플릿에서 그래프를 폼 상단으로 올린다**

`execute.html` 의 시스템 폼 안에서, `data-role="module-selector"` 절(`execute.html:317~331`)을 **폼의 첫 자식**으로 옮기고 `.exec-graph` 로 감싼다. 프리셋 패널은 그 아래로 내린다.

```jinja
      <form class="system-form grid gap-x-4 gap-y-5 sm:grid-cols-2" data-system-code="{{ system.system_code }}">
        <script type="application/json" data-role="system-definition">{{ systems_payload[system.system_code] | tojson }}</script>

        <section class="exec-graph sm:col-span-2" data-role="module-selector">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 class="text-sm font-bold text-gray-900">{{ system.name }}</h4>
              <p class="mt-1 text-xs leading-relaxed text-gray-500">그래프에서 모듈을 클릭해 제외할 수 있습니다. 잘못된 의존성 조합은 실행 시 서버가 거부합니다.</p>
            </div>
            <p class="text-xs font-medium text-gray-500" data-role="module-selection-summary">모듈 선택 준비 중</p>
          </div>
          <div class="module-graph-viewport mt-4 pb-2">
            <div class="module-graph-canvas" data-role="module-graph-canvas">
              <svg class="module-graph-edges" data-role="module-graph-edges" aria-hidden="true"></svg>
              <div class="module-graph-grid" data-role="module-graph-grid"></div>
            </div>
          </div>
          <div class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800 is-hidden" data-role="module-selection-warning"></div>
        </section>

        {# 프리셋 패널 · 인증 필드 · 실행 버튼은 기존 순서대로 이 아래에 온다 #}
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_execute_layout.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 게이트와 빌드**

Run: `python3 scripts/check_frontend_gates.py && npm run build`
Expected: 게이트 통과, 빌드 성공

`app.css` 에서 잘라낸 hex 가 `execute.css` 로 그대로 옮겨 갔다면 **FG-002 가 잡는다**(`execute.css` 는 allowlist 에 없다). 그 경우 옮긴 선언의 hex 를 `var(--c-*)` 토큰으로 바꾼다 — `primitives.css` 에 이미 대응 값이 있다.

- [ ] **Step 7: 눈으로 확인한다**

`/runs/execute` 에서 HOM(모듈 10개)을 선택한다. 확인 항목:
- 그래프가 패널 상단을 차지하고 노드가 이전보다 크다
- 엣지 곡선이 그려지고, 노드를 클릭하면 활성/비활성 색이 바뀐다
- 노드가 캔버스를 넘치지 않는다(`fitModuleGraphToViewport` 가 맞춰야 한다)

- [ ] **Step 8: 커밋**

```bash
git add app/web/frontend/styles/app.css app/web/frontend/styles/execute.css app/web/templates/execute.html tests/test_execute_layout.py
git commit -m "feat(execute): 모듈 의존성 그래프를 패널 상단 지배 요소로"
```

---

### Task 3: 좌측 목록의 오늘 상태 배지

`/api/dashboard/daily` 를 재사용한다(D6). 서버 변경 0.

**Files:**
- Create: `app/web/frontend/entries/execute-badges.ts`
- Create: `app/web/frontend/entries/execute-badges.test.ts`
- Modify: `vite.config.ts`
- Modify: `app/web/templates/execute.html` (스크립트 블록)

**Interfaces:**
- Consumes: `GET /api/dashboard/daily` 응답. `components/status-badge` 의 `renderStatusBadge(tone, label)` · `normalizeTone(value)`(`app/web/frontend/components/status-badge/index.ts`). 실제 시그니처를 열어 확인하고 그대로 쓴다
- Produces: `applySystemBadges(root: ParentNode, systems: Array<{system_code: string, tone: string, label: string}>): void` — `[data-exec-badge="{code}"]` 에 배지를 렌더한다. 목록에 없는 코드는 비워 둔다

- [ ] **Step 1: 응답 형태를 실측한다**

Run: `python3 -m pytest tests/test_daily_dashboard.py -v`

그리고 `app/contexts/insights/application/daily_dashboard.py` 를 열어 시스템별 항목의 **정확한 키 이름**(`system_code` · `tone` · `status_label` 등)을 확인한다. 아래 테스트의 픽스처를 그 키에 맞춘다. **추측하지 않는다** — 키 하나가 다르면 배지가 조용히 비어 버린다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`app/web/frontend/entries/execute-badges.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { applySystemBadges } from "./execute-badges";

function host(codes: string[]): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = codes.map((c) => `<span data-exec-badge="${c}"></span>`).join("");
  return root;
}

describe("applySystemBadges", () => {
  it("코드가 맞는 자리에 배지를 넣는다", () => {
    const root = host(["hom", "mhm"]);
    applySystemBadges(root, [{ system_code: "hom", tone: "passed", label: "정상" }]);
    expect(root.querySelector('[data-exec-badge="hom"]')!.textContent).toContain("정상");
  });

  it("응답에 없는 시스템 자리는 비워 둔다", () => {
    const root = host(["hom", "mhm"]);
    applySystemBadges(root, [{ system_code: "hom", tone: "passed", label: "정상" }]);
    expect(root.querySelector('[data-exec-badge="mhm"]')!.innerHTML).toBe("");
  });

  it("두 번 불러도 배지가 겹쳐 쌓이지 않는다", () => {
    const root = host(["hom"]);
    const data = [{ system_code: "hom", tone: "passed", label: "정상" }];
    applySystemBadges(root, data);
    applySystemBadges(root, data);
    expect(root.querySelectorAll('[data-exec-badge="hom"] > *').length).toBe(1);
  });

  it("빈 배열이면 모든 자리를 비운다 — 조회 실패 시 화면은 살아야 한다", () => {
    const root = host(["hom"]);
    applySystemBadges(root, [{ system_code: "hom", tone: "passed", label: "정상" }]);
    applySystemBadges(root, []);
    expect(root.querySelector('[data-exec-badge="hom"]')!.innerHTML).toBe("");
  });
});
```

- [ ] **Step 3: 실패를 확인한다**

Run: `npm run test -- execute-badges`
Expected: FAIL — `Cannot find module './execute-badges'`

- [ ] **Step 4: 엔트리를 만든다**

`app/web/frontend/entries/execute-badges.ts`. 상태 라벨을 **하드코딩하지 않는다**(FG-003) — 서버가 준 `label` 을 그대로 쓰고, 톤만 `normalizeTone` 으로 정규화한다.

```typescript
// 좌측 목록의 오늘 상태 배지. 서버 변경 없이 대시보드 API 를 재사용한다(설계 D6).
// 이 호출이 실패해도 실행 기능은 살아야 하므로, 실패는 '배지 없음' 으로만 나타난다.
import { normalizeTone, renderStatusBadge } from "../components/status-badge/index";

type SystemStatus = { system_code: string; tone: string; label: string };

export function applySystemBadges(root: ParentNode, systems: SystemStatus[]): void {
  const byCode = new Map(systems.map((s) => [s.system_code, s]));
  for (const slot of root.querySelectorAll<HTMLElement>("[data-exec-badge]")) {
    const code = slot.dataset.execBadge ?? "";
    const status = byCode.get(code);
    slot.innerHTML = "";
    if (!status) continue;
    slot.append(renderStatusBadge(normalizeTone(status.tone), status.label));
  }
}

export async function loadSystemBadges(root: ParentNode = document): Promise<void> {
  try {
    const response = await fetch("/api/dashboard/daily", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const payload = await response.json();
    applySystemBadges(root, extractSystems(payload));
  } catch {
    // 배지는 부가 정보다. 실패해도 화면의 주 기능은 건드리지 않는다.
  }
}
```

`extractSystems(payload)` 는 Step 1 에서 실측한 응답 구조에 맞춰 작성한다. `renderStatusBadge` 의 실제 반환 타입(Element 인지 문자열인지)도 `components/status-badge/index.ts` 를 열어 확인하고 `append` 여부를 맞춘다.

- [ ] **Step 5: Vite 엔트리로 등록한다**

`vite.config.ts` 의 `rollupOptions.input` 에 추가한다.

```typescript
        "execute-badges": resolve(__dirname, "app/web/frontend/entries/execute-badges.ts"),
```

`execute.html` 에 스크립트 블록을 추가한다(FG-005 준수 — `_assets.html` 매크로 경유).

```jinja
{% block scripts %}
{% import "_assets.html" as exec_assets %}
{{ exec_assets.asset_script("entries/execute-badges.ts") }}
{% endblock %}
```

엔트리 하단에서 기동한다:

```typescript
document.addEventListener("DOMContentLoaded", () => void loadSystemBadges());
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `npm run test && npm run typecheck && npm run lint`
Expected: 전부 PASS

- [ ] **Step 7: 눈으로 확인한다**

`/runs/execute` 좌측 목록에 오늘 상태 배지가 뜨고, 색과 라벨이 `/` 대시보드와 **같은지** 확인한다. 다르면 Cycle 0 이 덜 끝났거나 `normalizeTone` 매핑이 어긋난 것이다.

개발자 도구 Network 에서 `/api/dashboard/daily` 를 차단해 두고 새로고침해 **실행 버튼이 여전히 동작하는지** 확인한다.

- [ ] **Step 8: 커밋**

```bash
git add app/web/frontend/entries/execute-badges.ts app/web/frontend/entries/execute-badges.test.ts vite.config.ts app/web/templates/execute.html
git commit -m "feat(execute): 좌측 목록에 오늘 상태 배지 — 대시보드 API 재사용"
```

---

### Task 4: 넌스크롤 회귀 테스트

레이아웃이 조용히 무너지는 것을 막는다.

**Files:**
- Create: `tests/test_execute_viewport.py`

**Interfaces:**
- Consumes: Task 1~3 의 완성된 화면
- Produces: 없음(회귀 가드)

- [ ] **Step 1: 테스트를 쓴다**

`tests/test_dashboard_viewport.py` 의 구조(uvicorn 스레드 + Playwright)를 그대로 따른다. 포트 확보 `_free_port()` · 앱 조립 · `pytest.importorskip("playwright")` 포함.

```python
"""점검 실행 넌스크롤 Playwright 테스트.

Chromium 미설치 시 ``python3 -m playwright install chromium`` 후 재실행.
"""

VIEWPORTS = [(1366, 768), (1920, 1080), (2560, 1440)]


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_page_scroll(page_factory, width, height):
    page = page_factory(width, height)
    page.goto(f"{BASE_URL}/runs/execute")
    page.wait_for_selector(".exec")
    overflow = page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )
    assert overflow <= 1, f"{width}x{height} 에서 세로 스크롤 {overflow}px"


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_start_button_is_visible_without_scrolling(page_factory, width, height):
    page = page_factory(width, height)
    page.goto(f"{BASE_URL}/runs/execute")
    page.wait_for_selector("#suite-start-button")
    assert page.locator("#suite-start-button").is_visible()


def test_exactly_one_internal_scroller(page_factory):
    """스크롤 소유권은 우측 조건 열 하나뿐이다(설계 §4.2 규격 2번)."""
    page = page_factory(1920, 1080)
    page.goto(f"{BASE_URL}/runs/execute")
    page.wait_for_selector(".exec")
    scrollers = page.evaluate(
        """() => Array.from(document.querySelectorAll('.exec *'))
              .filter((el) => {
                  const style = getComputedStyle(el);
                  const scrollable = /auto|scroll/.test(style.overflowY);
                  return scrollable && el.scrollHeight > el.clientHeight + 1;
              })
              .map((el) => el.className)"""
    )
    assert len(scrollers) <= 1, f"내부 스크롤러가 여럿: {scrollers}"


def test_selecting_a_system_swaps_the_panel(page_factory):
    page = page_factory(1920, 1080)
    page.goto(f"{BASE_URL}/runs/execute")
    page.wait_for_selector('[data-exec-target="hom"]')
    page.click('[data-exec-target="hom"]')
    assert page.locator('[data-exec-panel="hom"]').is_visible()
    assert not page.locator('[data-exec-panel="suite"]').is_visible()
```

`page_factory` 픽스처와 `BASE_URL` 은 `tests/test_dashboard_viewport.py` 의 서버 기동 픽스처를 그대로 옮겨 쓴다. 그 파일이 픽스처를 모듈 안에 두고 있으면 공용 모듈로 뽑지 말고 **복사한다** — 두 번째 사용처가 생겼을 뿐이고, 세 번째가 생기면 그때 뽑는다.

- [ ] **Step 2: 실행한다**

Run: `python3 -m pytest tests/test_execute_viewport.py -v`
Expected: PASS. 실패하면 어느 뷰포트에서 몇 px 넘쳤는지 메시지가 알려준다 — `.exec` 의 `padding` 이나 `.exec-env` 높이를 줄인다.

Chromium 이 없으면 `python3 -m playwright install chromium` 후 재실행.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_execute_viewport.py
git commit -m "test(execute): 넌스크롤·스크롤 소유권·패널 전환 회귀 검증"
```

---

### Task 5: AC Spec 갱신과 전체 게이트

**Files:**
- Modify: `docs/specs/dashboard/02-execute-page.md`

**Interfaces:**
- Consumes: Task 1~4 의 결과
- Produces: 없음(문서)

- [ ] **Step 1: SPEC-UI-002 의 §2 구성을 갱신한다**

`docs/specs/dashboard/02-execute-page.md` 의 헤더 표에 대체 관계를 적고, §2 를 마스터-디테일 구조로 다시 쓴다. **AC-001 · AC-002 는 손대지 않는다** — 동작 규칙은 불변이다.

```markdown
| **상태** | `approved` (시각·레이아웃은 `2026-08-24-execute-promotion-design.md` §4.3 이 우선) |
```

§2 에 추가할 내용:

```markdown
### FR-004: 마스터-디테일 레이아웃

- 좌측: 점검 대상 선택 목록(SUITE + 허용 시스템). 각 항목에 오늘 상태 배지
- 우측: 선택 대상의 실행 조건 패널. 모듈 의존성 그래프가 상단 지배 요소
- 기본 선택은 SUITE
- 모든 뷰포트에서 `body` 세로 스크롤 0. 내부 스크롤은 우측 패널 하나
- `< 1024px` 에서 1열로 붕괴하고 좌측 목록은 가로 스크롤 칩 행이 된다
```

- [ ] **Step 2: 문서 정합성 가드를 돌린다**

Run: `python3 scripts/check_docs_consistency.py`
Expected: 통과

- [ ] **Step 3: 동작 불변을 확인한다**

Run: `python3 -m pytest tests/test_presets_http.py tests/test_suite_aggregate.py tests/test_suite_decider.py -v`
Expected: PASS — 이 계획은 API 를 건드리지 않았으므로 한 건도 바뀌면 안 된다.

- [ ] **Step 4: 전체 게이트를 돌린다**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

- [ ] **Step 5: 커밋**

```bash
git add docs/specs/dashboard/02-execute-page.md
git commit -m "docs(execute): SPEC-UI-002 에 마스터-디테일 레이아웃 반영"
```

---

## 완료 확인

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [ ] `npm run test && npm run typecheck && npm run lint` 통과
- [ ] `execute.html` 에 `<details>` 0건
- [ ] 1366 · 1920 · 2560 px 에서 세로 스크롤 0, 실행 버튼 가시
- [ ] 내부 스크롤러 1개(우측 패널)
- [ ] 좌측 배지 색·라벨이 `/` 대시보드와 일치
- [ ] `/api/dashboard/daily` 차단 상태에서도 실행 동작
- [ ] `app.css` 가 약 140줄 줄었다(모듈 그래프 절 이사)

## 이 계획이 남기는 것

| 항목 | 다음 단계 |
| --- | --- |
| `app.js` 약 1,400줄이 아직 이 화면을 구동한다 | Cycle 1b |
| `FG005_ALLOWLIST` 의 `/static/app.js` | Cycle 4 (app.js 소멸 시) |
| `app.css` 잔여(약 1,270줄, 400줄 상한 초과) | Cycle 1b~6 이 절씩 이사 |
| `body:has(.dash)` 와 `body:has(.exec)` 셸 중복 | 세 번째 화면이 같은 셸을 요구하면 공통으로 뽑는다 |
| 예약 등록 폼(cron 빌더)이 SUITE 패널에 남아 있다 | Cycle 6 에서 중복 판단(설계 D7) |
