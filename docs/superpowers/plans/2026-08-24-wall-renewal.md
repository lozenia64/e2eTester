# 상황판 리뉴얼 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상황판(`/wall`)을 암색 관제탑으로 바꾸고, 시스템 매트릭스를 오늘의 시간축 타임라인으로 승격한다.

**Architecture:** 서버(Jinja)가 렌더하는 구조를 그대로 유지한다. 백엔드는 기존 순수 빌더에 시각 필드와 타임라인 계산 함수를 더하고, 프론트는 CSS 백분율 배치로 막대를 그린다. 차트 라이브러리를 쓰지 않으며 신규 npm 패키지도 0개다(idiomorph 는 이미 저장소 의존성).

**Tech Stack:** Python 3.13 · FastAPI · Jinja2 · pytest · Playwright / TypeScript · Vite · htmx 2 · idiomorph

**Spec:** `docs/superpowers/specs/2026-08-24-wall-renewal-design.md`

## Global Constraints

스펙에서 그대로 옮긴 전역 요구사항. **모든 태스크에 암묵적으로 적용된다.**

- **차트 라이브러리 금지**(D2). 서버가 백분율을 계산하고 CSS 가 배치한다.
- **신규 npm 패키지 0개.** `idiomorph` 는 이미 `package.json` 에 있다.
- **테마 축을 만들지 않는다**(D3). 다크는 `wall.css` 스코프 안에서만. 다른 화면·메일·`tokens.generated.css` 에 영향 0.
- **`kpi_card` 매크로 시그니처 불변** — 대시보드와 공유한다.
- **JSON API 신설 금지**(P3-2 D3). 서버 렌더 HTML 만.
- **FG-001:** 외부 CDN 0. idiomorph 는 npm self-host + Vite 엔트리.
- **FG-002:** `frontend/` 안 하드코딩 hex 0. 예외는 `primitives.css` · `tokens.generated.css` · `status.generated.ts` 뿐.
- **FG-004:** `frontend/entries/` · `frontend/components/` 파일당 400줄 상한. `wall.css` 는 allowlist 에 없다(현재 128줄).
- **FG-006:** 템플릿에 상태 키 맵·상태 라벨 리터럴 금지. 서버 주입만.
- **UI 문자열은 한국어 고정**(`AGENTS.md`).
- **검증은 `.venv` 로 실행한다** — 시스템 Python 은 ruff 0.15/pytest-cov 미설치로 CI 와 어긋난다.
  - `./.venv/Scripts/python.exe -m pytest ...`
  - `./.venv/Scripts/python.exe -m ruff format --check .` (마크다운 안 파이썬 블록도 검사 대상)
- **`npm run build` 는 `emptyOutDir: true`** 라 dist 를 통째로 비운다. 빌드와 Playwright 를 겹쳐 돌리지 마라.

---

## File Structure

**수정**

| 파일 | 변경 |
| --- | --- |
| `app/contexts/insights/application/daily_dashboard.py` | 모듈 뷰에 `at_iso`, 시스템 뷰에 `first_at`/`last_at` |
| `app/contexts/insights/application/wall_view.py` | `build_timeline()` 신설 + `build_wall_view` 가 호출 |
| `app/web/frontend/styles/primitives.css` | 다크 램프 `--c-ink-*` 5개 추가 |
| `app/web/frontend/styles/wall.css` | 다크 전환 · 매트릭스 → 타임라인 · 모션 |
| `app/web/templates/wall.html` | `hx-ext="morph"` |
| `app/web/templates/wall_fragment.html` | 타임라인 마크업 · morph swap |
| `app/web/frontend/entries/wall.ts` | idiomorph 확장 import |
| `tests/test_daily_dashboard.py` | 시각 필드 계약 |
| `tests/test_wall_view.py` | 타임라인 계약 (기존 테스트 유지) |
| `tests/test_wall_http.py` | 프래그먼트 계약 갱신 |
| `tests/test_dashboard_viewport.py` | 상황판 Playwright 검증 추가 |

**신규 파일 없음.**

---

## Task 1: 뷰모델에 시각 필드

**Files:**
- Modify: `app/contexts/insights/application/daily_dashboard.py`
- Test: `tests/test_daily_dashboard.py`

**Interfaces:**
- Consumes: `DailyStatusRow.updated_at` (tz-aware datetime), 기존 `tz: ZoneInfo` 인자
- Produces:
  - 모듈 뷰 dict 에 `"at_iso": str | None` — 로컬 타임존 ISO
  - 시스템 뷰 dict 에 `"first_at": str | None` · `"last_at": str | None` — 그 시스템 모듈들의 `at_iso` 최소·최대

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_daily_dashboard.py` 끝에 추가:

```python
def test_module_view_carries_local_at_iso():
    from zoneinfo import ZoneInfo

    systems = [_sysdef("hom", ["login"])]
    rows = [make_status_row(system_code="hom", module_id="login", last_status=ModuleStatus.PASSED)]
    data = build_daily_dashboard_from_projection(
        systems,
        rows,
        [],
        generated_at=GEN_AT,
        date_label="2026-07-08",
        tz=ZoneInfo("Asia/Seoul"),
    )
    module = data["systems"][0]["modules"][0]
    # make_status_row 의 updated_at 은 2026-08-15 09:00 UTC == 18:00 KST
    assert module["at_iso"].startswith("2026-08-15T18:00")


