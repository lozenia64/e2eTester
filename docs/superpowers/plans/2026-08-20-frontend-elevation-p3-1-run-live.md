# 프론트엔드 고도화 P3-1 (Run 상세 라이브) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run/Suite 상세의 서버 최초 렌더를 `StatusBadge` 컴포넌트 경계 안으로 넣어 상태 배지 버그 3건을 근절하고, 상태 전이 점등과 치유 이력을 화면에 드러낸다.

**Architecture:** 템플릿이 자체 상태 색 맵을 들고 있는 것이 문제의 근원이므로, 톤·라벨 계산을 Jinja 전역 함수 하나(`status_badge_view`)로 옮기고 마크업은 P2 의 `status-badge` 매크로에 위임한다. 재발은 FG-006 이 차단하고, 파이썬 SSOT ↔ TS 생성물 ↔ 서버 렌더 3자 일치를 테스트가 강제한다. 점등은 `data-tone` 이 이미 붙으므로 순수 CSS 로 처리해 JS 변경을 피한다.

**Tech Stack:** Python 3.13 · FastAPI · Jinja2 · pytest · CSS · Vitest

**Spec:** `docs/superpowers/specs/2026-08-20-frontend-elevation-p3-1-run-live-design.md`

## Global Constraints

- UI·로그·README 문자열은 **한국어**. (`AGENTS.md`)
- **라이트 단일 팔레트.** 다크모드·테마 분기 금지.
- **톤 축은 정확히 9개**: `passed` `anomaly` `error` `running` `waiting_input` `blocked` `skipped` `cancelled` `pending`
- `app/web/frontend/**` 내 하드코딩 hex 금지 (FG-002). 색은 토큰만.
- 엔트리·컴포넌트 파일 **400줄 상한** (FG-004).
- **`prefers-reduced-motion: reduce` 에서 모든 pulse·깜빡임 정지.** (P2 에서 이 가드를 빠뜨려 접근성 회귀를 만든 전례가 있다.)
- **`recovered` 배지와 AI 분석 패널은 재작성하지 않는다** — 이미 온전하다.
- **`app.js` 변경은 아래 열거된 6곳으로 제한한다.** 리팩터링·이관은 하지 않는다(Step 7 의 몫).
  `3127` · `3144-3147` · `3167-3170` (Run) / `2991-2994` · `3031` · `3105` (Suite).
  **이 변경은 선택이 아니라 필수다** — `app.js:3144` 이 WS 갱신마다 `#run-status` 에 영문 enum 값을
  다시 쓰고, `app.js:3127` 의 `updateRunActions()` 가 그 **텍스트**를 소문자로 만들어
  `RUN_ACTIVE_STATUSES = {"pending","running","waiting_input"}` 와 비교한다. 배지 텍스트만
  한국어로 바꾸면 매칭이 깨져 **실행 중인 Run 의 취소 버튼이 사라진다.** 상태 판정을
  `dataset.status` 로 옮겨야 안전하다.
- 새 CI 게이트를 등록하지 않는다. FG-006 은 기존 `frontend_gates` 안의 규칙 추가다.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full` + `npm run build && npm run typecheck && npm run lint && npm run test`.

---

## 설계와의 의도적 차이 1건

스펙 §3.1 은 *"뷰에 `status_tone` 필드를 추가한다"* 고 적었다. **구현은 Jinja 전역 함수로 바꾼다.**

이유: `app/contexts/run/views/view.py:33` 의 `RunView.modules` 는 `list[RunModule]` 로 **도메인 모델을 의도적으로 그대로 재사용**한다(해당 파일 docstring: *"모듈 항목은 이미 공개에 안전한 `RunModule` 형태를 그대로 재사용한다(필드 드리프트 방지)"*). 모듈에 `status_tone` 을 넣으려면 쓰기 모델인 `RunModule` 을 고쳐야 하고, 이는 그 규율을 깨뜨린다. `ModuleView` 도 `RunModule` 을 감싸기만 한다.

대신 `app/api/routes_daily.py:21` 이 이미 쓰는 패턴 — `templates.env.globals["system_summary_badge"] = system_summary_badge` — 을 따른다. 뷰 계약을 넓히지 않고 템플릿이 톤 계산을 하지 않는다는 목표를 동일하게 달성한다.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `app/web/status_view.py` (신규) | `status_badge_view(status) -> StatusBadgeView` — enum 타입별 톤·라벨 해석. I/O 없음 |
| `app/api/routes_dashboard.py` (수정) | Jinja 전역에 `status_badge_view` 등록 |
| `app/web/templates/run.html` (수정) | `status_pill` 삭제, 배지 3곳을 매크로로 |
| `app/web/templates/suite.html` (수정) | 동일 |
| `app/web/frontend/components/status-badge/macro.jinja` (수정) | `elem_id`·`status_value`·`role` 인자 추가 (첫 소비자가 P3-1) |
| `app/web/static/app.js` (수정, **6곳 한정**) | 상태 판정을 `dataset.status` 로 이관 + 배지 마크업 통일 |
| `scripts/check_frontend_gates.py` (수정) | FG-006 + `FG006_ALLOWLIST` |
| `app/web/frontend/components/status-badge/styles.css` (수정) | 점등·깜빡임 + reduced-motion |
| `app/web/frontend/styles/app.css` (수정) | `.node-card.status-waiting_input` 토큰 교정 |
| `app/contexts/healing/service.py` (수정) | `list_events` 에 `run_id` 필터 |
| `app/api/routes_dashboard.py` (수정) | Run 상세가 치유 이벤트를 함께 조회 |
| `tests/test_status_badge_view.py` (신규) | 톤·라벨 해석 단위 테스트 |
| `tests/test_run_detail_status_badge.py` (신규) | 서버 렌더 계약 (버그 3건 회귀 가드) |
| `tests/test_status_ssot_alignment.py` (신규) | 3자 일치 |
| `tests/test_frontend_gates.py` (수정) | FG-006 단위 테스트 |
| `tests/test_run_detail_healing.py` (신규) | 치유 이력 표시 |

---

## Task 1: `status_badge_view` — 톤·라벨 해석의 단일 경로

**Files:**
- Create: `app/web/status_view.py`
- Test: `tests/test_status_badge_view.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class StatusBadgeView:
      tone: str
      label: str

  def status_badge_view(status: RunStatus | ModuleStatus | SuiteStatus) -> StatusBadgeView
  ```
  알 수 없는 타입에는 `TypeError` 를 던진다(조용한 fallback 금지).

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_status_badge_view.py`:

