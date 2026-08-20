# 프론트엔드 고도화 P3-2 (상황판 /wall) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 없이 접근하는 사무실 상시 디스플레이용 상황판 `/wall` 을 만든다 — 단일 화면에서 상태에 따라 지배 요소가 바뀌고, OTP 대기가 실패보다 우선한다.

**Architecture:** 비인증 GET 라우트 2개(페이지·프래그먼트)만 노출하고 JSON API 를 만들지 않는다. 데이터는 P2 의 `DailySummaryQueries` 를 그대로 재사용하며, 지배 요소 판정은 순수 함수 `build_wall_view` 가 담당한다. 화면은 `base.html` 을 상속하지 않는 독립 레이아웃이고, P1 이 설계한 다중 Vite 엔트리의 첫 소비자가 된다.

**Tech Stack:** Python 3.13 · FastAPI · Jinja2 · pytest · Vite (다중 엔트리) · htmx · CSS

**Spec:** `docs/superpowers/specs/2026-08-20-frontend-elevation-p3-2-wall-design.md`

## Global Constraints

- UI·로그·README 문자열은 **한국어**. (`AGENTS.md`)
- **라이트 단일 팔레트.** 다크모드·테마 분기 금지.
- **톤 축은 정확히 9개**: `passed` `anomaly` `error` `running` `waiting_input` `blocked` `skipped` `cancelled` `pending`
- `app/web/frontend/**` 내 하드코딩 hex 금지 (FG-002). 색은 토큰만.
- 엔트리·컴포넌트 파일 **400줄 상한** (FG-004).
- **`wall.html` 을 `FG006_ALLOWLIST` 에 추가하지 않는다.** 상태 표현은 `status_badge_view` 를 경유한다.
- **`prefers-reduced-motion: reduce` 에서 모든 맥동 정지.**
- **`/wall` 은 비인증.** `get_current_user` 의존을 걸지 않는다. **GET 전용** — POST/PUT/DELETE 를 만들지 않고 페이지에 링크·버튼을 두지 않는다.
- **`my_seconds` 를 상황판 렌더에 쓰지 않는다.** 값이 0 인 것과 무관하게 사용 자체를 금지한다.
- **`dashboard.js` 의 밀도 시스템을 재사용하지 않는다.** (`syncRowPartition`·`fitAndPartition`·`data-density`)
- **`_macros.html`·`zone_b_matrix.html` 을 임포트하지 않는다.** (`_macros.html` 은 FG006 allowlist 파일 — 알려진 위반을 끌어오지 않는다)
- 새 CI 게이트를 등록하지 않는다.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full` + `npm run build && npm run typecheck && npm run lint && npm run test`.

---

## 선행 의존

이 브랜치는 **PR #133(P3-1) 위에 쌓여 있다.** 다음 자산을 소비한다:

| 자산 | 위치 |
| --- | --- |
| `status_badge_view(status) -> StatusBadgeView(tone, label)` | `app/web/status_view.py` |
| `status_badge(tone, label, size, role, elem_id, status_value)` 매크로 | `app/web/frontend/components/status-badge/macro.jinja` |
| 점등 CSS + `prefers-reduced-motion` 가드 | `app/web/frontend/components/status-badge/styles.css` |
| FG-006 (구조 탐지) | `scripts/check_frontend_gates.py` |

#133 이 병합되면 `main` 으로 리베이스한다.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `app/core/settings.py` (수정) | `wall_enabled: bool` 필드 |
| `.env.example` · `docs/INSTALL.md` (수정) | `E2E_WALL_ENABLED` 문서화 (`docs_consistency` 게이트 요구) |
| `app/orchestrator/queries/daily_summary_queries.py` (수정) | `summary["systems"]` 패스스루 |
| `app/contexts/insights/application/wall_view.py` (신규) | `build_wall_view()` — 지배 요소 판정 + 시스템 톤 축약. I/O 없음 |
| `app/api/routes_wall.py` (신규) | 비인증 GET 2개. 인증 라우터와 물리적으로 분리 |
| `app/main.py` (수정) | `wall_router` 등록 |
| `app/web/templates/wall.html` (신규) | 독립 레이아웃 (base.html 미상속) |
| `app/web/templates/wall_fragment.html` (신규) | 갱신 대상 본문 (페이지가 include, htmx 가 재요청) |
| `app/web/frontend/entries/wall.ts` (신규) | 두 번째 Vite 엔트리 — htmx + wall.css + 폴링 |
| `app/web/frontend/styles/wall.css` (신규) | 대형 스케일링·독립 레이아웃 |
| `vite.config.ts` (수정) | `wall` 엔트리 추가 |
| `app/web/frontend/components/kpi-card/macro.jinja` (수정) | `size` 인자 추가 |
| `app/web/frontend/components/kpi-card/styles.css` (수정) | `data-size="lg"` 분기 |
| `scripts/check_wall_console.py` (신규) | 수동 Playwright 콘솔 검사 (CI 아님) |
| `tests/test_wall_view.py` (신규) | 지배 요소 판정 5경로 + OTP 우선 |
| `tests/test_wall_http.py` (신규) | 비인증 200 · 스위치 404 · 프라이버시 · 프래그먼트 |
| `tests/frontend/test_wall_assets.py` (신규) | 다중 엔트리 · reduced-motion 가드 |

---

## Task 1: `E2E_WALL_ENABLED` 설정과 문서

**Files:**
- Modify: `app/core/settings.py`
- Modify: `.env.example`
- Modify: `docs/INSTALL.md:62-63` 부근 (env 표)
- Test: `tests/test_wall_settings.py`

**Interfaces:**
- Produces: `E2ESettings.wall_enabled: bool` (기본 `True`, alias `E2E_WALL_ENABLED`)

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_wall_settings.py`:

```python
"""상황판 차단 스위치.

/wall 은 비인증 공개 라우트다(설계 D1). 앱이 사내망 밖으로 노출되는 상황에서
즉시 끌 수 있어야 한다(D2). 기본값은 true 다 — false 로 두면 배포 때 켜는 것을
잊어 "왜 안 되지" 사고가 난다.
"""

from app.core.settings import E2ESettings


def test_wall_is_enabled_by_default():
    assert E2ESettings().wall_enabled is True


def test_wall_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("E2E_WALL_ENABLED", "false")
    assert E2ESettings().wall_enabled is False
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_wall_settings.py -q`
Expected: FAIL — `AttributeError: 'E2ESettings' object has no attribute 'wall_enabled'`

- [ ] **Step 3: 설정 필드를 추가한다**

`app/core/settings.py` 의 `run_retention_enabled` 선언 아래에 추가한다(같은 `bool = Field(...)` 형식):