def test_system_view_carries_first_and_last_at():
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from app.contexts.insights.contracts.query_rows import DailyStatusRow

    def _row(module_id: str, hour: int) -> DailyStatusRow:
        return DailyStatusRow(
            day_key="2026-08-15",
            system_code="hom",
            module_id=module_id,
            last_status=ModuleStatus.PASSED,
            last_run_id="run-1",
            duration_ms=1000,
            updated_at=datetime(2026, 8, 15, hour, 0, tzinfo=UTC),
            recovered=False,
        )

    systems = [_sysdef("hom", ["a", "b", "c"])]
    rows = [_row("b", 3), _row("a", 1), _row("c", 5)]
    data = build_daily_dashboard_from_projection(
        systems,
        rows,
        [],
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
    )
    system = data["systems"][0]
    assert system["first_at"].startswith("2026-08-15T10:00")  # 01:00 UTC == 10:00 KST
    assert system["last_at"].startswith("2026-08-15T14:00")  # 05:00 UTC == 14:00 KST


def test_system_without_inspection_has_no_span():
    from zoneinfo import ZoneInfo

    systems = [_sysdef("hom", ["login"])]
    data = build_daily_dashboard_from_projection(
        systems,
        [],
        [],
        generated_at=GEN_AT,
        date_label="2026-08-15",
        tz=ZoneInfo("Asia/Seoul"),
    )
    system = data["systems"][0]
    assert system["first_at"] is None
    assert system["last_at"] is None
    assert system["modules"][0]["at_iso"] is None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_daily_dashboard.py -q -k "at_iso or first_and_last or without_inspection"`
Expected: FAIL — `KeyError: 'at_iso'`

- [ ] **Step 3: 모듈 뷰에 `at_iso` 를 더한다**

`_module_view_from_row` 는 현재 `status_row` 와 `duration_ms` 를 받는다. `tz` 를 키워드로 받도록 시그니처를 넓히고 반환 dict 에 한 줄 더한다.

```python
def _module_view_from_row(
    module: RunModule | Any,
    *,
    status_row: DailyStatusRow | None,
    duration_ms: int | None,
    tz: ZoneInfo,
) -> dict[str, Any]:
```

`status` 를 `None` 으로 되돌리는 기존 `_NON_RESULT_STATUSES` 분기 **바로 아래**에 계산을 넣는다(제외 상태면 시각도 없어야 한다):

```python
    at_iso = (
        status_row.updated_at.astimezone(tz).isoformat()
        if status_row is not None and status is not None
        else None
    )
```

반환 dict 의 `"recovered": recovered,` 아래에 더한다:

```python
        # 상황판 타임라인의 x 좌표 원천(설계 §4.3). 로컬 타임존 ISO.
        "at_iso": at_iso,
```

- [ ] **Step 4: 시스템 뷰에 `first_at`/`last_at` 을 더한다**

`_system_view_from_projection` 도 `tz` 를 키워드로 받게 하고, `module_views` 를 만들 때 `tz=tz` 를 넘긴다. `counts` 계산 **아래**에 추가한다:

```python
    stamps = sorted(view["at_iso"] for view in module_views if view["at_iso"])
```

반환 dict 의 `"modules": module_views,` **위**에 두 줄을 더한다:

```python
        # 상황판 타임라인의 시스템 스팬(설계 §4.3). 점검이 없으면 None.
        "first_at": stamps[0] if stamps else None,
        "last_at": stamps[-1] if stamps else None,
```

> ISO 문자열 정렬로 시각을 비교한다. 같은 타임존·같은 포맷이므로 사전순 = 시간순이다.

- [ ] **Step 5: 호출부에 `tz` 를 넘긴다**

`build_daily_dashboard_from_projection` 안에서 `_system_view_from_projection(...)` 을 호출하는 자리에 `tz=tz,` 를 더한다.

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_daily_dashboard.py tests/test_daily_activity_feed.py -q`
Expected: PASS

- [ ] **Step 7: 대시보드 회귀가 없는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q -k "daily or dashboard or wall" -p no:randomly`
Expected: PASS

- [ ] **Step 8: 커밋**

```bash
git add app/contexts/insights/application/daily_dashboard.py tests/test_daily_dashboard.py
git commit -m "feat(wall): 뷰모델에 모듈 시각과 시스템 점검 스팬"
```

---

## Task 2: `build_timeline()` 순수 함수

**Files:**
- Modify: `app/contexts/insights/application/wall_view.py`
- Test: `tests/test_wall_view.py`

**Interfaces:**
- Consumes: Task 1 의 시스템 뷰 필드 `first_at` · `last_at`, 그리고 기존 `system_code` · `system_name` · `counts`
- Produces:
  ```python
  def build_timeline(systems: list[dict[str, Any]], *, now_iso: str) -> dict[str, Any]
  ```
  반환:
  ```python
  {
      "has_data": bool,
      "span_minutes": int,
      "now_pct": float,
      "lanes": [{"code": str, "name": str, "tone": str, "left_pct": float, "width_pct": float}],
      "ticks": [{"label": "07:00", "left_pct": float}],
  }
  ```

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_wall_view.py` 끝에 추가:

```python
def _sys_with_span(code: str, first: str, last: str, *, anomaly: int = 0) -> dict:
    return {
        "system_code": code,
        "system_name": code,
        "module_total": 3,
        "counts": {
            "passed": 3 - anomaly,
            "anomaly": anomaly,
            "error": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 0,
        },
        "modules": [],
        "first_at": first,
        "last_at": last,
    }


def test_timeline_is_empty_when_nothing_was_inspected():
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [_sys_with_span("HOM", None, None)]
    tl = build_timeline(systems, now_iso="2026-08-24T08:25:00+09:00")
    assert tl["has_data"] is False
    assert tl["lanes"] == []


def test_timeline_places_lane_by_elapsed_ratio():
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [
        _sys_with_span("HOM", "2026-08-24T07:00:00+09:00", "2026-08-24T07:30:00+09:00"),
        _sys_with_span("MHM", "2026-08-24T08:00:00+09:00", "2026-08-24T08:15:00+09:00"),
    ]
    tl = build_timeline(systems, now_iso="2026-08-24T09:00:00+09:00")
    assert tl["has_data"] is True
    assert tl["span_minutes"] == 120  # 07:00 -> 09:00
    hom, mhm = tl["lanes"]
    assert hom["left_pct"] == 0.0
    assert hom["width_pct"] == 25.0  # 30분 / 120분
    assert mhm["left_pct"] == 50.0  # 60분 / 120분
    assert mhm["width_pct"] == 12.5  # 15분 / 120분
    assert tl["now_pct"] == 100.0


def test_timeline_enforces_minimum_window_of_30_minutes():
    """전 시스템이 몇 분 안에 끝나도 스팬이 화면을 가득 채우지 않는다(설계 §4.3)."""
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [_sys_with_span("HOM", "2026-08-24T07:00:00+09:00", "2026-08-24T07:05:00+09:00")]
    tl = build_timeline(systems, now_iso="2026-08-24T07:06:00+09:00")
    assert tl["span_minutes"] == 30
    assert tl["lanes"][0]["width_pct"] == pytest.approx(16.67, abs=0.01)  # 5분 / 30분


def test_timeline_enforces_minimum_lane_width():
    """26초 Run 이 사라지지 않는다(설계 §4.3)."""
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [
        _sys_with_span("HOM", "2026-08-24T07:00:00+09:00", "2026-08-24T08:00:00+09:00"),
        _sys_with_span("CHB", "2026-08-24T07:30:00+09:00", "2026-08-24T07:30:26+09:00"),
    ]
    tl = build_timeline(systems, now_iso="2026-08-24T08:25:00+09:00")
    chb = tl["lanes"][1]
    assert chb["width_pct"] == 0.8


def test_timeline_survives_reversed_timestamps():
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [_sys_with_span("HOM", "2026-08-24T08:00:00+09:00", "2026-08-24T07:00:00+09:00")]
    tl = build_timeline(systems, now_iso="2026-08-24T09:00:00+09:00")
    assert tl["lanes"][0]["width_pct"] == 0.8
    assert tl["lanes"][0]["left_pct"] >= 0.0


def test_timeline_lane_tone_matches_system_tone():
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [
        _sys_with_span("FP", "2026-08-24T07:00:00+09:00", "2026-08-24T07:10:00+09:00", anomaly=1)
    ]
    tl = build_timeline(systems, now_iso="2026-08-24T08:00:00+09:00")
    assert tl["lanes"][0]["tone"] == "anomaly"


def test_timeline_emits_five_ticks_spanning_the_window():
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [_sys_with_span("HOM", "2026-08-24T07:00:00+09:00", "2026-08-24T07:30:00+09:00")]
    tl = build_timeline(systems, now_iso="2026-08-24T09:00:00+09:00")
    assert [t["left_pct"] for t in tl["ticks"]] == [0.0, 25.0, 50.0, 75.0, 100.0]
    assert [t["label"] for t in tl["ticks"]] == ["07:00", "07:30", "08:00", "08:30", "09:00"]


def test_systems_never_inspected_are_dropped_from_lanes():
    from app.contexts.insights.application.wall_view import build_timeline

    systems = [
        _sys_with_span("HOM", "2026-08-24T07:00:00+09:00", "2026-08-24T07:30:00+09:00"),
        _sys_with_span("HRP", None, None),
    ]
    tl = build_timeline(systems, now_iso="2026-08-24T09:00:00+09:00")
    assert [lane["code"] for lane in tl["lanes"]] == ["HOM"]
```

파일 상단 import 에 `import pytest` 가 없으면 더한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wall_view.py -q -k timeline`
Expected: FAIL — `ImportError: cannot import name 'build_timeline'`

- [ ] **Step 3: 구현한다**

`app/contexts/insights/application/wall_view.py` 상단 import 에 더한다:

```python
from datetime import datetime, timedelta
```

`_system_tone` 정의 **아래**에 추가한다:

```python
# 점검 창이 짧아도 스팬이 화면을 가득 채우지 않게 하는 하한(설계 §4.3).
_MIN_WINDOW = timedelta(minutes=30)
# 26초 Run 이 사라지지 않게 하는 폭 하한(%). 1920px 에서 약 15px.
_MIN_LANE_WIDTH_PCT = 0.8
_TICK_COUNT = 5


def _pct(part: timedelta, whole: timedelta) -> float:
    if whole.total_seconds() <= 0:
        return 0.0
    return round(part.total_seconds() / whole.total_seconds() * 100, 4)