```python
"""상태 → 배지(톤·라벨) 해석 단일 경로.

템플릿이 자체 색 맵을 들고 있던 것이 P3-1 이 고치는 버그의 근원이다. 이 함수가
유일한 해석 경로이며, status_labels.py 의 SSOT 만 참조한다.
"""

import pytest

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import (
    STATUS_TONES,
    module_status_badge_tone,
    module_status_label,
    run_status_badge_tone,
    run_status_label,
    suite_status_badge_tone,
    suite_status_label,
)
from app.web.status_view import StatusBadgeView, status_badge_view


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_module_status_matches_ssot(status: ModuleStatus) -> None:
    view = status_badge_view(status)
    assert view.tone == module_status_badge_tone(status)
    assert view.label == module_status_label(status)


@pytest.mark.parametrize("status", list(RunStatus))
def test_run_status_matches_ssot(status: RunStatus) -> None:
    view = status_badge_view(status)
    assert view.tone == run_status_badge_tone(status)
    assert view.label == run_status_label(status)


@pytest.mark.parametrize("status", list(SuiteStatus))
def test_suite_status_matches_ssot(status: SuiteStatus) -> None:
    view = status_badge_view(status)
    assert view.tone == suite_status_badge_tone(status)
    assert view.label == suite_status_label(status)


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_every_tone_is_in_the_nine_tone_axis(status: ModuleStatus) -> None:
    assert status_badge_view(status).tone in STATUS_TONES


def test_anomaly_and_error_are_not_neutral() -> None:
    """버그 2 회귀 가드 — 이 둘이 pending/회색으로 떨어지면 안 된다."""
    assert status_badge_view(ModuleStatus.ANOMALY).tone == "anomaly"
    assert status_badge_view(ModuleStatus.ERROR).tone == "error"


def test_legacy_failed_is_anomaly_not_error() -> None:
    """버그 3 회귀 가드 — 레거시 FAILED 는 이상징후(amber)다."""
    assert status_badge_view(ModuleStatus.FAILED).tone == "anomaly"
    assert status_badge_view(ModuleStatus.FAILED).label == "이상징후"


def test_labels_are_korean() -> None:
    """버그 1 회귀 가드 — 영문 enum 값이 라벨로 새지 않는다."""
    for status in ModuleStatus:
        label = status_badge_view(status).label
        assert label != status.value
        assert not label.isascii(), (status, label)


def test_unknown_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="지원하지 않는 상태 타입"):
        status_badge_view("PASSED")  # type: ignore[arg-type]


def test_view_is_immutable() -> None:
    view = status_badge_view(ModuleStatus.PASSED)
    assert isinstance(view, StatusBadgeView)
    with pytest.raises(AttributeError):
        view.tone = "error"  # type: ignore[misc]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_status_badge_view.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.web.status_view'`

- [ ] **Step 3: 구현한다**

`app/web/status_view.py`:

```python
"""상태 → 배지(톤·라벨) 해석 — 템플릿이 쓰는 단일 경로.

템플릿이 자체 색 맵(`status_pill`)을 들고 있던 것이 P3-1 이 고치는 버그의 근원이다.
Jinja 전역으로 등록해 템플릿이 톤을 직접 계산하지 않게 한다
(`app/api/routes_daily.py` 의 `system_summary_badge` 등록과 같은 패턴).

뷰 모델에 필드를 추가하지 않는 이유: `RunView.modules` 는 도메인 `RunModule` 을
의도적으로 그대로 재사용하며(필드 드리프트 방지), 여기에 표현용 필드를 넣으면
그 규율이 깨진다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import (
    module_status_badge_tone,
    module_status_label,
    run_status_badge_tone,
    run_status_label,
    suite_status_badge_tone,
    suite_status_label,
)


@dataclass(frozen=True)
class StatusBadgeView:
    """배지 렌더에 필요한 최소 표현. `status-badge` 매크로의 인자와 1:1."""

    tone: str
    label: str


def status_badge_view(status: RunStatus | ModuleStatus | SuiteStatus) -> StatusBadgeView:
    """상태 enum → 톤·라벨. 톤·라벨 규칙은 status_labels.py 가 유일한 출처다.

    문자열을 받지 않는다 — 어느 enum 인지 모르면 톤 규칙을 고를 수 없고,
    조용히 잘못된 톤을 주는 것보다 실패하는 편이 안전하다.
    """
    if isinstance(status, ModuleStatus):
        return StatusBadgeView(module_status_badge_tone(status), module_status_label(status))
    if isinstance(status, RunStatus):
        return StatusBadgeView(run_status_badge_tone(status), run_status_label(status))
    if isinstance(status, SuiteStatus):
        return StatusBadgeView(suite_status_badge_tone(status), suite_status_label(status))
    msg = (
        f"지원하지 않는 상태 타입: {type(status).__name__}. "
        "RunStatus/ModuleStatus/SuiteStatus 중 하나를 넘기세요."
    )
    raise TypeError(msg)
```