```python
    # 상황판(/wall)은 로그인 없이 열리는 공개 읽기 라우트다(P3-2 설계 D1).
    # 사내망 전제이므로 기본은 켜 두고, 앱이 외부에서 접근 가능한 배포에서는
    # false 로 즉시 차단한다. false 면 /wall·/wall/fragment 가 404 다.
    wall_enabled: bool = Field(default=True, validation_alias="E2E_WALL_ENABLED")
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_wall_settings.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: `.env.example` 에 문서화한다**

`E2E_RUN_RETENTION_ENABLED` 블록 아래에 추가한다:

```dotenv
# 상황판(/wall) 공개 여부. 로그인 없이 열리는 읽기 전용 화면이다 —
# 사무실 상시 디스플레이가 7일 JWT 만료로 로그인 폼을 띄우는 것을 피하기 위해
# 비인증으로 둔다. 앱이 사내망 밖에서 접근 가능한 배포에서는 false 로 끈다.
E2E_WALL_ENABLED=true
```

- [ ] **Step 6: `docs/INSTALL.md` env 표에 추가한다**

`| E2E_RUN_RETENTION_ENABLED / ... | 실패 Run 자동 삭제 |` 행 아래에 추가:

```markdown
| `E2E_WALL_ENABLED` | 상황판 `/wall` 공개 여부(비인증 읽기 전용). 외부 접근 가능한 배포에서는 `false` |
```

- [ ] **Step 7: 문서 정합성 게이트를 확인한다**

Run: `python3 scripts/ci/run_all_gates.py --gate docs_consistency`
Expected: `{"passed": true, ...}`

이 게이트는 **코드가 읽는 환경변수가 `docs/INSTALL.md` 또는 `.env.example` 에 문서화되어 있는지** 검사한다. 실패하면 Step 5/6 중 하나가 빠진 것이다.

- [ ] **Step 8: 커밋**

```bash
git add app/core/settings.py .env.example docs/INSTALL.md tests/test_wall_settings.py
git commit -m "feat(config): 상황판 차단 스위치 E2E_WALL_ENABLED 추가"
```

---

## Task 2: `build_wall_view` — 지배 요소 판정

**Files:**
- Modify: `app/orchestrator/queries/daily_summary_queries.py:56-59`
- Create: `app/contexts/insights/application/wall_view.py`
- Test: `tests/test_wall_view.py`

**Interfaces:**
- Consumes: `get_daily_summary()` 반환 dict — `cards` · `totals` · `date_label` · `generated_at` · `attention` (+ 이 태스크가 추가하는 `systems`)
- Produces:
  ```python
  def build_wall_view(summary: dict[str, Any]) -> dict[str, Any]
  # → {
  #     "dominant": {"kind": str, "tone": str, "headline": str, "detail": str},
  #     "systems": [{"code": str, "name": str, "tone": str, "passed": int, "total": int}],
  #     "strip": [card, ...],          # cards 중 pass_rate 를 제외한 3장
  #     "date_label": str,
  #     "generated_at": str,
  #   }
  ```
  `dominant.kind` 는 정확히 `"waiting_input"` · `"error"` · `"anomaly"` · `"running"` · `"passed"` 중 하나.

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_wall_view.py`:

```python
"""상황판 지배 요소 판정.

상황판의 직분은 "지금 정상인가" 하나다. 이상이 있으면 몰라보기가 불가능해야 한다.
OTP 대기는 실패보다 우선한다 — 이미 끝난 실패보다 지금 막혀서 사람을 기다리는
Run 이 급하기 때문이다(설계 §3.3).
"""

from typing import Any

from app.contexts.insights.application.wall_view import build_wall_view

CARDS = [
    {
        "key": "pass_rate",
        "label": "통과율",
        "value": 94,
        "unit": "%",
        "period": "오늘",
        "note": "34/36 모듈 정상",
        "tone": "passed",
        "href": "",
        "estimated": False,
    },
    {
        "key": "self_healed",
        "label": "스스로 복구",
        "value": 7,
        "unit": "건",
        "period": "오늘",
        "note": "이번 달 누적 21건",
        "tone": "running",
        "href": "",
        "estimated": False,
    },
    {
        "key": "pending_patches",
        "label": "내 승인 대기",
        "value": 2,
        "unit": "건",
        "period": "패치",
        "note": "검토",
        "tone": "anomaly",
        "href": "",
        "estimated": False,
    },
    {
        "key": "savings",
        "label": "이번 달 절감",
        "value": 310,
        "unit": "h",
        "period": "이번 달",
        "note": "1,240회",
        "tone": "passed",
        "href": "",
        "estimated": True,
    },
]

SYSTEMS = [
    {
        "system_code": "HOM",
        "system_name": "대표홈",
        "module_total": 6,
        "pass_rate": 100,
        "counts": {
            "passed": 6,
            "anomaly": 0,
            "error": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 0,
        },
        "modules": [],
    },
    {
        "system_code": "FP",
        "system_name": "위촉서류",
        "module_total": 6,
        "pass_rate": 67,
        "counts": {
            "passed": 4,
            "anomaly": 2,
            "error": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 0,
        },
        "modules": [],
    },
]


def _summary(
    *,
    error: int = 0,
    anomaly: int = 0,
    running: int = 0,
    attention: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "cards": CARDS,
        "systems": SYSTEMS,
        "totals": {
            "modules": 36,
            "passed": 34,
            "pass_rate": 94,
            "error": error,
            "anomaly": anomaly,
            "running": running,
            "not_inspected": 0,
        },
        "attention": attention or [],
        "date_label": "2026-08-20",
        "generated_at": "2026-08-20T09:14:00+00:00",
    }


def _attention(tone: str, *, system_name: str = "HOM", module_name: str = "로그인") -> dict:
    return {
        "kind": "module",
        "system_code": "HOM",
        "system_name": system_name,
        "module_id": "m1",
        "module_name": module_name,
        "status_label": "입력 대기" if tone == "waiting_input" else "점검실패",
        "tone": tone,
        "run_id": "run1",
        "rank": 30,
    }


def test_all_clear_shows_passed_as_dominant():
    view = build_wall_view(_summary())
    assert view["dominant"]["kind"] == "passed"
    assert view["dominant"]["tone"] == "passed"
    assert "정상" in view["dominant"]["headline"]


def test_error_dominates_over_clear():
    view = build_wall_view(_summary(error=2, attention=[_attention("error")]))
    assert view["dominant"]["kind"] == "error"
    assert view["dominant"]["tone"] == "error"


def test_anomaly_dominates_when_no_error():
    view = build_wall_view(_summary(anomaly=2, attention=[_attention("anomaly")]))
    assert view["dominant"]["kind"] == "anomaly"


def test_error_beats_anomaly():
    view = build_wall_view(_summary(error=1, anomaly=3, attention=[_attention("error")]))
    assert view["dominant"]["kind"] == "error"


def test_running_dominates_when_nothing_wrong():
    view = build_wall_view(_summary(running=3))
    assert view["dominant"]["kind"] == "running"


def test_waiting_input_beats_error():
    """핵심 규칙 — 이미 끝난 실패보다 사람을 기다리는 Run 이 급하다."""
    view = build_wall_view(
        _summary(error=2, attention=[_attention("error"), _attention("waiting_input")])
    )
    assert view["dominant"]["kind"] == "waiting_input"
    assert view["dominant"]["tone"] == "waiting_input"


def test_waiting_input_found_anywhere_in_attention():
    """attention 은 rank 순 정렬이라 waiting_input 이 첫 항목이 아닐 수 있다."""
    attention = [_attention("error"), _attention("anomaly"), _attention("waiting_input")]
    view = build_wall_view(_summary(error=1, anomaly=1, attention=attention))
    assert view["dominant"]["kind"] == "waiting_input"


def test_dominant_detail_names_the_system_and_module():
    view = build_wall_view(
        _summary(error=1, attention=[_attention("error", system_name="FP", module_name="첨부")])
    )
    assert "FP" in view["dominant"]["detail"]
    assert "첨부" in view["dominant"]["detail"]


def test_strip_excludes_pass_rate_card():
    """통과율은 히어로가 흡수하므로 스트립에 두지 않는다(설계 §3.5)."""
    view = build_wall_view(_summary())
    assert [c["key"] for c in view["strip"]] == [
        "self_healed",
        "pending_patches",
        "savings",
    ]


def test_systems_are_reduced_to_wall_shape():
    view = build_wall_view(_summary())
    assert view["systems"] == [
        {"code": "HOM", "name": "대표홈", "tone": "passed", "passed": 6, "total": 6},
        {"code": "FP", "name": "위촉서류", "tone": "anomaly", "passed": 4, "total": 6},
    ]


def test_system_tone_takes_the_worst_bucket():
    systems = [
        {
            "system_code": "X",
            "system_name": "X",
            "module_total": 4,
            "pass_rate": 25,
            "counts": {
                "passed": 1,
                "anomaly": 1,
                "error": 1,
                "running": 1,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
        }
    ]
    summary = _summary()
    summary["systems"] = systems
    view = build_wall_view(summary)
    assert view["systems"][0]["tone"] == "error"


def test_not_inspected_system_is_pending():
    systems = [
        {
            "system_code": "Y",
            "system_name": "Y",
            "module_total": 3,
            "pass_rate": 0,
            "counts": {
                "passed": 0,
                "anomaly": 0,
                "error": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 3,
            },
            "modules": [],
        }
    ]
    summary = _summary()
    summary["systems"] = systems
    view = build_wall_view(summary)
    assert view["systems"][0]["tone"] == "pending"


def test_view_never_carries_my_seconds():
    """프라이버시 계약 — 상황판은 개인 기여분을 쓰지 않는다."""
    view = build_wall_view(_summary())
    assert "my_seconds" not in str(view)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_wall_view.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.contexts.insights.application.wall_view'`