def build_timeline(systems: list[dict[str, Any]], *, now_iso: str) -> dict[str, Any]:
    """오늘의 점검 창을 x축으로 하는 시스템별 스팬(설계 §4.3).

    축의 범위는 '오늘 첫 점검 → 지금'이다. 24시간 축은 실측상 94% 가 빈 공간이 된다
    (설계 §2). 창이 30분보다 짧으면 30분으로 늘려 잡는다.
    """
    now = datetime.fromisoformat(now_iso)
    spans = [
        (
            system,
            datetime.fromisoformat(system["first_at"]),
            datetime.fromisoformat(system["last_at"]),
        )
        for system in systems
        if system.get("first_at") and system.get("last_at")
    ]
    if not spans:
        return {"has_data": False, "span_minutes": 0, "now_pct": 0.0, "lanes": [], "ticks": []}

    origin = min(first for _, first, _ in spans)
    end = max(now, origin + _MIN_WINDOW)
    window = end - origin

    lanes = [
        {
            "code": system["system_code"],
            "name": system.get("system_name", system["system_code"]),
            "tone": _system_tone(system.get("counts", {})),
            "left_pct": _pct(max(first - origin, timedelta(0)), window),
            "width_pct": max(_pct(max(last - first, timedelta(0)), window), _MIN_LANE_WIDTH_PCT),
        }
        for system, first, last in spans
    ]

    ticks = [
        {
            "label": (origin + window * (i / (_TICK_COUNT - 1))).strftime("%H:%M"),
            "left_pct": round(i / (_TICK_COUNT - 1) * 100, 4),
        }
        for i in range(_TICK_COUNT)
    ]

    return {
        "has_data": True,
        "span_minutes": int(window.total_seconds() // 60),
        "now_pct": _pct(now - origin, window),
        "lanes": lanes,
        "ticks": ticks,
    }
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wall_view.py -q`
Expected: PASS (기존 테스트 포함 전부)

- [ ] **Step 5: 돌연변이 검증 — 테스트가 진짜인지 확인한다**

최소 창 하한을 지워 테스트가 실제로 잡는지 본다.

```bash
cp app/contexts/insights/application/wall_view.py /tmp/wv.bak
sed -i 's/end = max(now, origin + _MIN_WINDOW)/end = now/' app/contexts/insights/application/wall_view.py
./.venv/Scripts/python.exe -m pytest tests/test_wall_view.py -q -k minimum_window
# Expected: FAIL
cp /tmp/wv.bak app/contexts/insights/application/wall_view.py
git status --porcelain   # 비어야 정상
```

- [ ] **Step 6: 커밋**

```bash
git add app/contexts/insights/application/wall_view.py tests/test_wall_view.py
git commit -m "feat(wall): 오늘의 점검 창을 x축으로 하는 타임라인 계산기"
```

---

## Task 3: `build_wall_view` 에 타임라인 연결

**Files:**
- Modify: `app/contexts/insights/application/wall_view.py`
- Test: `tests/test_wall_view.py`

**Interfaces:**
- Consumes: Task 2 의 `build_timeline(systems, *, now_iso)`
- Produces: `build_wall_view(summary)` 반환 dict 에 `"timeline": dict` 추가. 기존 키(`dominant` · `systems` · `strip` · `date_label` · `generated_at`)는 **전부 유지**한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_wall_view.py` 끝에 추가:

```python
def test_wall_view_carries_timeline():
    summary = _summary()
    summary["systems"] = [
        _sys_with_span("HOM", "2026-08-24T07:00:00+09:00", "2026-08-24T07:30:00+09:00"),
    ]
    summary["generated_at"] = "2026-08-24T09:00:00+09:00"
    view = build_wall_view(summary)
    assert view["timeline"]["has_data"] is True
    assert view["timeline"]["lanes"][0]["code"] == "HOM"


def test_wall_view_timeline_is_empty_without_generated_at():
    """generated_at 이 비면 축을 그릴 수 없다 — 빈 상태로 떨어진다."""
    summary = _summary()
    summary["generated_at"] = ""
    view = build_wall_view(summary)
    assert view["timeline"]["has_data"] is False


def test_wall_view_keeps_existing_keys():
    view = build_wall_view(_summary())
    for key in ("dominant", "systems", "strip", "date_label", "generated_at"):
        assert key in view
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wall_view.py -q -k "carries_timeline or without_generated_at or keeps_existing"`
Expected: FAIL — `KeyError: 'timeline'`

- [ ] **Step 3: 구현한다**

`build_wall_view` 의 반환 dict 에서 `"date_label"` **위**에 한 항목을 더한다:

```python
        "timeline": (
            build_timeline(summary.get("systems", []), now_iso=generated_at)
            if generated_at
            else {"has_data": False, "span_minutes": 0, "now_pct": 0.0, "lanes": [], "ticks": []}
        ),
```

같은 함수 안에서 `generated_at` 을 먼저 꺼낸다. 반환문 **위**에 둔다:

```python
    generated_at = summary.get("generated_at", "")
```

그리고 반환 dict 의 `"generated_at": summary.get("generated_at", ""),` 를 `"generated_at": generated_at,` 로 바꾼다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wall_view.py tests/test_wall_http.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/contexts/insights/application/wall_view.py tests/test_wall_view.py
git commit -m "feat(wall): 뷰에 타임라인 연결 — 기존 키는 전부 유지"
```

---

## Task 4: 암색 팔레트

**Files:**
- Modify: `app/web/frontend/styles/primitives.css`
- Modify: `app/web/frontend/styles/wall.css`
- Test: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: 없음
- Produces: `wall.css` 의 `--wl-bg` · `--wl-surface` · `--wl-line` · `--wl-ink` · `--wl-dim` 토큰. Task 5 의 타임라인 스타일이 이것을 쓴다.

- [ ] **Step 1: 실패하는 Playwright 테스트를 쓴다**

`tests/test_dashboard_viewport.py` 끝에 추가한다. 이 파일의 `live_server` 픽스처를 그대로 쓴다.

```python
def test_wall_is_dark(page, live_server: str) -> None:
    """상황판이 실제로 어두운가 — DOM 존재가 아니라 computed style 로 본다(설계 §6)."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/wall", wait_until="networkidle")
    page.wait_for_selector("body.wall")
    got = page.evaluate(
        """() => {
            const cs = getComputedStyle(document.body);
            const rgb = cs.backgroundColor.match(/\\d+/g).map(Number);
            const lum = (0.2126*rgb[0] + 0.7152*rgb[1] + 0.0722*rgb[2]) / 255;
            return { bg: cs.backgroundColor, lum, color: cs.color };
        }"""
    )
    print("WALL DARK:", got)
    assert got["lum"] < 0.15, got
```

**`live_server` 는 현재 `/wall` 라우터를 마운트하지 않는다**(`_build_dashboard_test_app` 이
`dashboard_router` · `daily_router` 둘만 include). 먼저 마운트를 더한다.

`tests/test_dashboard_viewport.py` 상단 import 에:

```python
from app.api import routes_wall
```

`_build_dashboard_test_app` 안, `app.include_router(daily_router)` **아래**에 두 줄:

```python
    app.include_router(routes_wall.router)
    app.dependency_overrides[routes_wall.wall_enabled] = lambda: True
```

`get_daily_summary_queries` 는 이미 `FakeDailySummaryQueries(dashboard_data)` 로 덮여 있으므로
상황판도 같은 가짜 데이터를 쓴다 — 추가 픽스처가 필요 없다.

`wall_enabled` 를 명시적으로 덮는 이유: 기본값은 `true` 지만 로컬 `.env` 의
`E2E_WALL_ENABLED` 가 무엇이든 테스트가 흔들리지 않아야 한다. 대시보드 작업에서
`.env` 누출로 테스트가 깨진 전례가 있다(`test_auto_rerun_wiring`).

- [ ] **Step 2: 실패를 확인한다**

```bash
npm run build
./.venv/Scripts/python.exe -m pytest tests/test_dashboard_viewport.py -q -s -k wall_is_dark
```
Expected: FAIL — 현재 배경이 `--pl-bg`(밝은 회색)라 `lum` 이 0.9 대

- [ ] **Step 3: 다크 램프를 primitives 에 더한다**

`app/web/frontend/styles/primitives.css` 의 마지막 `}` **바로 위**에 추가한다.

```css
  /* ink — 상황판 전용 다크 램프(설계 §4.2).
     상시 디스플레이는 눈부심·번인 때문에 어두운 화면을 쓴다. 이 램프는
     wall.css 만 참조하며 다른 화면·메일에는 영향이 없다(테마 축 신설 아님). */
  --c-ink-950: #0b0e14;
  --c-ink-900: #111622;
  --c-ink-800: #1c2230;
  --c-ink-400: #8b93a7;
  --c-ink-100: #e7e9ee;
```

- [ ] **Step 4: `wall.css` 를 다크로 전환한다**

`@import` 두 줄 아래, `*` 리셋 **위**에 스코프 토큰을 둔다:

```css
/* 상황판 스코프 다크(설계 §4.2, D3). 테마 축을 만들지 않는다 —
   이 매핑은 wall.css 안에서만 유효하다. */
body.wall {
  --wl-bg: var(--c-ink-950);
  --wl-surface: var(--c-ink-900);
  --wl-line: var(--c-ink-800);
  --wl-dim: var(--c-ink-400);
  --wl-ink: var(--c-ink-100);
}
```

`body.wall` 규칙의 색 두 줄을 바꾼다:

```css
  background: var(--wl-bg);
  color: var(--wl-ink);
```

히어로 색을 `-text`(밝은 배경용)에서 `-solid`(발광용)로 바꾼다:

```css
.wall-hero[data-tone="passed"] .wall-hero__headline { color: var(--st-passed-solid); }
.wall-hero[data-tone="anomaly"] .wall-hero__headline { color: var(--st-anomaly-solid); }
.wall-hero[data-tone="error"] .wall-hero__headline { color: var(--st-error-solid); }
.wall-hero[data-tone="running"] .wall-hero__headline { color: var(--st-running-solid); }
.wall-hero[data-tone="waiting_input"] .wall-hero__headline { color: var(--st-waiting_input-solid); }
```

나머지 `--pl-*` 참조를 `--wl-*` 로 바꾼다:

| 기존 | 변경 |
| --- | --- |
| `.wall-hero__detail` 의 `var(--pl-text-muted)` | `var(--wl-dim)` |
| `.wall-sys` 의 `background: var(--pl-surface)` | `var(--wl-surface)` |
| `.wall-sys__count` 의 `var(--pl-text-muted)` | `var(--wl-dim)` |
| `.wall-sys__name` 의 `var(--pl-text-subtle)` | `var(--wl-dim)` |
| `.wall-meta` 의 `var(--pl-text-subtle)` | `var(--wl-dim)` |

확인:

```bash
grep -c -- "--pl-" app/web/frontend/styles/wall.css   # 0 이어야 한다
```

- [ ] **Step 5: 게이트와 테스트를 돌린다**

```bash
npm run build
./.venv/Scripts/python.exe scripts/check_frontend_gates.py; echo "FG: $?"
./.venv/Scripts/python.exe -m pytest tests/test_dashboard_viewport.py -q -s -k wall_is_dark
```
Expected: FG exit 0, 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/web/frontend/styles/primitives.css app/web/frontend/styles/wall.css tests/test_dashboard_viewport.py
git commit -m "feat(wall): 상황판 스코프 암색 팔레트 — 테마 축 신설 아님"
```

---

## Task 5: 타임라인 마크업과 스타일

**Files:**
- Modify: `app/web/templates/wall_fragment.html`
- Modify: `app/web/frontend/styles/wall.css`
- Test: `tests/test_wall_http.py`

**Interfaces:**
- Consumes: Task 3 의 `view.timeline` (`has_data` · `lanes[].code/name/tone/left_pct/width_pct` · `ticks[].label/left_pct` · `now_pct`), Task 4 의 `--wl-*` 토큰
- Produces: `.wall-timeline` 마크업. Task 6 의 모션이 `.wall-lane__span` 을 겨냥한다.

- [ ] **Step 1: 픽스처가 summary 를 갈아끼울 수 있게 만든다**

현재 `_FakeSummaryQueries` 는 모듈 상수 `SUMMARY` 를 **고정 반환**하고(`tests/test_wall_http.py:97-105`),
`SUMMARY["systems"]` 에는 Task 1 이 추가한 `first_at`/`last_at` 이 없다. 빈 상태 테스트를 쓰려면
주입이 필요하다. 두 곳만 고친다.

```python
class _FakeSummaryQueries:
    def __init__(self, summary: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.summary = summary if summary is not None else SUMMARY

    async def get_daily_summary(self, *, user_id, allowed_system_codes, is_admin=False):
        self.calls.append(
            {"user_id": user_id, "allowed": allowed_system_codes, "is_admin": is_admin}
        )
        return self.summary
```

```python
def _client(
    *, enabled: bool = True, summary: dict[str, Any] | None = None
) -> tuple[TestClient, _FakeSummaryQueries]:
    app = FastAPI()
    app.include_router(routes_wall.router)
    fake = _FakeSummaryQueries(summary)
    app.dependency_overrides[get_daily_summary_queries] = lambda: fake
    app.dependency_overrides[routes_wall.wall_enabled] = lambda: enabled
    return TestClient(app), fake
```

기본값이 `SUMMARY` 이므로 **기존 테스트 전부 그대로 통과한다.**

그리고 `SUMMARY["systems"]` 의 각 시스템에 스팬 두 필드를 더한다(값은 KST 아침대):

```python
        # 첫 번째 시스템
        "first_at": "2026-08-24T07:00:00+09:00",
        "last_at": "2026-08-24T07:30:00+09:00",
        # 두 번째 시스템
        "first_at": "2026-08-24T08:00:00+09:00",
        "last_at": "2026-08-24T08:15:00+09:00",
```

`SUMMARY["generated_at"]` 이 없으면 `"2026-08-24T09:00:00+09:00"` 을 더한다 — 없으면
`build_wall_view` 가 타임라인을 빈 상태로 떨어뜨린다(Task 3).

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_wall_http.py` 끝에 추가:

```python
def test_timeline_renders_a_lane_per_inspected_system():
    client, _ = _client()
    html = client.get("/wall").text
    assert 'class="wall-timeline"' in html
    assert html.count('class="wall-lane"') == 2  # SUMMARY 의 시스템 2개


def test_timeline_lane_carries_geometry_from_server():
    """좌표 계산은 서버가 한다 — 클라이언트 JS 가 없어도 그려진다(D2)."""
    client, _ = _client()
    html = client.get("/wall").text
    assert "--lane-left:" in html
    assert "--lane-width:" in html


def test_timeline_marks_now():
    client, _ = _client()
    html = client.get("/wall").text
    assert 'class="wall-timeline__now"' in html


def test_timeline_shows_waiting_message_when_nothing_inspected():
    empty = {**SUMMARY, "systems": []}
    client, _ = _client(summary=empty)
    html = client.get("/wall").text
    assert "오늘 점검 대기 중" in html
    assert 'class="wall-lane"' not in html


def test_matrix_markup_is_gone():
    """매트릭스는 타임라인의 y축으로 흡수됐다(D1)."""
    client, _ = _client()
    html = client.get("/wall").text
    assert 'class="wall-matrix"' not in html
    assert 'class="wall-sys"' not in html
```

- [ ] **Step 3: 실패를 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wall_http.py -q -k timeline`
Expected: FAIL — `wall-timeline` 없음

- [ ] **Step 4: 프래그먼트를 다시 쓴다**

`app/web/templates/wall_fragment.html` 의 `<section class="wall-matrix">…</section>` 블록 **전체**를 아래로 교체한다. 나머지(히어로·strip·meta)는 그대로 둔다.

```jinja
  {% set tl = view.timeline %}
  <section class="wall-timeline">
    {% if not tl.has_data %}
    <p class="wall-timeline__empty">오늘 점검 대기 중</p>
    {% else %}
    <div class="wall-timeline__lanes">
      {% for lane in tl.lanes %}
      <div class="wall-lane">
        <span class="wall-lane__code">{{ lane.code }}</span>
        <div class="wall-lane__track">
          <span class="wall-lane__span"
                data-tone="{{ lane.tone }}"
                style="--lane-left: {{ lane.left_pct }}%; --lane-width: {{ lane.width_pct }}%"
                aria-hidden="true"></span>
        </div>
      </div>
      {% endfor %}
      <span class="wall-timeline__now" style="--now-left: {{ tl.now_pct }}%" aria-hidden="true"></span>
    </div>
    <div class="wall-timeline__axis">
      {% for tick in tl.ticks %}
      <span class="wall-timeline__tick" style="--tick-left: {{ tick.left_pct }}%">{{ tick.label }}</span>
      {% endfor %}
    </div>
    {% endif %}
  </section>
```

- [ ] **Step 5: 스타일을 쓴다**

`app/web/frontend/styles/wall.css` 에서 `.wall-matrix` · `.wall-sys*` 규칙을 **전부 삭제**하고 그 자리에 넣는다.

```css
/* ── 오늘의 타임라인 ──
   x 좌표는 서버가 백분율로 계산해 --lane-* 로 내려준다(설계 §4.3, D2).
   차트 라이브러리를 쓰지 않으므로 JS 가 죽어도 이 화면은 그대로 남는다. */
.wall-timeline {
  display: flex;
  flex-direction: column;
  gap: 1vmin;
}

.wall-timeline__empty {
  padding: 6vmin 0;
  font-size: clamp(1rem, 5vmin, 5rem);
  font-weight: 700;
  color: var(--wl-dim);
}

.wall-timeline__lanes {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1vmin;
}

.wall-lane {
  display: grid;
  grid-template-columns: 12vmin 1fr;
  align-items: center;
  gap: 1.5vmin;
}

.wall-lane__code {
  font-size: clamp(0.875rem, 2.4vmin, 2.25rem);
  font-weight: 800;
  color: var(--wl-dim);
  text-align: right;
  letter-spacing: 0.04em;
}

.wall-lane__track {
  position: relative;
  height: 3vmin;
  border-radius: 0.6vmin;
  background: var(--wl-surface);
  overflow: hidden;
}

.wall-lane__span {
  position: absolute;
  top: 0;
  bottom: 0;
  left: var(--lane-left);
  width: var(--lane-width);
  border-radius: 0.6vmin;
}

.wall-lane__span[data-tone="passed"] { background: var(--st-passed-solid); }
.wall-lane__span[data-tone="anomaly"] { background: var(--st-anomaly-solid); }
.wall-lane__span[data-tone="error"] { background: var(--st-error-solid); }
.wall-lane__span[data-tone="running"] { background: var(--st-running-solid); }
.wall-lane__span[data-tone="blocked"] { background: var(--st-blocked-solid); }
.wall-lane__span[data-tone="pending"] { background: var(--st-pending-solid); }

/* "지금" — 레인 전체를 가로지르는 세로선. 오른쪽 끝에서 새 스팬이 태어난다. */
.wall-timeline__now {
  position: absolute;
  top: 0;
  bottom: 0;
  left: calc(12vmin + 1.5vmin + var(--now-left) * (100% - 13.5vmin) / 100%);
  width: 0.3vmin;
  background: var(--st-running-solid);
}

.wall-timeline__axis {
  position: relative;
  height: 3vmin;
  margin-left: calc(12vmin + 1.5vmin);
}

.wall-timeline__tick {
  position: absolute;
  left: var(--tick-left);
  transform: translateX(-50%);
  font-size: clamp(0.625rem, 1.6vmin, 1.5rem);
  color: var(--wl-dim);
  white-space: nowrap;
}
```

- [ ] **Step 6: 게이트와 테스트를 돌린다**

```bash
npm run build
./.venv/Scripts/python.exe scripts/check_frontend_gates.py; echo "FG: $?"
./.venv/Scripts/python.exe -m pytest tests/test_wall_http.py -q
```
Expected: FG exit 0(특히 FG-002 hex 0 · FG-006 상태 리터럴 0), 테스트 PASS

- [ ] **Step 7: 커밋**

```bash
git add app/web/templates/wall_fragment.html app/web/frontend/styles/wall.css tests/test_wall_http.py
git commit -m "feat(wall): 매트릭스를 오늘의 타임라인으로 승격"
```

---

## Task 6: morph 전환과 모션

**Files:**
- Modify: `app/web/frontend/entries/wall.ts`
- Modify: `app/web/templates/wall.html`
- Modify: `app/web/templates/wall_fragment.html`
- Modify: `app/web/frontend/styles/wall.css`
- Test: `tests/test_wall_http.py`

**Interfaces:**
- Consumes: Task 5 의 `.wall-lane__span` · `.wall-timeline__now`
- Produces: 없음(최종 태스크가 검증만 한다)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_wall_http.py` 끝에 추가:

```python
def test_body_declares_morph_extension_outside_the_swap_target():
    """확장 선언이 교체 대상 안에 있으면 첫 교체 후 사라진다(설계 §4.4)."""
    client, _ = _client()
    html = client.get("/wall").text
    body_open = html.index("<body")
    wall_body = html.index('id="wall-body"')
    assert 'hx-ext="morph"' in html
    assert html.index('hx-ext="morph"') < wall_body
    assert html.index('hx-ext="morph"') > body_open


def test_fragment_uses_morph_swap():
    client, _ = _client()
    html = client.get("/wall/fragment").text
    assert 'hx-swap="morph:outerHTML"' in html
    assert 'hx-swap="outerHTML"' not in html
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wall_http.py -q -k morph`
Expected: FAIL — `hx-ext="morph"` 없음

- [ ] **Step 3: 엔트리에서 확장을 임포트한다**

먼저 실제 파일명을 확인한다. **경로를 추측하지 마라.**

```bash
ls node_modules/idiomorph/dist/
```

`app/web/frontend/entries/wall.ts` 의 `import "htmx.org";` **아래**에 확인한 경로로 한 줄 더한다:

```ts
import "idiomorph/dist/idiomorph-ext.esm.js";
```

- [ ] **Step 4: 템플릿을 배선한다**

`app/web/templates/wall.html` 의 `<body class="wall">` 를 바꾼다:

```jinja
<body class="wall" hx-ext="morph">
```

`app/web/templates/wall_fragment.html` 의 `hx-swap="outerHTML"` 를 바꾼다:

```jinja
     hx-get="/wall/fragment" hx-trigger="wall-refresh from:body" hx-swap="morph:outerHTML">
```

- [ ] **Step 5: 모션을 더한다**

`app/web/frontend/styles/wall.css` 의 기존 `@keyframes wall-attention` 블록 **위**에 추가한다.

```css
/* ── 모션 ──
   원칙: 변한 것만 움직인다. morph 가 노드를 보존하므로 새로 삽입된 스팬만
   진입 애니메이션을 탄다(설계 §4.4). */
@starting-style {
  .wall-lane__span {
    width: 0;
    opacity: 0;
  }
}

.wall-lane__span {
  transition: width 0.6s var(--ease-out), opacity 0.6s var(--ease-out);
}

@keyframes wall-now-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.wall-timeline__now {
  animation: wall-now-pulse 1.8s ease-in-out infinite;
}

@keyframes wall-span-shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.wall-lane__span[data-tone="running"] {
  animation: wall-span-shimmer 1.8s ease-in-out infinite;
}
```

기존 `@media (prefers-reduced-motion: reduce)` 블록 안에 정지 규칙을 더한다:

```css
  .wall-lane__span,
  .wall-timeline__now {
    transition: none;
    animation: none;
  }
```

- [ ] **Step 6: 검증**

```bash
npm run build && npm run typecheck && npm run lint
./.venv/Scripts/python.exe scripts/check_frontend_gates.py; echo "FG: $?"
./.venv/Scripts/python.exe -m pytest tests/test_wall_http.py -q
```
Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add app/web/frontend/entries/wall.ts app/web/templates/wall.html app/web/templates/wall_fragment.html app/web/frontend/styles/wall.css tests/test_wall_http.py
git commit -m "feat(wall): morph 교체 + 새 스팬만 등장하는 모션"
```

---

## Task 7: 최종 검증

**Files:**
- Modify: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: Task 4~6 의 전체 화면
- Produces: 없음

- [ ] **Step 1: 넌스크롤·기하 검증 테스트를 쓴다**

`tests/test_dashboard_viewport.py` 끝에 추가:

```python
@pytest.mark.parametrize("w,h", [(1920, 1080), (2560, 1440)])
def test_wall_never_scrolls(page, live_server: str, w: int, h: int) -> None:
    page.set_viewport_size({"width": w, "height": h})
    page.goto(f"{live_server}/wall", wait_until="networkidle")
    page.wait_for_selector("body.wall")
    got = page.evaluate(
        """() => ({
            docOk: document.documentElement.scrollHeight <= window.innerHeight + 1,
            bodyOverflow: getComputedStyle(document.body).overflow,
        })"""
    )
    print(f"WALL SCROLL {w}x{h}:", got)
    assert got["docOk"], got


def test_wall_timeline_spans_are_positioned_and_visible(page, live_server: str) -> None:
    """서버가 내려준 백분율이 실제 픽셀로 반영되는가."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/wall", wait_until="networkidle")
    page.wait_for_selector(".wall-lane__span")
    got = page.evaluate(
        """() => [...document.querySelectorAll('.wall-lane__span')].map((s) => {
            const r = s.getBoundingClientRect();
            return { w: Math.round(r.width), h: Math.round(r.height) };
        })"""
    )
    print("WALL SPANS:", got)
    assert got, "스팬이 하나도 없다"
    assert all(s["w"] >= 4 and s["h"] >= 4 for s in got), got