**주의 — enum 판정 순서:** `RunStatus`·`ModuleStatus`·`SuiteStatus` 는 모두 `StrEnum` 이므로 `isinstance(x, str)` 이 참이다. 따라서 문자열 분기를 먼저 두면 안 된다. 위 순서(구체 타입 먼저, 마지막에 `TypeError`)를 유지한다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_status_badge_view.py -q`
Expected: PASS

`test_labels_are_korean` 이 실패하면 `status_labels.py` 의 라벨 맵에 빠진 상태가 있는 것이다. 그 경우 이 테스트가 아니라 **SSOT 를 고친다.**

- [ ] **Step 5: 커밋**

```bash
git add app/web/status_view.py tests/test_status_badge_view.py
git commit -m "feat(web): 상태→배지 해석 단일 경로(status_badge_view) 추가"
```

---

## Task 2: Run/Suite 템플릿의 `status_pill` 제거

**Files:**
- Modify: `app/api/routes_dashboard.py:23-25` (Jinja 전역 등록)
- Modify: `app/web/templates/run.html:6, 22, 85`
- Modify: `app/web/templates/suite.html:6, 20, 67`
- Test: `tests/test_run_detail_status_badge.py`

**Interfaces:**
- Consumes: Task 1 의 `status_badge_view(status) -> StatusBadgeView`, P2 의 `app/web/frontend/components/status-badge/macro.jinja` 의 `status_badge(status, label, size="md")`
- Produces: Run/Suite 상세 HTML 의 상태 배지가 `class="status-badge" data-tone="…"` 형태로 렌더된다

- [ ] **Step 1: 서버 렌더 계약 테스트를 작성한다**

`tests/test_run_detail_status_badge.py`:

```python
"""Run 상세 상태 배지의 서버 렌더 계약 — 버그 3건 회귀 가드.

이전에는 run.html 이 자체 status_pill 맵을 들고 있어
(1) 배지 텍스트가 영문 enum 값, (2) ANOMALY/ERROR 가 회색,
(3) 레거시 FAILED 가 빨강이었다. 완료된 Run 은 WS 갱신이 오지 않아 끝까지 깨졌다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_dashboard
from app.api.dependencies import get_run_queries
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.views.view import RunView
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import RunModule
from app.core.status_labels import module_status_badge_tone, module_status_label

BADGE_RE = re.compile(
    r'<span class="status-badge"[^>]*data-tone="(?P<tone>[a-z_]+)"[^>]*>(?P<text>[^<]*)</span>'
)


def _run_view(module_status: ModuleStatus, run_status: RunStatus = RunStatus.PASSED) -> RunView:
    return RunView(
        run_id="run1",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=run_status,
        status_label="정상",
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="m1",
                name="로그인",
                group="인증",
                order=1,
                status=module_status,
            )
        ],
    )


class _StubRunQueries:
    def __init__(self, run: RunView) -> None:
        self._run = run

    async def get_run_detail(self, run_id: str) -> RunView:
        if run_id != self._run.run_id:
            raise KeyError(run_id)
        return self._run


def _html(run: RunView) -> str:
    app = FastAPI()
    app.include_router(routes_dashboard.router)
    app.dependency_overrides[get_run_queries] = lambda: _StubRunQueries(run)
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="u1",
        email="tester@test.local",
        name="tester",
        role="admin",
        hashed_password="x",
        created_at=datetime.now(UTC),
    )
    with TestClient(app) as client:
        response = client.get("/runs/run1")
        assert response.status_code == 200, response.text
        return response.text


def test_status_pill_map_is_gone() -> None:
    """템플릿이 자체 색 맵을 다시 들면 이 테스트가 막는다."""
    source = __import__("pathlib").Path("app/web/templates/run.html").read_text(encoding="utf-8")
    assert "status_pill" not in source


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_module_badge_tone_and_label_match_ssot(status: ModuleStatus) -> None:
    html = _html(_run_view(status))
    badges = BADGE_RE.findall(html)
    tones = {tone for tone, _ in badges}
    texts = {text.strip() for _, text in badges}
    assert module_status_badge_tone(status) in tones, (status, tones)
    assert module_status_label(status) in texts, (status, texts)


def test_anomaly_module_is_not_rendered_neutral() -> None:
    """버그 2 회귀 가드."""
    html = _html(_run_view(ModuleStatus.ANOMALY))
    assert 'data-tone="anomaly"' in html


def test_error_module_is_not_rendered_neutral() -> None:
    """버그 2 회귀 가드."""
    html = _html(_run_view(ModuleStatus.ERROR))
    assert 'data-tone="error"' in html


def test_legacy_failed_module_renders_as_anomaly() -> None:
    """버그 3 회귀 가드."""
    html = _html(_run_view(ModuleStatus.FAILED))
    assert 'data-tone="anomaly"' in html


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_no_english_enum_value_in_badge_text(status: ModuleStatus) -> None:
    """버그 1 회귀 가드 — 클래스 값은 정당하므로 배지 텍스트만 검사한다."""
    html = _html(_run_view(status))
    texts = {text.strip() for _, text in BADGE_RE.findall(html)}
    assert status.value not in texts, (status, texts)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_run_detail_status_badge.py -q`
Expected: FAIL — `test_status_pill_map_is_gone` 은 `status_pill` 존재로 실패, 나머지는 `status-badge` 마크업이 없어 실패

- [ ] **Step 3: Jinja 전역을 등록한다**

`app/api/routes_dashboard.py` 의 `templates.env.globals["asset_css"] = asset_css` (25행) 아래에 추가:

```python
templates.env.globals["status_badge_view"] = status_badge_view
```

import 추가: `from app.web.status_view import status_badge_view`

- [ ] **Step 4: 매크로에 필요한 속성 인자를 추가한다**

`app/web/frontend/components/status-badge/macro.jinja` 는 **현재 호출부가 없다** (P2 가 컴포넌트 페어 규약으로 만들었으나 TS 쪽만 쓰였다). P3-1 이 첫 소비자이므로 시그니처를 자유롭게 확정한다.

`app.js` 가 `#run-status`·`#suite-status` 를 `getElementById` 로 찾고 `data-role="module-status"`·`"step-status"` 로 모듈/스텝 배지를 찾으므로, 그 훅을 배지 자체가 들고 있어야 한다. 또한 상태 판정용 원시 enum 값을 `data-status` 로 실어 보낸다(Step 6 참조).

```jinja
{% macro status_badge(tone, label, size="md", role="", elem_id="", status_value="") -%}
<span class="status-badge"{% if elem_id %} id="{{ elem_id }}"{% endif %} data-tone="{{ tone }}" data-size="{{ size }}"{% if status_value %} data-status="{{ status_value }}"{% endif %}{% if role %} data-role="{{ role }}"{% endif %}>{{ label }}</span>
{%- endmacro %}
```

첫 인자 이름을 `status` → `tone` 으로 바꾼다 — 실제로 받는 것이 톤이고, `status_value` 와 혼동되지 않아야 한다.

- [ ] **Step 5: `run.html` 을 고친다**

6행의 `{% set status_pill = {...} %}` 줄을 **삭제**하고 그 자리에 매크로를 임포트한다:

```jinja
{% import "components/status-badge/macro.jinja" as sb %}
```

22행(Run 상태 배지)을 교체한다. `id="run-status"` 를 배지 자체가 갖는다:

```jinja
        {% set rb = status_badge_view(run.status) %}
        {{ sb.status_badge(rb.tone, rb.label, size="md", elem_id="run-status", status_value=run.status.value) }}
```

85행(모듈 상태 배지)을 교체한다. `data-role="module-status"` 를 보존한다 — `app/web/static/app.js:1913` 이 `card.querySelector('[data-role="module-status"]')` 로 이 노드를 찾는다:

```jinja
                    {% set mb = status_badge_view(module.status) %}
                    {{ sb.status_badge(mb.tone, mb.label, size="sm", role="module-status", status_value=module.status.value) }}
```

- [ ] **Step 6: `run.html` 관련 `app.js` 3곳을 고친다**

`app.js` 는 `#run-status` 의 **텍스트**로 버튼 표시를 결정한다. 배지 텍스트를 한국어로 바꾸면 그 판정이 깨지므로 판정 근거를 `dataset.status` 로 옮긴다.

**(a) 3127행** — 초기 바인딩:

```javascript
    updateRunActions(document.getElementById("run-status")?.dataset.status);
```

**(b) 3144~3147행** — snapshot 처리. 현재는 영문 enum 값을 텍스트로 쓰고 Tailwind 클래스를 섞는다. 컴포넌트 형태로 통일한다:

```javascript
            const snapshotStatusNode = document.getElementById("run-status");
            snapshotStatusNode.textContent = window.__statusBadge.statusLabel(message.payload.status);
            snapshotStatusNode.className = "status-badge";
            snapshotStatusNode.dataset.size = "md";
            snapshotStatusNode.dataset.tone = window.__statusBadge.normalizeTone(message.payload.status);
            snapshotStatusNode.dataset.status = message.payload.status;
            updateRunActions(message.payload.status);
```

`updateRunActions` 에는 **원시 상태값을 그대로** 넘긴다(이미 그렇게 되어 있다). 라벨을 넘기지 않는다.

**(c) 3167~3170행** — `run_status` 이벤트 처리. 같은 형태로 바꾼다:

```javascript
            const runStatus = document.getElementById("run-status");
            runStatus.textContent = window.__statusBadge.statusLabel(message.run_status);
            runStatus.className = "status-badge";
            runStatus.dataset.size = "md";
            runStatus.dataset.tone = window.__statusBadge.normalizeTone(message.run_status);
            runStatus.dataset.status = message.run_status;
            updateRunActions(message.run_status);
```

**이 3곳 외에는 `app.js` 를 고치지 않는다.**

- [ ] **Step 7: `suite.html` 과 관련 `app.js` 3곳을 고친다**

`suite.status` 와 `step.status` 는 **둘 다 `SuiteStatus`** 다 (`app/core/suite_models.py:17,23` 확인). `/suites/{suite_id}` 라우트는 `suite_service.get_suite()` 가 돌려주는 `SuiteRun` 엔티티를 그대로 템플릿에 넘긴다.

`suite.html` 6행의 `status_pill` 을 삭제하고 매크로를 임포트한다:

```jinja
{% import "components/status-badge/macro.jinja" as sb %}
```

20행:

```jinja
        {% set sv = status_badge_view(suite.status) %}
        {{ sb.status_badge(sv.tone, sv.label, size="md", elem_id="suite-status", status_value=suite.status.value) }}
```

67행 — `data-role="step-status"` 를 보존한다 (`app.js:2947` 이 이 노드를 갱신한다):

```jinja
                {% set stv = status_badge_view(step.status) %}
                {{ sb.status_badge(stv.tone, stv.label, size="sm", role="step-status", status_value=step.status.value) }}
```

`app.js` 의 Suite 쪽 3곳도 같은 규칙으로 바꾼다:

**2991~2994행:**

```javascript
    const statusNode = document.getElementById("suite-status");
    statusNode.textContent = window.__statusBadge.statusLabel(suite.status);
    statusNode.className = "status-badge";
    statusNode.dataset.size = "md";
    statusNode.dataset.tone = window.__statusBadge.normalizeTone(suite.status);
    statusNode.dataset.status = suite.status;
```

**3031행:**

```javascript
    updateSuiteActions(document.getElementById("suite-status")?.dataset.status);
```

**3105행** — 이 줄의 전후를 읽어 `#suite-status` 를 어떻게 쓰는지 확인하고, 텍스트를 쓰는 자리면 (2991행과) 같은 6줄 형태로, 판정에 쓰는 자리면 `dataset.status` 로 바꾼다.

- [ ] **Step 8: 배지가 `data-status` 를 싣는지 테스트에 추가한다**

`tests/test_run_detail_status_badge.py` 에 추가한다:

```python
def test_run_badge_carries_raw_status_for_action_buttons() -> None:
    """app.js 가 버튼 표시를 판정하는 근거. 없으면 실행 중 Run 의 취소 버튼이 사라진다."""
    html = _html(_run_view(ModuleStatus.PASSED, run_status=RunStatus.RUNNING))
    assert 'id="run-status"' in html
    assert 'data-status="RUNNING"' in html


def test_module_badge_keeps_the_js_hook() -> None:
    """app.js:1913 이 이 속성으로 모듈 배지를 찾는다."""
    html = _html(_run_view(ModuleStatus.PASSED))
    assert 'data-role="module-status"' in html
```

- [ ] **Step 9: 통과를 확인한다**

Run: `python3 -m pytest tests/test_run_detail_status_badge.py -q`
Expected: PASS

Run: `python3 -m pytest tests/test_run_detail_recovery_badge.py -q`
Expected: PASS — `recovered` 배지는 건드리지 않았으므로 그대로 통과해야 한다

Run: `npm run test`
Expected: PASS — `status-badge/index.test.ts` 8건은 TS 쪽이라 매크로 변경에 영향받지 않는다

- [ ] **Step 10: 버튼 동작을 육안 검증한다**

이 단계는 **생략하면 안 된다.** 자동 테스트가 `app.js` 의 버튼 로직을 덮지 않는다(app.js 는 Vitest 대상이 아니다).

앱을 띄우고:
1. Run 을 실행한다 → 상세 화면에서 **"실행 취소" 버튼이 보이는지** 확인
2. Run 이 끝난 뒤 → **"동일 조건으로 재실행" 버튼으로 바뀌는지** 확인
3. 완료된 `ERROR` Run 을 새로 열어 → 배지가 **빨강 + "점검실패"** 인지 확인
4. Suite 상세에서도 1~2 를 반복 (`#suite-cancel`)
5. 브라우저 콘솔 에러 0건

1 또는 2 가 깨지면 Step 6/7 의 `dataset.status` 배선이 빠진 것이다.

- [ ] **Step 11: 커밋**

```bash
git add app/api/routes_dashboard.py app/web/templates/run.html app/web/templates/suite.html         app/web/frontend/components/status-badge/macro.jinja app/web/static/app.js         tests/test_run_detail_status_badge.py
git commit -m "fix(web): Run/Suite 상세 상태 배지를 컴포넌트로 교체 — 회색·영문 배지 버그 수정"
```

---

## Task 3: 3자 일치 테스트

**Files:**
- Test: `tests/test_status_ssot_alignment.py`

**Interfaces:**
- Consumes: Task 1 의 `status_badge_view`, 생성물 `app/web/frontend/lib/status.generated.ts`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_status_ssot_alignment.py`:

```python
"""파이썬 SSOT ↔ TS 생성물 ↔ 서버 렌더 3자 일치.