- [ ] **Step 3: `systems` 패스스루를 추가한다**

`app/orchestrator/queries/daily_summary_queries.py` 의 패스스루 블록에 한 줄 추가한다:

```python
        summary["attention"] = dashboard["attention"]
        # 상황판(P3-2)이 매트릭스를 그리는 데 쓴다. PII 없음(시스템·모듈 메타뿐).
        summary["systems"] = dashboard["systems"]
        return summary
```

**계약 변경 주의:** `/api/dashboard/daily/summary` 응답에 필드가 하나 늘어난다. 가산적 변경이며 `systems` 는 시스템 코드·이름·모듈 상태만 담아 PII 가 없다. P2 의 프라이버시 테스트(`tests/test_daily_summary_http.py::test_summary_response_has_no_user_identifiers`)가 계속 통과하는지 Step 5 에서 확인한다.

- [ ] **Step 4: `build_wall_view` 를 구현한다**

`app/contexts/insights/application/wall_view.py`:

```python
"""상황판 뷰 조립 — 지배 요소 판정 + 시스템 톤 축약.

I/O 없음. 라우트가 ``DailySummaryQueries.get_daily_summary()`` 결과를 넘겨 호출한다
(``build_daily_summary`` 와 같은 순수 빌더 패턴).

상황판의 직분은 "지금 정상인가" 하나다. 따라서 화면의 지배 요소는 상태에 따라
교체되며, OTP 대기가 실패보다 우선한다 — 이미 끝난 실패보다 지금 막혀서 사람을
기다리는 Run 이 급하기 때문이다.
"""

from __future__ import annotations

from typing import Any

# 시스템 블록 색을 정하는 최악 버킷 우선순위. daily_dashboard._ATTENTION_RANK 와
# 같은 사상이지만 상황판 전용이며 공유하지 않는다(그쪽을 바꾸면 일간 대시보드가 바뀐다).
_WORST_BUCKET_ORDER = ("error", "anomaly", "running", "other", "not_inspected")
_BUCKET_TO_TONE = {
    "error": "error",
    "anomaly": "anomaly",
    "running": "running",
    "other": "blocked",
    "not_inspected": "pending",
}

# 통과율은 히어로가 흡수하므로 성과 스트립에 두지 않는다(설계 §3.5).
_STRIP_EXCLUDED_CARD_KEYS = frozenset({"pass_rate"})


def _find_waiting_input(attention: list[dict[str, Any]]) -> dict[str, Any] | None:
    """attention 전체를 훑는다.

    attention 은 _ATTENTION_RANK(error 50 > anomaly 40 > running 30) 순으로 정렬되어
    있어 OTP 대기가 첫 항목이 아닐 수 있다. 공유 랭크를 바꾸지 않고 여기서 직접 찾는다.
    """
    return next((item for item in attention if item.get("tone") == "waiting_input"), None)


def _detail_of(item: dict[str, Any] | None) -> str:
    if item is None:
        return ""
    system = item.get("system_name") or item.get("system_code") or ""
    module = item.get("module_name")
    return f"{system} · {module}" if module else str(system)


def _dominant(totals: dict[str, Any], attention: list[dict[str, Any]]) -> dict[str, Any]:
    waiting = _find_waiting_input(attention)
    if waiting is not None:
        return {
            "kind": "waiting_input",
            "tone": "waiting_input",
            "headline": "OTP 입력 대기",
            "detail": _detail_of(waiting),
        }

    def _first(tone: str) -> dict[str, Any] | None:
        return next((item for item in attention if item.get("tone") == tone), None)

    if int(totals.get("error", 0) or 0) > 0:
        return {
            "kind": "error",
            "tone": "error",
            "headline": "점검실패",
            "detail": _detail_of(_first("error")),
        }
    if int(totals.get("anomaly", 0) or 0) > 0:
        return {
            "kind": "anomaly",
            "tone": "anomaly",
            "headline": "이상징후",
            "detail": _detail_of(_first("anomaly")),
        }
    if int(totals.get("running", 0) or 0) > 0:
        running = int(totals["running"])
        return {
            "kind": "running",
            "tone": "running",
            "headline": "점검 진행 중",
            "detail": f"{running}개 모듈",
        }
    passed = int(totals.get("passed", 0) or 0)
    modules = int(totals.get("modules", 0) or 0)
    return {
        "kind": "passed",
        "tone": "passed",
        "headline": "정상",
        "detail": f"{passed}/{modules} 모듈",
    }


def _system_tone(counts: dict[str, Any]) -> str:
    for bucket in _WORST_BUCKET_ORDER:
        if int(counts.get(bucket, 0) or 0) > 0:
            return _BUCKET_TO_TONE[bucket]
    return "passed"


def build_wall_view(summary: dict[str, Any]) -> dict[str, Any]:
    """일간 요약 → 상황판 뷰. my_seconds 를 쓰지 않는다(프라이버시 계약)."""
    totals = summary.get("totals", {})
    attention = summary.get("attention", []) or []
    return {
        "dominant": _dominant(totals, attention),
        "systems": [
            {
                "code": system["system_code"],
                "name": system["system_name"],
                "tone": _system_tone(system.get("counts", {})),
                "passed": int(system.get("counts", {}).get("passed", 0) or 0),
                "total": int(system.get("module_total", 0) or 0),
            }
            for system in summary.get("systems", [])
        ],
        "strip": [
            card
            for card in summary.get("cards", [])
            if card.get("key") not in _STRIP_EXCLUDED_CARD_KEYS
        ],
        "date_label": summary.get("date_label", ""),
        "generated_at": summary.get("generated_at", ""),
    }
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python3 -m pytest tests/test_wall_view.py -q`
Expected: PASS (13 passed)

Run: `python3 -m pytest tests/test_daily_summary.py tests/test_daily_summary_http.py -q`
Expected: PASS — `systems` 패스스루가 P2 계약(특히 프라이버시 테스트)을 깨지 않아야 한다

- [ ] **Step 6: 아키텍처 게이트를 확인한다**