```

- [ ] **Step 2: 격리 환경에서 전체 검증**

메인 저장소에서 돌리면 `vite build --watch` 가 dist 를 비워 오탐이 난다. 격리 워크트리에서 돌린다.

```bash
WT=/tmp/wall-verify
git worktree add --detach "$WT" HEAD
cmd //c mklink //J "$(cygpath -w $WT)\\node_modules" "$(cygpath -w $PWD)\\node_modules"
cp .env "$WT/.env"
cd "$WT" && npm run build && ./.venv/Scripts/python.exe -m pytest tests/test_dashboard_viewport.py -q -s -k wall
```
Expected: 전부 PASS

- [ ] **Step 3: 전체 게이트**

```bash
cd "$WT" && ./.venv/Scripts/python.exe scripts/ci/run_all_gates.py --profile full
```
Expected: `{"passed": true, ...}`

- [ ] **Step 4: 워크트리 정리**

```bash
cd /c/Users/ljy93/Desktop/e2eTester
git worktree remove --force /tmp/wall-verify
git worktree list   # 메인 하나만 남아야 한다
```

- [ ] **Step 5: 커밋**

```bash
git add tests/test_dashboard_viewport.py
git commit -m "test(wall): 넌스크롤·다크·스팬 기하 회귀 검증"
```

---

## 완료 확인

1단계가 끝났을 때 아래가 전부 참이어야 한다(스펙 §3.3).

- [ ] 1920×1080 · 2560×1440 에서 세로 스크롤바 0
- [ ] `body.wall` 배경 휘도 0.15 미만 (computed style)
- [ ] 프래그먼트가 `hx-swap="morph:outerHTML"`, `outerHTML` 단독 0건
- [ ] `hx-ext="morph"` 가 `#wall-body` **바깥**(body 태그)에 있다
- [ ] `build_timeline()` 단위 테스트 통과 — 위치·폭·최소 창·최소 폭·시각 역전·빈 상태
- [ ] 오늘 점검 0건이면 "오늘 점검 대기 중" 표시, 레인 0개
- [ ] `wall.css` 에 `--pl-*` 참조 0건, 하드코딩 hex 0건
- [ ] `wall-matrix` · `wall-sys` 마크업 0건
- [ ] `run_all_gates.py --profile full` 통과

**후속(이번 범위 밖):** 일자별 추이 · 30일 복구 추이 · `run_history_index` 기반 타임라인 승격 — 스펙 §8.