같은 상태를 세 경로가 다르게 그리던 것이 P3-1 이 고친 버그의 본질이다.
어느 한쪽만 바뀌면 이 테스트가 막는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import STATUS_TONES, module_status_label
from app.web.status_view import status_badge_view

GENERATED_TS = Path("app/web/frontend/lib/status.generated.ts")


def _parse_ts_object(source: str, name: str) -> dict[str, str]:
    """생성물 TS 의 `export const <name>: Record<string, string> = { ... };` 를 읽는다.

    생성기가 만드는 형식은 결정적이다(키·값 모두 이중 인용부호, 후행 콤마).
    JSON 으로 바꿔 파싱하므로 정규식으로 값을 하나씩 긁지 않는다.
    """
    match = re.search(
        rf"export const {name}: Record<string, string> = \{{(.*?)\n\}};", source, re.S
    )
    assert match, f"{name} 을 {GENERATED_TS} 에서 찾지 못했습니다."
    body = match.group(1).strip().rstrip(",")
    return json.loads("{" + body + "}")


@pytest.fixture(scope="module")
def generated_source() -> str:
    assert GENERATED_TS.exists(), (
        f"{GENERATED_TS} 가 없습니다. `python3 scripts/gen_frontend_tokens.py` 를 실행하세요."
    )
    return GENERATED_TS.read_text(encoding="utf-8")