Run: `python3 scripts/check_architecture_gates.py && python3 -m importlinter.cli lint`
Expected: 둘 다 통과 — `wall_view.py` 는 I/O 를 임포트하지 않는 순수 모듈이다

- [ ] **Step 7: 커밋**

```bash
git add app/contexts/insights/application/wall_view.py \
        app/orchestrator/queries/daily_summary_queries.py tests/test_wall_view.py
git commit -m "feat(insights): 상황판 뷰 조립기(build_wall_view) 추가 — OTP 대기 우선 판정"
```

---

## Task 3: 두 번째 Vite 엔트리와 대형 스케일링

**Files:**
- Modify: `vite.config.ts:16-20`
- Create: `app/web/frontend/entries/wall.ts`
- Create: `app/web/frontend/styles/wall.css`
- Test: `tests/frontend/test_wall_assets.py`

**Interfaces:**
- Produces: manifest 엔트리 키 `entries/wall.ts`. `wall.css` 가 `main` 번들에 섞이지 않는다.
- **다음 태스크가 이것을 요구한다**: Task 4 의 `wall.html` 이 `asset_styles("entries/wall.ts")` 로 참조하므로, 이 태스크의 `npm run build` 가 먼저 성공해야 그 템플릿이 렌더된다.

- [ ] **Step 1: 테스트를 작성한다**

`tests/frontend/test_wall_assets.py`:

```python
"""상황판 자산 — 다중 엔트리와 접근성 가드.

P1 §3.2 가 페이지별 Vite 엔트리 구조를 설계했지만 소비자가 없어 검증되지 않았다.
상황판이 첫 소비자다 — 동작하지 않으면 P1 설계에 결함이 있다는 뜻이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

MANIFEST = Path("app/web/static/dist/.vite/manifest.json")
WALL_CSS = Path("app/web/frontend/styles/wall.css")


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.exists(), f"{MANIFEST} 가 없습니다. `npm run build` 를 먼저 실행하세요."
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_wall_entry_exists_in_manifest(manifest: dict) -> None:
    assert "entries/wall.ts" in manifest, sorted(manifest)


def test_wall_entry_has_its_own_css(manifest: dict) -> None:
    css = manifest["entries/wall.ts"].get("css") or []
    assert css, "상황판 엔트리에 CSS 산출물이 없습니다."


def test_main_bundle_does_not_carry_wall_styles(manifest: dict) -> None:
    """일반 페이지 번들에 상황판 전용 무게를 얹지 않는다(설계 §3.7)."""
    main_css = manifest["entries/main.ts"].get("css") or []
    for name in main_css:
        text = (Path("app/web/static/dist") / name).read_text(encoding="utf-8")
        assert ".wall-hero" not in text, f"{name} 에 상황판 스타일이 섞였습니다."


def test_wall_css_has_no_hardcoded_hex() -> None:
    """FG-002 — 색은 토큰만."""
    import re

    source = WALL_CSS.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)


def test_wall_css_guards_reduced_motion() -> None:
    source = WALL_CSS.read_text(encoding="utf-8")
    if "animation" not in source:
        pytest.skip("wall.css 에 움직임이 없다")
    assert "prefers-reduced-motion" in source
    start = source.index("prefers-reduced-motion")
    assert "animation: none" in source[start : start + 400]


def test_wall_css_is_nonscrolling() -> None:
    source = WALL_CSS.read_text(encoding="utf-8")
    assert "overflow: hidden" in source
    assert "100dvh" in source
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_wall_assets.py -q`
Expected: FAIL — `entries/wall.ts` 가 manifest 에 없음

- [ ] **Step 3: Vite 에 엔트리를 추가한다**

`vite.config.ts` 의 `rollupOptions.input` 을 확장한다:

```ts
    rollupOptions: {
      input: {
        main: resolve(__dirname, "app/web/frontend/entries/main.ts"),
        // 상황판은 사이드바·Alpine·컴포넌트 TS 가 필요 없는 독립 화면이라
        // 별 엔트리로 둔다 — 일반 페이지 번들에 상황판 CSS 를 얹지 않기 위함.
        wall: resolve(__dirname, "app/web/frontend/entries/wall.ts"),
      },
    },
```

- [ ] **Step 4: 엔트리와 스타일을 만든다**

`app/web/frontend/entries/wall.ts`:

```ts
// 상황판 엔트리. Alpine·status-badge TS 를 싣지 않는다 — 조작이 없는 화면이다.
import "htmx.org";

import "../styles/wall.css";
```

`app/web/frontend/styles/wall.css`:

```css
/* 상황판 — 3~5m 거리에서 읽는 고정 디스플레이용.
   base.html 을 상속하지 않으므로 리셋부터 여기서 책임진다.
   색은 전부 P1 토큰(FG-002). dashboard.js 의 밀도 시스템은 쓰지 않는다. */
@import "./primitives.css";
@import "./tokens.generated.css";

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body.wall {
  overflow: hidden;
  height: 100dvh;
  background: var(--pl-bg);
  color: var(--pl-text);
  font-family: "Pretendard Variable", Pretendard, "Noto Sans KR", sans-serif;
}

.wall-body {
  display: flex;
  height: 100dvh;
  flex-direction: column;
  justify-content: center;
  gap: 2vmin;
  padding: 4vmin;
  text-align: center;
}

/* 지배 요소 — 상태에 따라 색이 바뀐다. 크기는 vmin 기준이라 1080p·1440p·4K 에서
   비율이 유지된다. */
.wall-hero__headline {
  font-size: clamp(3rem, 14vmin, 14rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.02em;
}

.wall-hero__detail {
  margin-top: 1vmin;
  font-size: clamp(1rem, 4vmin, 4rem);
  color: var(--pl-text-muted);
}

.wall-hero[data-tone="passed"] .wall-hero__headline { color: var(--st-passed-text); }
.wall-hero[data-tone="anomaly"] .wall-hero__headline { color: var(--st-anomaly-text); }
.wall-hero[data-tone="error"] .wall-hero__headline { color: var(--st-error-text); }
.wall-hero[data-tone="running"] .wall-hero__headline { color: var(--st-running-text); }
.wall-hero[data-tone="waiting_input"] .wall-hero__headline { color: var(--st-waiting_input-text); }

.wall-meta {
  font-size: clamp(0.75rem, 2vmin, 2rem);
  color: var(--pl-text-subtle);
}

/* OTP 대기가 지배 요소일 때만 히어로 전체가 맥동한다 — 3~5m 거리에서 배지
   크기의 맥동은 보이지 않기 때문이다(설계 §3.10). */
@keyframes wall-attention {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

.wall-body[data-dominant="waiting_input"] .wall-hero {
  animation: wall-attention 1.4s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .wall-body[data-dominant="waiting_input"] .wall-hero {
    animation: none;
  }
}
```

- [ ] **Step 5: 빌드하고 통과를 확인한다**

Run: `npm run build`
Expected: 성공. 출력에 `wall-*.css` 와 `wall-*.js` 가 보인다

Run: `python3 -m pytest tests/frontend/test_wall_assets.py -q`
Expected: PASS (6 passed)

`test_main_bundle_does_not_carry_wall_styles` 가 실패하면 Vite 가 CSS 를 공통 청크로 합친 것이다. 그 경우 `build.cssCodeSplit`(기본 `true`)이 꺼져 있는지 확인한다.

- [ ] **Step 6: 게이트를 확인한다**

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과 (FG-001~006)

Run: `npm run typecheck && npm run lint`
Expected: 에러 0

- [ ] **Step 7: 커밋**