def test_ts_tone_map_matches_python(generated_source: str) -> None:
    """축 3: TS 생성물의 톤 매핑 == 파이썬 톤 매핑."""
    ts_map = _parse_ts_object(generated_source, "STATUS_TONE_MAP")
    for status in ModuleStatus:
        assert ts_map[status.value.lower()] == status_badge_view(status).tone, status


def test_ts_labels_match_python(generated_source: str) -> None:
    ts_labels = _parse_ts_object(generated_source, "MODULE_STATUS_LABELS")
    for status in ModuleStatus:
        assert ts_labels[status.value.lower()] == module_status_label(status), status


def test_ts_union_covers_the_nine_tones(generated_source: str) -> None:
    for tone in STATUS_TONES:
        assert f'"{tone}"' in generated_source, tone


@pytest.mark.parametrize(
    "enum_cls", [ModuleStatus, RunStatus, SuiteStatus], ids=["module", "run", "suite"]
)
def test_every_status_resolves_into_the_nine_tone_axis(enum_cls) -> None:
    for status in enum_cls:
        assert status_badge_view(status).tone in STATUS_TONES, status
```

- [ ] **Step 2: 실패 여부를 확인한다**

Run: `python3 -m pytest tests/test_status_ssot_alignment.py -q`

**여기서는 통과할 가능성이 높다** — P1/P2 가 이미 일치를 만들어 놓았기 때문이다. 이 테스트는 새 기능을 구동하는 것이 아니라 **일치를 못 박는 가드**다. 통과하면 그대로 진행한다.

실패하면 그것이 곧 실제 드리프트다. `python3 scripts/gen_frontend_tokens.py` 로 생성물을 갱신하고 다시 돌린다.

- [ ] **Step 3: 가드가 실제로 작동하는지 확인한다**

일부러 깨뜨려 본다:

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("app/web/frontend/lib/status.generated.ts")
s = p.read_text(encoding="utf-8")
p.write_text(s.replace('"error": "점검실패"', '"error": "FAILED"', 1), encoding="utf-8")
PY
python3 -m pytest tests/test_status_ssot_alignment.py -q
```

Expected: FAIL (`test_ts_labels_match_python`)

원상복구:

```bash
python3 scripts/gen_frontend_tokens.py
python3 -m pytest tests/test_status_ssot_alignment.py -q
```

Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/test_status_ssot_alignment.py
git commit -m "test(web): 파이썬 SSOT·TS 생성물·서버 렌더 3자 일치 가드 추가"
```

---

## Task 4: FG-006 — 템플릿의 상태 표현 하드코딩 차단

**Files:**
- Modify: `scripts/check_frontend_gates.py`
- Modify: `tests/test_frontend_gates.py`
- Modify: `docs/CI.md`

**Interfaces:**
- Produces: `check_fg006_no_template_status_literals(root: Path) -> list[str]`, 상수 `FG006_ALLOWLIST: set[str]`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_frontend_gates.py` 에 추가:

```python
from scripts.check_frontend_gates import check_fg006_no_template_status_literals


def test_fg006_flags_status_color_pair(tmp_path):
    _write(
        tmp_path,
        "app/web/templates/x.html",
        '<span class="rounded-full bg-red-100 text-red-700">점검실패</span>',
    )
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert problems, problems
    assert "bg-red-100" in problems[0]


def test_fg006_allows_decorative_single_color(tmp_path):
    """장식용 단독 배경색은 상태 표현이 아니다."""
    _write(tmp_path, "app/web/templates/x.html", '<div class="bg-indigo-50 p-4">배너</div>')
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_bg_white(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", '<div class="bg-white shadow">카드</div>')
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_flags_korean_status_label(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", "<span>이상징후</span>")
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert problems
    assert "이상징후" in problems[0]


def test_fg006_skips_allowlisted_template(tmp_path, monkeypatch):
    import scripts.check_frontend_gates as gates

    monkeypatch.setattr(gates, "FG006_ALLOWLIST", {"app/web/templates/legacy.html"})
    _write(
        tmp_path,
        "app/web/templates/legacy.html",
        '<span class="bg-red-100 text-red-700">점검실패</span>',
    )
    assert gates.check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_does_not_allowlist_run_and_suite(tmp_path):
    """P3-1 이 고친 두 템플릿은 처음부터 allowlist 밖에 있어야 한다."""
    import scripts.check_frontend_gates as gates

    assert "app/web/templates/run.html" not in gates.FG006_ALLOWLIST
    assert "app/web/templates/suite.html" not in gates.FG006_ALLOWLIST
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_frontend_gates.py -q -k fg006`
Expected: FAIL — `ImportError: cannot import name 'check_fg006_no_template_status_literals'`

- [ ] **Step 3: 구현한다**

`scripts/check_frontend_gates.py` 의 `FG005_ALLOWLIST` 정의 아래에 추가:

```python
# P3-1 이후에도 상태 색·라벨을 하드코딩한 채 남아 있는 템플릿.
# Step 7 이 화면을 이관할 때마다 한 줄씩 지운다. 비면 FG-006 이 완성된다.
# run.html·suite.html 은 P3-1 이 고쳤으므로 처음부터 여기에 없다.
FG006_ALLOWLIST = {
    "app/web/templates/base.html",
    "app/web/templates/execute.html",
    "app/web/templates/self_healing.html",
    "app/web/templates/admin/base.html",
    "app/web/templates/admin/users.html",
}

# 상태 배지의 형태 — 배경+전경이 쌍으로 붙은 유틸리티. 장식용 단독 배경색과 구분된다.
_STATUS_COLOR_PAIR = re.compile(
    r"bg-(?:emerald|amber|red|orange|slate|zinc|blue|gray|green|yellow)-\d{2,3}"
    r"\s+text-\w+-\d{2,3}"
)

_STATUS_LABEL_LITERALS = (
    "정상",
    "이상징후",
    "점검실패",
    "입력 대기",
    "실행 중",
    "차단",
    "제외",
    "취소",
)
```

그리고 체크 함수를 추가한다:

```python
def check_fg006_no_template_status_literals(root: Path = REPO_ROOT) -> list[str]:
    """FG-006: 템플릿에 상태 색 쌍·상태 라벨 하드코딩 금지.

    run.html 이 자체 status_pill 맵을 들고 있어 ANOMALY/ERROR 배지가 회색으로
    렌더되던 사고(P3-1)를 막는다. FG-003 은 frontend/**/*.ts 만 보므로
    템플릿은 무검증이었다.
    """
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        rel = _rel(path, root)
        if rel in FG006_ALLOWLIST:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            pair = _STATUS_COLOR_PAIR.search(line)
            if pair:
                problems.append(
                    f"[FG-006] {rel}:{lineno} 상태 색 하드코딩 `{pair.group(0)}` — "
                    "components/status-badge/macro.jinja 의 status_badge 를 쓰세요."
                )
            for label in _STATUS_LABEL_LITERALS:
                if label in line:
                    problems.append(
                        f"[FG-006] {rel}:{lineno} 상태 라벨 하드코딩 `{label}` — "
                        "status_badge_view(status).label 을 쓰세요."
                    )
    return problems
```