```bash
git add vite.config.ts app/web/frontend/entries/wall.ts \
        app/web/frontend/styles/wall.css tests/frontend/test_wall_assets.py
git commit -m "build(frontend): 상황판 Vite 엔트리 추가 — P1 다중 엔트리 구조 첫 검증"
```

---

## Task 4: 비인증 라우트와 화면

**Files:**
- Create: `app/api/routes_wall.py`
- Create: `app/web/templates/wall.html`
- Create: `app/web/templates/wall_fragment.html`
- Modify: `app/main.py:11-23` (import), `:90-101` 부근 (include_router)
- Test: `tests/test_wall_http.py`

**Interfaces:**
- Consumes: Task 1 의 `settings.wall_enabled`, Task 2 의 `build_wall_view`, Task 3 의 `entries/wall.ts` 빌드 산출물
- Produces: `GET /wall` · `GET /wall/fragment` (둘 다 비인증). `app.api.routes_wall.router`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_wall_http.py`:

```python
"""상황판 라우트 계약 — 비인증·차단 스위치·프라이버시.

/wall 은 로그인 없이 열린다(설계 D1). 7일 JWT 만료로 사무실 벽에 로그인 폼이
뜨는 것을 피하기 위한 결정이며, 대가로 E2E_WALL_ENABLED 차단 스위치를 둔다(D2).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_wall
from app.api.dependencies import get_daily_summary_queries

SUMMARY: dict[str, Any] = {
    "cards": [
        {
            "key": "pass_rate",
            "label": "통과율",
            "value": 94,
            "unit": "%",
            "period": "오늘",
            "note": "34/36 모듈 정상",
            "tone": "passed",
            "href": "",
            "estimated": False,
        },
        {
            "key": "self_healed",
            "label": "스스로 복구",
            "value": 7,
            "unit": "건",
            "period": "오늘",
            "note": "이번 달 누적 21건",
            "tone": "running",
            "href": "",
            "estimated": False,
        },
        {
            "key": "pending_patches",
            "label": "내 승인 대기",
            "value": 2,
            "unit": "건",
            "period": "패치",
            "note": "검토",
            "tone": "anomaly",
            "href": "",
            "estimated": False,
        },
        {
            "key": "savings",
            "label": "이번 달 절감",
            "value": 310,
            "unit": "h",
            "period": "이번 달",
            "note": "1,240회",
            "tone": "passed",
            "href": "",
            "estimated": True,
        },
    ],
    "systems": [
        {
            "system_code": "HOM",
            "system_name": "대표홈",
            "module_total": 6,
            "pass_rate": 100,
            "counts": {
                "passed": 6,
                "anomaly": 0,
                "error": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
        },
    ],
    "totals": {
        "modules": 36,
        "passed": 34,
        "pass_rate": 94,
        "error": 0,
        "anomaly": 0,
        "running": 0,
        "not_inspected": 0,
    },
    "attention": [],
    "date_label": "2026-08-20",
    "generated_at": "2026-08-20T09:14:00+00:00",
}


class _FakeSummaryQueries:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_daily_summary(self, *, user_id, allowed_system_codes, is_admin=False):
        self.calls.append(
            {"user_id": user_id, "allowed": allowed_system_codes, "is_admin": is_admin}
        )
        return SUMMARY


def _client(*, enabled: bool = True) -> tuple[TestClient, _FakeSummaryQueries]:
    app = FastAPI()
    app.include_router(routes_wall.router)
    fake = _FakeSummaryQueries()
    app.dependency_overrides[get_daily_summary_queries] = lambda: fake
    app.dependency_overrides[routes_wall.wall_enabled] = lambda: enabled
    return TestClient(app), fake


def test_wall_renders_without_authentication():
    """인증 쿠키 없이 200 이어야 한다 — 상황판의 존재 이유다."""
    client, _ = _client()
    with client:
        response = client.get("/wall")
    assert response.status_code == 200, response.text
    assert "정상" in response.text


def test_fragment_renders_without_authentication():
    client, _ = _client()
    with client:
        response = client.get("/wall/fragment")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", ["/wall", "/wall/fragment"])
def test_disabled_switch_returns_404(path: str):
    client, _ = _client(enabled=False)
    with client:
        assert client.get(path).status_code == 404


def test_queries_are_called_company_wide_and_anonymous():
    """user_id=None(내 기여분 무의미) · allowed=None(전사) · is_admin=False(링크 없음)."""
    client, fake = _client()
    with client:
        client.get("/wall")
    assert fake.calls == [{"user_id": None, "allowed": None, "is_admin": False}]


def test_response_has_no_user_identifiers():
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    for forbidden in ("my_seconds", "email", "user_id", "user_name"):
        assert forbidden not in body, forbidden


def test_page_has_no_interactive_controls():
    """조작하지 않는 화면 — 링크·버튼·폼을 두지 않는다(설계 §3.1)."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    for tag in ("<button", "<form", "<a "):
        assert tag not in body, tag


def test_page_does_not_import_dashboard_macros():
    """_macros.html 은 FG006 allowlist 파일이다 — 알려진 위반을 끌어오지 않는다."""
    from pathlib import Path

    source = Path("app/web/templates/wall.html").read_text(encoding="utf-8")
    fragment = Path("app/web/templates/wall_fragment.html").read_text(encoding="utf-8")
    for text in (source, fragment):
        assert "_macros.html" not in text
        assert "zone_b_matrix" not in text


def test_page_does_not_extend_base_layout():
    """사이드바·모바일 네비가 없는 독립 레이아웃이다(설계 §3.8)."""
    from pathlib import Path

    source = Path("app/web/templates/wall.html").read_text(encoding="utf-8")
    assert 'extends "base.html"' not in source
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_wall_http.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.routes_wall'`

- [ ] **Step 3: 라우터를 구현한다**

`app/api/routes_wall.py`:

```python
"""상황판(/wall) — 로그인 없이 열리는 읽기 전용 공개 화면.

사무실 상시 디스플레이용이다. 기존 인증을 쓸 수 없는 이유: JWT 가 7일 만료이고
비인증 상태에서 비-API 경로는 /login 으로 리다이렉트하므로, 키보드 없는 디스플레이는
주마다 재로그인해야 하고 만료 순간 사무실 벽에 로그인 폼이 뜬다.

설계 원칙:
- **GET 전용, 부수효과 없음.** POST 를 만들지 않고 페이지에 링크·버튼을 두지 않는다.
- **JSON API 를 만들지 않는다.** 비인증 표면을 최소화하기 위해 서버 렌더 HTML 만 낸다.
- **인증 라우터와 물리적으로 분리한다.** routes_dashboard.py 는 전부 인증 경로이므로,
  비인증 라우트를 섞으면 다음 사람이 의존을 실수로 빼거나 붙일 위험이 생긴다.
- E2E_WALL_ENABLED=false 면 404 — 앱이 사내망 밖에 노출될 때의 차단 스위치다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import get_daily_summary_queries
from app.contexts.insights.application.wall_view import build_wall_view
from app.core.settings import get_settings
from app.web.asset_manifest import TEMPLATE_SEARCH_DIRS, asset_css, asset_js
from app.web.status_view import status_badge_view

if TYPE_CHECKING:
    from app.orchestrator.queries.daily_summary_queries import DailySummaryQueries

router = APIRouter(tags=["wall"])
templates = Jinja2Templates(directory=TEMPLATE_SEARCH_DIRS)
templates.env.globals["asset_js"] = asset_js
templates.env.globals["asset_css"] = asset_css
templates.env.globals["status_badge_view"] = status_badge_view


def wall_enabled() -> bool:
    """차단 스위치. 의존성으로 두어 테스트가 override 할 수 있게 한다."""
    return get_settings().wall_enabled


async def _load_view(summary_queries: DailySummaryQueries) -> dict[str, Any]:
    summary = await summary_queries.get_daily_summary(
        user_id=None,  # 상황판에 "내 기여분"은 의미가 없다
        allowed_system_codes=None,  # 전사 상황판
        is_admin=False,  # 절감 카드의 관리자 링크를 비운다
    )
    return build_wall_view(summary)


def _require_enabled(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/wall", response_class=HTMLResponse)
async def wall_page(
    request: Request,
    enabled: bool = Depends(wall_enabled),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """상황판 전체 페이지. 인증하지 않는다."""
    _require_enabled(enabled)
    view = await _load_view(summary_queries)
    return templates.TemplateResponse(request, "wall.html", {"view": view, "request": request})


@router.get("/wall/fragment", response_class=HTMLResponse)
async def wall_fragment(
    request: Request,
    enabled: bool = Depends(wall_enabled),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """htmx 갱신 대상 본문. 인증하지 않는다."""
    _require_enabled(enabled)
    view = await _load_view(summary_queries)
    return templates.TemplateResponse(
        request, "wall_fragment.html", {"view": view, "request": request}
    )
```