`CHECKS` 튜플에 추가한다:

```python
CHECKS = (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
    check_fg006_no_template_status_literals,
)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_frontend_gates.py -q`
Expected: PASS

- [ ] **Step 5: 실제 저장소에 대해 돌린다**

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과

위반이 보고되면 두 갈래다:
- `run.html`/`suite.html` 위반 → Task 2 가 덜 끝났다. 남은 리터럴을 매크로로 옮긴다.
- allowlist 에 없는 다른 템플릿 위반 → 그 파일을 `FG006_ALLOWLIST` 에 추가하고, **주석에 왜 남는지(Step 7 이관 대기)를 적는다.**

- [ ] **Step 6: `docs/CI.md` 를 갱신한다**

"프론트엔드 게이트 요약" 표에 행을 추가한다:

```markdown
| FG-006 | 템플릿의 상태 색 쌍·상태 라벨 하드코딩 금지 (allowlist 축소형) |
```

- [ ] **Step 7: 커밋**

```bash
git add scripts/check_frontend_gates.py tests/test_frontend_gates.py docs/CI.md
git commit -m "feat(ci): FG-006 추가 — 템플릿의 상태 표현 하드코딩 차단"
```

---

## Task 5: 점등 — 상태 전이를 보이게

**Files:**
- Modify: `app/web/frontend/components/status-badge/styles.css`
- Modify: `app/web/frontend/styles/app.css:379-381`
- Test: `tests/test_reduced_motion_guard.py`

**Interfaces:**
- Consumes: Task 2 가 심은 `data-tone` 속성

- [ ] **Step 1: reduced-motion 가드 테스트를 작성한다**

애니메이션 자체는 시각 효과라 단위 테스트로 검증할 가치가 낮지만, **접근성 가드의 존재**는 기계적으로 검증할 수 있고 P2 에서 실제로 빠뜨린 항목이다.

`tests/test_reduced_motion_guard.py`:

```python
"""움직임을 넣는 CSS 는 prefers-reduced-motion 가드를 동반해야 한다.

P2 에서 카운트업을 컴포넌트로 이관할 때 원본 dashboard.js 의 `if (REDUCED)`
가드를 빠뜨려 접근성 회귀를 만들었다. 그 재발을 막는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ANIMATED_CSS = [
    Path("app/web/frontend/components/status-badge/styles.css"),
    Path("app/web/frontend/components/kpi-card/styles.css"),
]


@pytest.mark.parametrize("path", ANIMATED_CSS, ids=lambda p: p.name)
def test_animation_is_guarded_by_reduced_motion(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    uses_motion = "animation" in source or "@keyframes" in source
    if not uses_motion:
        pytest.skip(f"{path} 에 움직임이 없다")
    assert "prefers-reduced-motion" in source, (
        f"{path} 가 애니메이션을 쓰는데 prefers-reduced-motion 가드가 없다."
    )


def test_status_badge_defines_running_and_waiting_input_motion() -> None:
    """설계 §3.4 — running 은 은은하게, waiting_input 은 눈에 띄게."""
    source = Path("app/web/frontend/components/status-badge/styles.css").read_text(encoding="utf-8")
    assert '[data-tone="running"]' in source
    assert '[data-tone="waiting_input"]' in source
    assert "@keyframes" in source


def test_reduced_motion_block_disables_animation() -> None:
    source = Path("app/web/frontend/components/status-badge/styles.css").read_text(encoding="utf-8")
    start = source.index("prefers-reduced-motion")
    block = source[start : start + 400]
    assert "animation: none" in block, block
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_reduced_motion_guard.py -q`
Expected: FAIL — `test_status_badge_defines_running_and_waiting_input_motion` (아직 `@keyframes` 없음)

- [ ] **Step 3: 점등 CSS 를 추가한다**

`app/web/frontend/components/status-badge/styles.css` 끝에 추가:

```css
/* ── 점등 (설계 §3.4) ─────────────────────────────────────────
   data-tone 이 바뀔 때 색이 전이되고, 진행 중·입력 대기만 계속 움직인다.
   색은 전부 토큰(FG-002). */
.status-badge {
  transition:
    background-color 0.25s var(--ease-out),
    color 0.25s var(--ease-out),
    border-color 0.25s var(--ease-out);
}

@keyframes status-badge-breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.62;
  }
}

@keyframes status-badge-attention {
  0%,
  100% {
    box-shadow: 0 0 0 0 var(--st-waiting_input-border);
  }
  50% {
    box-shadow: 0 0 0 4px var(--st-waiting_input-border);
  }
}

/* 진행 중 — 은은하게 */
.status-badge[data-tone="running"] {
  animation: status-badge-breathe 1.8s ease-in-out infinite;
}

/* 입력 대기 — 사람의 OTP 입력을 기다리는 유일한 상태. 눈에 띄어야 한다. */
.status-badge[data-tone="waiting_input"] {
  animation: status-badge-attention 1.2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .status-badge {
    transition: none;
  }

  .status-badge[data-tone="running"],
  .status-badge[data-tone="waiting_input"] {
    animation: none;
  }
}
```

- [ ] **Step 4: `.node-card` 의 잘못된 토큰을 고친다**

`app/web/frontend/styles/app.css:379-381` 이 `waiting_input` 에 이상징후 색을 쓰고 있다. P1 이 독립 톤을 만들었으므로 교정한다.

```css
.node-card.status-waiting_input {
    border-left-color: var(--st-waiting_input-solid);
}
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python3 -m pytest tests/test_reduced_motion_guard.py -q`
Expected: PASS

Run: `npm run build && python3 scripts/check_frontend_gates.py`
Expected: 둘 다 성공 (FG-002 — 새로 넣은 CSS 에 hex 0건)

- [ ] **Step 6: 육안 검증**

앱을 띄우고(`docs/INSTALL.md`) 진행 중인 Run 상세를 연다.

확인 항목:
- 실행 중 모듈 배지가 은은하게 숨쉬는가
- OTP 대기 상태에서 배지가 눈에 띄게 맥동하는가
- 상태가 바뀔 때 색이 튀지 않고 전이되는가
- **OS 설정에서 "동작 줄이기"를 켜면 움직임이 멈추는가** (Windows: 설정 → 접근성 → 시각 효과 → 애니메이션 효과 끄기)
- 완료된 실패 Run 을 열었을 때 배지가 **빨강/amber 이고 한국어**인가 (Task 2 결과 재확인)
- 브라우저 콘솔 에러 0건

- [ ] **Step 7: 커밋**

```bash
git add app/web/frontend/components/status-badge/styles.css app/web/frontend/styles/app.css \
        tests/test_reduced_motion_guard.py
git commit -m "feat(web): 상태 배지 점등 + waiting_input 맥동 (reduced-motion 존중)"
```

---