- [ ] **Step 4: 템플릿 2개를 만든다 (히어로만 — 매트릭스·스트립은 Task 5)**

`app/web/templates/wall_fragment.html`:

```jinja
{# 상황판 본문 — htmx 가 15초마다 이 프래그먼트만 다시 받는다.
   조작하지 않는 화면이므로 링크·버튼·폼을 두지 않는다. #}
{% set d = view.dominant %}
<div id="wall-body" class="wall-body" data-dominant="{{ d.kind }}" data-tone="{{ d.tone }}">
  <section class="wall-hero" data-tone="{{ d.tone }}">
    <p class="wall-hero__headline">{{ d.headline }}</p>
    {% if d.detail %}<p class="wall-hero__detail">{{ d.detail }}</p>{% endif %}
  </section>
  <p class="wall-meta">{{ view.date_label }}{% if view.generated_at %} · 갱신 {{ view.generated_at[11:16] }}{% endif %}</p>
</div>
```

`app/web/templates/wall.html` — `base.html` 을 상속하지 않는 독립 문서:

```jinja
{# 상황판 독립 레이아웃. base.html 을 상속하지 않는다 — 사이드바·모바일 네비가
   없는 고정 디스플레이용이기 때문이다(설계 §3.8). #}
{% import "_assets.html" as assets %}<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>점검 상황판</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    {{ assets.asset_styles("entries/wall.ts") }}
</head>
<body class="wall">
    {% include "wall_fragment.html" %}
    {{ assets.asset_script("entries/wall.ts") }}
</body>
</html>
```

**주의:** `favicon.svg` 는 `/static/` 직접 참조이므로 FG-005 가 걸릴 수 있다. `FG005_ALLOWLIST` 에 `/static/favicon.svg` 가 이미 있는지 확인한다:

Run: `grep -n "favicon.svg" scripts/check_frontend_gates.py`
Expected: `FG005_ALLOWLIST` 안에 존재. 없으면 `<link rel="icon">` 줄을 삭제한다(상황판에 파비콘은 불필요하다).

- [ ] **Step 5: 라우터를 앱에 등록한다**

`app/main.py` 의 import 블록에 추가:

```python
from app.api.routes_wall import router as wall_router
```

`app.include_router(trigger_router)` 근처(다른 `include_router` 들과 같은 블록)에 추가:

```python
app.include_router(wall_router)
```

- [ ] **Step 6: 통과를 확인한다**

Run: `python3 -m pytest tests/test_wall_http.py -q`
Expected: PASS (9 passed)

`ManifestMissingError` 가 나면 Task 3 의 `npm run build` 를 건너뛴 것이다. `npm run build` 를 실행하고 다시 돌린다 — `asset_styles("entries/wall.ts")` 는 manifest 에 그 엔트리가 있어야 해석된다.

- [ ] **Step 7: 커밋**

```bash
git add app/api/routes_wall.py app/web/templates/wall.html \
        app/web/templates/wall_fragment.html app/main.py tests/test_wall_http.py
git commit -m "feat(api): 비인증 상황판 라우트 /wall 추가 + 차단 스위치"
```

---

## Task 5: 매트릭스와 성과 스트립

**Files:**
- Modify: `app/web/frontend/components/kpi-card/macro.jinja`
- Modify: `app/web/frontend/components/kpi-card/styles.css`
- Modify: `app/web/templates/wall_fragment.html`
- Modify: `app/web/frontend/styles/wall.css`
- Test: `tests/test_wall_http.py` (추가)

**Interfaces:**
- Consumes: Task 2 의 `view.systems` · `view.strip`
- Produces: `kpi_card(..., size="md")` 인자 추가. `size="lg"` 를 상황판이 쓴다.

- [ ] **Step 1: 테스트를 추가한다**

`tests/test_wall_http.py` 에 추가:

```python
def test_matrix_renders_every_system():
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert 'data-wall-system="HOM"' in body
    assert "대표홈" in body


def test_matrix_system_carries_its_tone():
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert 'data-tone="passed"' in body


def test_strip_renders_three_large_cards():
    """통과율은 히어로가 흡수 — 스트립은 3장(설계 §3.5)."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert body.count('class="kpi-card"') == 3
    assert body.count('data-size="lg"') == 3


def test_strip_has_no_pass_rate_card():
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert 'data-key="pass_rate"' not in body


def test_strip_cards_are_not_links():
    """조작하지 않는 화면 — href 가 있어도 링크로 렌더하지 않는다."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert "<a " not in body
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_wall_http.py -q -k "matrix or strip"`
Expected: FAIL — 매트릭스·스트립 마크업이 없음

- [ ] **Step 3: `kpi_card` 에 `size` 인자를 추가한다**

`app/web/frontend/components/kpi-card/macro.jinja` 의 `kpi_card` 시그니처와 여는 태그를 고친다:

```jinja
{% macro kpi_card(key, label, value, unit="", period="", note="", tone="pending", href="", estimated=false, size="md") -%}
{% set tag = "a" if href else "article" %}
<{{ tag }} class="kpi-card" data-tone="{{ tone }}" data-key="{{ key }}" data-size="{{ size }}"{% if href %} href="{{ href }}"{% endif %}>
```

나머지 본문은 그대로 둔다. `kpi_band(cards)` 는 `size` 를 넘기지 않으므로 기존 일간 현황은 `md` 로 동작이 유지된다.

- [ ] **Step 4: `data-size="lg"` 스타일을 추가한다**

`app/web/frontend/components/kpi-card/styles.css` 에 추가:

```css
/* 상황판 대형 모드 — 3~5m 거리용. 값은 vmin 기준으로 해상도에 비례한다. */
.kpi-card[data-size="lg"] {
  padding: 2vmin 2.5vmin;
  gap: 0.5vmin;
}

.kpi-card[data-size="lg"] .kpi-card__label {
  font-size: clamp(0.75rem, 1.8vmin, 1.75rem);
}

.kpi-card[data-size="lg"] .kpi-card__value {
  font-size: clamp(1.5rem, 5vmin, 5rem);
}

.kpi-card[data-size="lg"] .kpi-card__unit {
  font-size: clamp(0.75rem, 2vmin, 2rem);
}

.kpi-card[data-size="lg"] .kpi-card__note {
  font-size: clamp(0.625rem, 1.4vmin, 1.25rem);
}
```

- [ ] **Step 5: 프래그먼트에 매트릭스와 스트립을 추가한다**

`app/web/templates/wall_fragment.html` 전체를 교체한다:

```jinja
{# 상황판 본문 — htmx 가 15초마다 이 프래그먼트만 다시 받는다.
   조작하지 않는 화면이므로 링크·버튼·폼을 두지 않는다.
   _macros.html·zone_b_matrix.html 을 임포트하지 않는다(FG006 allowlist 파일이며
   dashboard.css 밀도 선택자에 묶여 있다 — 설계 §3.4.1). #}
{% import "components/kpi-card/macro.jinja" as kpi %}
{% set d = view.dominant %}
<div id="wall-body" class="wall-body" data-dominant="{{ d.kind }}" data-tone="{{ d.tone }}">
  <section class="wall-hero" data-tone="{{ d.tone }}">
    <p class="wall-hero__headline">{{ d.headline }}</p>
    {% if d.detail %}<p class="wall-hero__detail">{{ d.detail }}</p>{% endif %}
  </section>

  <section class="wall-matrix">
    {% for system in view.systems %}
    <div class="wall-sys" data-wall-system="{{ system.code }}" data-tone="{{ system.tone }}">
      <span class="wall-sys__code">{{ system.code }}</span>
      <span class="wall-sys__bar" aria-hidden="true"></span>
      <span class="wall-sys__count">{{ system.passed }}/{{ system.total }}</span>
      <span class="wall-sys__name">{{ system.name }}</span>
    </div>
    {% endfor %}
  </section>

  <section class="wall-strip">
    {% for card in view.strip %}
    {{ kpi.kpi_card(card.key, card.label, card.value, card.unit, card.period, card.note, card.tone, "", card.estimated, "lg") }}
    {% endfor %}
  </section>

  <p class="wall-meta">{{ view.date_label }}{% if view.generated_at %} · 갱신 {{ view.generated_at[11:16] }}{% endif %}</p>
</div>
```

**`href` 를 빈 문자열로 넘기는 이유**: 카드에 `href` 가 있으면 매크로가 `<a>` 로 렌더한다. 상황판은 조작하지 않는 화면이므로 링크를 만들지 않는다.

- [ ] **Step 6: 매트릭스·스트립 스타일을 추가한다**

`app/web/frontend/styles/wall.css` 의 `.wall-meta` 규칙 **앞**에 추가:

```css
.wall-matrix {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1.5vmin;
}

.wall-sys {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5vmin;
  padding: 1.5vmin 1vmin;
  border-radius: 1.5vmin;
  background: var(--pl-surface);
}

.wall-sys__code {
  font-size: clamp(0.875rem, 2.4vmin, 2.25rem);
  font-weight: 800;
}

.wall-sys__bar {
  width: 100%;
  height: 2vmin;
  border-radius: 1vmin;
}

.wall-sys__count {
  font-size: clamp(0.75rem, 1.8vmin, 1.75rem);
  font-weight: 700;
  color: var(--pl-text-muted);
}

.wall-sys__name {
  font-size: clamp(0.625rem, 1.4vmin, 1.25rem);
  color: var(--pl-text-subtle);
}

.wall-sys[data-tone="passed"] .wall-sys__bar { background: var(--st-passed-solid); }
.wall-sys[data-tone="anomaly"] .wall-sys__bar { background: var(--st-anomaly-solid); }
.wall-sys[data-tone="error"] .wall-sys__bar { background: var(--st-error-solid); }
.wall-sys[data-tone="running"] .wall-sys__bar { background: var(--st-running-solid); }
.wall-sys[data-tone="blocked"] .wall-sys__bar { background: var(--st-blocked-solid); }
.wall-sys[data-tone="pending"] .wall-sys__bar { background: var(--st-pending-solid); }

.wall-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.5vmin;
}
```

- [ ] **Step 7: 통과를 확인한다**

Run: `npm run build && python3 -m pytest tests/test_wall_http.py -q`
Expected: PASS (14 passed)

Run: `python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py -q`
Expected: PASS — `kpi_card` 에 `size` 인자를 더한 것이 일간 현황을 깨지 않아야 한다

Run: `npm run test`
Expected: PASS — `kpi-card/index.test.ts` 는 TS 쪽이라 매크로 변경에 영향받지 않는다

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과

- [ ] **Step 8: 커밋**

```bash
git add app/web/frontend/components/kpi-card/ app/web/templates/wall_fragment.html \
        app/web/frontend/styles/wall.css tests/test_wall_http.py
git commit -m "feat(web): 상황판 매트릭스 + 성과 스트립(KpiCard 대형 모드)"
```

---

## Task 6: 갱신 폴링과 수동 콘솔 검사

**Files:**
- Modify: `app/web/frontend/entries/wall.ts`
- Modify: `app/web/templates/wall_fragment.html` (htmx 속성)
- Create: `scripts/check_wall_console.py`
- Modify: `docs/CI.md`
- Test: `tests/test_wall_http.py` (추가)

**Interfaces:**
- Consumes: Task 3 의 `GET /wall/fragment`

- [ ] **Step 1: 테스트를 추가한다**

`tests/test_wall_http.py` 에 추가:

```python
def test_body_declares_htmx_polling_target():
    """갱신은 htmx 가 /wall/fragment 를 다시 받아 처리한다(설계 §3.9)."""
    client, _ = _client()
    with client:
        body = client.get("/wall").text
    assert 'hx-get="/wall/fragment"' in body
    assert 'hx-swap="outerHTML"' in body


def test_fragment_is_self_replacing():
    """프래그먼트 루트가 교체 대상과 같은 요소여야 outerHTML 스왑이 성립한다."""
    client, _ = _client()
    with client:
        body = client.get("/wall/fragment").text
    assert 'id="wall-body"' in body
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_wall_http.py -q -k "htmx or self_replacing"`
Expected: FAIL — `hx-get` 속성 없음

- [ ] **Step 3: 프래그먼트에 htmx 속성을 붙인다**

`app/web/templates/wall_fragment.html` 의 루트 `<div>` 를 고친다:

```jinja
<div id="wall-body" class="wall-body"
     data-dominant="{{ d.kind }}" data-tone="{{ d.tone }}"
     hx-get="/wall/fragment" hx-trigger="wall-refresh from:body" hx-swap="outerHTML">
```

`hx-swap="outerHTML"` 이므로 프래그먼트가 자기 자신을 교체한다 — 갱신 후에도 `hx-*` 속성이 그대로 살아 있어야 하며, 위 마크업이 매번 같이 오므로 성립한다.

- [ ] **Step 4: 폴링을 구현한다**

`app/web/frontend/entries/wall.ts` 를 다음으로 교체한다:

```ts
// 상황판 엔트리. Alpine·status-badge TS 를 싣지 않는다 — 조작이 없는 화면이다.
import "htmx.org";

import "../styles/wall.css";

// 상황판의 존재 이유가 "살아있음" 이므로 일간 대시보드보다 짧게 둔다.
// 부하가 문제되면 이 상수를 늘린다(env 는 만들지 않는다 — 조절 필요가 확인되지 않았다).
const REFRESH_MS = 15_000;

// dashboard.js 와 같은 형태의 최소 구현. document.hidden 가드로 보이지 않는 탭에서는
// 요청하지 않는다.
window.setInterval(() => {
  if (!document.hidden) {
    document.body.dispatchEvent(new CustomEvent("wall-refresh"));
  }
}, REFRESH_MS);
```