## Task 6: 치유 이력 인라인

**Files:**
- Modify: `app/contexts/healing/service.py:195`
- Modify: `app/api/routes_dashboard.py` (`/runs/{run_id}`)
- Modify: `app/web/templates/run.html`
- Test: `tests/test_run_detail_healing.py`

**Interfaces:**
- Consumes: Task 2 의 템플릿 구조
- Produces:
  - `HealingService.list_events(*, allowed_system_codes=None, system_code=None, run_id=None, limit=…)`
  - Run 상세 템플릿 컨텍스트에 `healing_by_module: dict[str, list[dict]]`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_run_detail_healing.py`:

```python
"""Run 상세의 치유 이력 인라인 표시.

recovered 배지는 "재시도 후 통과"만 알린다. 무엇이 깨져서 무엇으로 고쳐졌는지는
Run 상세에 전혀 없었고 /self-healing 으로 따로 가야 보였다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.healing.models import HealingAction, HealingEvent


def _event(*, run_id: str, module_id: str, action: HealingAction, event_id: str) -> HealingEvent:
    return HealingEvent(
        event_id=event_id,
        run_id=run_id,
        module_id=module_id,
        system_code="HOM",
        module_name="로그인",
        broken_selector="#login-btn",
        healed_selector="[data-testid=login]",
        action=action,
        retry_succeeded=action is HealingAction.AUTO_HEALED,
        created_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )


class _StubEventStore:
    def __init__(self, events: list[HealingEvent]) -> None:
        self._events = events

    async def list(self, limit: int = 500) -> list[HealingEvent]:
        return self._events[:limit]


class _StubPatchStore:
    async def list(self) -> list:
        return []


@pytest.mark.asyncio
async def test_list_events_filters_by_run_id(healing_service_factory) -> None:
    """다른 Run 의 이벤트가 섞이지 않는다."""
    service = healing_service_factory(
        [
            _event(run_id="run1", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e1"),
            _event(run_id="run2", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e2"),
        ]
    )
    result = await service.list_events(run_id="run1")
    assert [item["event_id"] for item in result["items"]] == ["e1"]


@pytest.mark.asyncio
async def test_list_events_without_run_id_returns_all(healing_service_factory) -> None:
    """기존 호출자는 동작이 바뀌지 않는다."""
    service = healing_service_factory(
        [
            _event(run_id="run1", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e1"),
            _event(run_id="run2", module_id="m1", action=HealingAction.AUTO_HEALED, event_id="e2"),
        ]
    )
    result = await service.list_events()
    assert {item["event_id"] for item in result["items"]} == {"e1", "e2"}
```

픽스처를 같은 파일 안에 둔다. `HealingService.__init__` 은 `(event_store, policy_store, patch_store, registry, *, repo_root=".")` 이다(`app/contexts/healing/service.py:61`). `list_events` 는 이벤트 스토어와 레지스트리(시스템 이름 해석)만 쓰므로 나머지는 최소 스텁으로 채운다.

```python
from app.contexts.healing.service import HealingService


class _StubPolicyStore:
    async def get(self, system_code: str):
        return None

    async def list(self):
        return []


class _StubRegistry:
    def list_systems(self):
        from types import SimpleNamespace

        return [SimpleNamespace(system_code="HOM", name="대표홈")]


@pytest.fixture()
def healing_service_factory(tmp_path):
    def _make(events: list[HealingEvent]) -> HealingService:
        return HealingService(
            _StubEventStore(events),
            _StubPolicyStore(),
            _StubPatchStore(),
            _StubRegistry(),
            repo_root=tmp_path,
        )

    return _make
```

`_StubRegistry.list_systems()` 가 필요한 이유: `list_events` 가 `self._system_name(code)` 로 각 이벤트에 `system_name` 을 붙인다. 스텁이 비어 있으면 이름 해석이 빈 문자열이 되지만 테스트는 `event_id` 만 보므로 무해하다 — 그래도 실제 경로를 타도록 항목 하나를 넣는다.

`HealingService` 의 실제 인자 이름이 다르면 즉시 `TypeError` 로 드러난다. 그때는 `app/contexts/healing/service.py:61` 을 읽어 맞춘다.

렌더 테스트는 Step 5 에서 추가한다(템플릿 변경 후).

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_run_detail_healing.py -q`
Expected: FAIL — `list_events() got an unexpected keyword argument 'run_id'`

- [ ] **Step 3: `run_id` 필터를 추가한다**

`app/contexts/healing/service.py` 의 `list_events` 시그니처와 본문을 고친다:

```python
    async def list_events(
        self,
        *,
        allowed_system_codes: list[str] | None = None,
        system_code: str | None = None,
        run_id: str | None = None,
        limit: int = _EVENT_LIST_LIMIT,
    ) -> dict[str, Any]:
        events = self._scoped(await self._event_store.list(limit=limit), allowed_system_codes)
        if system_code:
            events = [e for e in events if e.system_code == system_code]
        if run_id:
            events = [e for e in events if e.run_id == run_id]
```

이후 본문(`heal_counts` 계산부터)은 그대로 둔다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_run_detail_healing.py -q`
Expected: PASS

Run: `python3 -m pytest tests/test_healing_service.py -q`
Expected: PASS — 기본 인자가 `None` 이라 기존 호출자 무영향

- [ ] **Step 5: Run 상세가 치유 이벤트를 함께 조회하게 한다**

`app/api/routes_dashboard.py` 의 `/runs/{run_id}` 핸들러(322행)에 `healing` 의존성을 추가하고 컨텍스트를 채운다:

```python
@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_dashboard(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_queries: RunQueries = Depends(get_run_queries),
    healing: HealingService = Depends(get_healing_service),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        run = await run_queries.get_run_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    healing_payload = await healing.list_events(allowed_system_codes=allowed, run_id=run_id)
    healing_by_module: dict[str, list[dict]] = {}
    for item in healing_payload["items"]:
        # NO_CANDIDATE 는 복구되지 않은 시도다 — 화면에 표시하지 않는다(설계 §3.5).
        if item["action"] == "NO_CANDIDATE":
            continue
        healing_by_module.setdefault(item["module_id"], []).append(item)

    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "run": run,
            "current_user": current_user,
            "healing_by_module": healing_by_module,
        },
    )
```

import 추가: `from app.api.dependencies import get_healing_service` 와 TYPE_CHECKING 하위 `from app.contexts.healing.service import HealingService`.

**기존 테스트 영향:** `tests/test_run_detail_recovery_badge.py` 와 Task 2 의 `tests/test_run_detail_status_badge.py` 가 `get_healing_service` 를 오버라이드하지 않아 실패한다. 두 파일의 `_build_client`/`_html` 에 다음을 추가한다:

```text
    class _NoHealing:
        async def list_events(self, **kwargs):
            return {"items": [], "systems": []}

    app.dependency_overrides[get_healing_service] = lambda: _NoHealing()
```

- [ ] **Step 6: 템플릿에 한 줄을 추가한다**

`app/web/templates/run.html` 의 `recovered` 배지 블록 **바로 아래**에 삽입한다:

```jinja
            {% set heals = healing_by_module.get(module.module_id, []) %}
            {% if heals %}
            <p class="mt-2 text-xs text-violet-700">
              🔧 셀렉터 {{ heals|length }}건
              {%- if heals[0].action == 'AUTO_HEALED' %} 자동 복구{% else %} 제안됨{% endif %} ·
              <code class="font-mono">{{ heals[0].broken_selector }}</code> →
              <code class="font-mono">{{ heals[0].healed_selector }}</code> ·
              <a href="/self-healing#patches" class="font-medium underline">상세</a>
            </p>
            {% endif %}
```

**FG-006 주의:** 위 마크업은 `text-violet-700` 을 단독으로 쓴다(배경+전경 쌍이 아님) — FG-006 의 탐지 정규식은 `bg-… text-…` 쌍만 잡으므로 걸리지 않는다. `bg-violet-50 text-violet-700` 처럼 쌍으로 쓰면 게이트가 막으므로, 배경이 필요하면 컴포넌트로 빼야 한다.

- [ ] **Step 7: 렌더 테스트를 추가한다**

`tests/test_run_detail_healing.py` 에 추가한다. `_html()` 헬퍼는 Task 2 의 `tests/test_run_detail_status_badge.py` 와 같은 구조이며, `get_healing_service` 를 실제 페이로드로 오버라이드한다:

```python
def _html_with_heals(items: list[dict]) -> str:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import routes_dashboard
    from app.api.dependencies import get_healing_service, get_run_queries
    from app.contexts.identity.dependencies import get_current_user
    from app.contexts.identity.models import User
    from app.contexts.run.views.view import RunView
    from app.core.enums import ModuleStatus, RunStatus
    from app.core.run_models import RunModule

    run = RunView(
        run_id="run1",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PASSED,
        status_label="정상",
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="m1", name="로그인", group="인증", order=1, status=ModuleStatus.PASSED
            )
        ],
    )

    class _Queries:
        async def get_run_detail(self, run_id: str) -> RunView:
            return run

    class _Healing:
        async def list_events(self, **kwargs):
            return {"items": items, "systems": []}

    app = FastAPI()
    app.include_router(routes_dashboard.router)
    app.dependency_overrides[get_run_queries] = lambda: _Queries()
    app.dependency_overrides[get_healing_service] = lambda: _Healing()
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="u1",
        email="t@t.local",
        name="t",
        role="admin",
        hashed_password="x",
        created_at=datetime.now(UTC),
    )
    with TestClient(app) as client:
        response = client.get("/runs/run1")
        assert response.status_code == 200, response.text
        return response.text


def _item(action: str) -> dict:
    return {
        "event_id": "e1",
        "run_id": "run1",
        "module_id": "m1",
        "system_code": "HOM",
        "module_name": "로그인",
        "broken_selector": "#login-btn",
        "healed_selector": "[data-testid=login]",
        "action": action,
        "heal_count": 1,
    }


def test_auto_healed_event_is_shown() -> None:
    html = _html_with_heals([_item("AUTO_HEALED")])
    assert "자동 복구" in html
    assert "#login-btn" in html
    assert "/self-healing#patches" in html


def test_suggested_event_is_labelled_as_suggestion() -> None:
    html = _html_with_heals([_item("SUGGESTED")])
    assert "제안됨" in html


def test_no_candidate_event_is_not_shown() -> None:
    """복구되지 않은 시도는 화면에 올리지 않는다(설계 §3.5)."""
    html = _html_with_heals([_item("NO_CANDIDATE")])
    assert "#login-btn" not in html


def test_module_without_heals_shows_nothing() -> None:
    html = _html_with_heals([])
    assert "셀렉터" not in html
```

- [ ] **Step 8: 통과를 확인한다**

Run: `python3 -m pytest tests/test_run_detail_healing.py tests/test_run_detail_recovery_badge.py tests/test_run_detail_status_badge.py -q`
Expected: PASS

- [ ] **Step 9: 전체 검증**

Run: `python3 -m pytest tests/ -q`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `npm run build && npm run typecheck && npm run lint && npm run test`
Expected: 전부 통과

- [ ] **Step 10: 커밋**

```bash
git add app/contexts/healing/service.py app/api/routes_dashboard.py \
        app/web/templates/run.html tests/
git commit -m "feat(web): Run 상세에 치유 이력 인라인 표시 + list_events run_id 필터"
```

---

## 완료 기준 (P3-1 DoD)

- [ ] `grep -n "status_pill" app/web/templates/run.html app/web/templates/suite.html` → 출력 없음
- [ ] `python3 scripts/check_frontend_gates.py` → 통과 (FG-001~006)
- [ ] `python3 -m pytest tests/ -q` → 전부 통과
- [ ] `python3 scripts/ci/run_all_gates.py --profile full` → 전 게이트 통과
- [ ] `npm run build && npm run typecheck && npm run lint && npm run test` → 전부 통과
- [ ] **완료된 `ERROR` Run 을 열면 배지가 빨강 + "점검실패"** (버그 1·2 해소)
- [ ] 레거시 `FAILED` 모듈 배지가 amber + "이상징후" (버그 3 해소)
- [ ] 실행 중 모듈 배지가 은은히 숨쉬고, OTP 대기 배지가 눈에 띄게 맥동
- [ ] OS "동작 줄이기" 설정에서 움직임 정지
- [ ] 치유가 발생한 모듈에 셀렉터 before→after 와 `/self-healing#patches` 링크 표시
- [ ] `recovered` 배지·AI 분석 패널이 이전과 동일하게 동작 (재작성하지 않았음)
- [ ] `app/web/static/app.js` 변경이 열거된 6곳에 한정 (`git diff main -- app/web/static/app.js` 를 읽어 확인)
- [ ] **실행 중인 Run 에서 "실행 취소" 버튼이 보이고, 완료된 Run 에서 "동일 조건으로 재실행"이 보인다** (배지 한국어화가 버튼 로직을 깨지 않았음)

---

## P3-1 이후

다음 조각은 **Step 5 — 상황판 `/wall`** 이다. 이 계획이 남기는 자산:

- `status_badge_view()` — 상황판도 같은 톤·라벨 해석을 쓴다
- `status-badge` 매크로의 `role` 인자 — 상황판 대형 모드에서 재사용
- 점등 CSS — 상황판이 "살아있는 화면"으로 보이는 핵심
- FG-006 — 상황판 템플릿이 처음부터 게이트 안에서 태어난다

**세 번째로 이월된 항목:** 자동 화면 스모크 테스트(콘솔 에러 0). P1·P2·P3-1 모두 인증 필요 경로뿐이어서 미뤘다. Step 5 의 `/wall` 이 인증 불필요 읽기 전용 경로를 만들 때 **반드시** 붙인다.