- [ ] **Step 5: 수동 콘솔 검사 스크립트를 만든다**

`docs/CI.md:3` 이 "라이브 Playwright E2E 는 CI 밖" 을 정책으로 못 박으므로 이 스크립트는 **게이트가 아니다.** 실행 가능한 형태로 남긴다.

`scripts/check_wall_console.py`:

```python
"""상황판 브라우저 콘솔 검사 — 수동 실행. CI 게이트가 아니다.

docs/CI.md 가 "라이브 Playwright E2E 는 CI 밖" 을 정책으로 두므로 이 검사는
게이트가 될 수 없다. P1·P2·P3-1 이 세 번 미룬 "콘솔 에러 0" 항목을 실행 가능한
형태로 남기는 것이 목적이다(P3-2 설계 §3.6 — 절반 해소).

사용:
    python3 scripts/run_local.py            # 별 터미널에서 앱 기동
    python3 scripts/check_wall_console.py   # 기본 http://127.0.0.1:8000/wall
    python3 scripts/check_wall_console.py --url http://host:port/wall
"""

from __future__ import annotations

import argparse
import sys

DEFAULT_URL = "http://127.0.0.1:8000/wall"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="상황판 콘솔 에러 검사(수동)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--wait-ms", type=int, default=3000, help="로드 후 관찰 시간")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 가 없습니다: python3 -m pip install -r requirements-dev.txt")
        return 2

    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in {"error", "warning"}
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        response = page.goto(args.url, wait_until="networkidle")
        if response is None or response.status != 200:
            status = response.status if response else "no response"
            print(f"실패: {args.url} 이 200 이 아닙니다 ({status})")
            browser.close()
            return 1
        page.wait_for_timeout(args.wait_ms)
        has_scrollbar = page.evaluate("document.documentElement.scrollHeight > window.innerHeight")
        browser.close()

    if has_scrollbar:
        problems.append("넌스크롤 위반: 1920x1080 에서 스크롤이 생겼습니다.")

    if problems:
        print(f"상황판 검사 실패 {len(problems)}건:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("상황판 검사 통과 (콘솔 에러 0 · 넌스크롤)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 6: `docs/CI.md` 에 CI 밖 검사로 기록한다**

`docs/CI.md` 의 "라이브 Playwright E2E 는 CI 밖" 서술과 같은 절에 추가한다:

```markdown
CI 밖 수동 검사:

| 스크립트 | 검사 |
| --- | --- |
| `scripts/check_wall_console.py` | 상황판 `/wall` 의 브라우저 콘솔 에러·넌스크롤 (앱 기동 후 실행) |
```

- [ ] **Step 7: 통과를 확인한다**

Run: `npm run build && python3 -m pytest tests/test_wall_http.py -q`
Expected: PASS (16 passed)

Run: `python3 -m pytest tests/ -q`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `npm run build && npm run typecheck && npm run lint && npm run test`
Expected: 전부 통과

- [ ] **Step 8: 육안 검증**

앱을 띄우고(`docs/INSTALL.md`) `http://127.0.0.1:8000/wall` 을 연다. **로그아웃 상태(시크릿 창)에서 확인한다** — 비인증 접근이 이 화면의 존재 이유다.

확인 항목:
- 시크릿 창에서 로그인 폼 없이 상황판이 뜨는가
- 브라우저 창을 1920×1080 으로 두었을 때 스크롤바가 없는가
- 창 크기를 바꿔도 글자 비율이 유지되는가 (`vmin` 기준)
- 시스템 6개가 한 줄에 보이고 색이 상태와 맞는가
- 성과 카드 3장이 크게 보이고 통과율 카드가 **없는가**
- 15초 뒤 갱신 요청이 네트워크 탭에 뜨는가 (`/wall/fragment`)
- 탭을 백그라운드로 두면 요청이 멈추는가 (`document.hidden` 가드)
- 콘솔 에러 0건 — 또는 `python3 scripts/check_wall_console.py`
- `E2E_WALL_ENABLED=false` 로 재기동하면 404 인가

OTP 대기 맥동은 실제 OTP 대기 Run 이 있어야 보인다. 확인하려면 브라우저 devtools 에서 `document.getElementById("wall-body").dataset.dominant = "waiting_input"` 로 강제한 뒤, OS "동작 줄이기" 를 켜서 멈추는지도 함께 본다.

- [ ] **Step 9: 커밋**

```bash
git add app/web/frontend/entries/wall.ts app/web/templates/wall_fragment.html \
        scripts/check_wall_console.py docs/CI.md tests/test_wall_http.py
git commit -m "feat(web): 상황판 15초 폴링 + 수동 콘솔 검사 스크립트"
```

---

## 완료 기준 (P3-2 DoD)

- [ ] 시크릿 창(비로그인)에서 `/wall` 200
- [ ] `E2E_WALL_ENABLED=false` → `/wall`·`/wall/fragment` 404
- [ ] `/wall` 응답에 `my_seconds`·`email`·`user_id`·`user_name` 문자열 0건
- [ ] `/wall` 응답에 `<button`·`<form`·`<a ` 0건
- [ ] `wall.html`·`wall_fragment.html` 이 `_macros.html`·`zone_b_matrix.html` 을 임포트하지 않음
- [ ] `wall.html` 이 `base.html` 을 상속하지 않음
- [ ] 지배 요소 5경로 + **OTP 대기가 실패보다 우선** (`tests/test_wall_view.py`)
- [ ] manifest 에 `entries/wall.ts` 존재, `main` 번들에 `.wall-hero` 미포함
- [ ] `wall.css` hex 0건 · `prefers-reduced-motion` 가드 존재 · `overflow: hidden` + `100dvh`
- [ ] 성과 스트립 3장(`data-size="lg"`), 통과율 카드 없음
- [ ] `wall.html` 이 `FG006_ALLOWLIST` 밖에서 게이트 통과
- [ ] `python3 -m pytest tests/ -q` 전부 통과
- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 전 게이트 통과
- [ ] `npm run build && npm run typecheck && npm run lint && npm run test` 전부 통과
- [ ] 1920×1080 에서 스크롤바 없음 (육안 또는 `scripts/check_wall_console.py`)
- [ ] `docs/CI.md` 에 CI 밖 수동 검사로 기록됨

---

## P3-2 이후

다음 조각은 **Step 6 — 일간 리포트 메일**이다. 이 계획이 남기는 자산:

- `build_wall_view` 의 지배 요소 판정 — 리포트의 "제목 한 줄"에 같은 규칙을 쓸 수 있다
- `kpi_card` 의 `size` 인자 — 메일은 인라인 스타일이 필요하므로 그대로 쓰기는 어렵지만 카드 계약(`key`·`label`·`value`·`note`)은 공유된다
- `summary["systems"]` 패스스루 — 리포트의 시스템별 표가 같은 데이터를 쓴다
- 다중 Vite 엔트리 — 검증된 구조

**Step 6 이 마주할 사실(P3-1 스펙 §0 에 기록):** `app/notifications/` 에는 Run 완료 메일만 있고 **일간·주간 리포트가 존재하지 않는다.** 상위 설계 §4 의 "같은 KPI 를 메일 인라인으로" 서술은 실제와 다르며, 생성기와 예약 발송을 새로 만들어야 한다. 또한 `report_renderer.py` 의 `_STATUS_COLORS` 는 웹 토큰과 **다른 hex 팔레트**(passed `#2f8f4e` vs `#10b981`)를 손으로 유지하고 있어, 화면과 메일의 상태 색이 어긋나 있다.
