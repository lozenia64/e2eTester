# 일간 대시보드 관제탑화 1단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일간 대시보드 `/` 를 3열 관제탑 레이아웃으로 바꾸고, 라이브 활동 피드를 신설하고, 교체를 morph 로 전환하고, 이중 밀도 시스템을 철거한다.

**Architecture:** Jinja 서버 렌더 + htmx 프래그먼트 폴링 구조를 그대로 유지한다(SPA 아님). 백엔드는 기존 순수 집계 함수에 활동 피드 빌더 하나를 더하고, 프래그먼트 존을 하나 추가한다. 프론트엔드는 `dashboard.js` 를 Vite 엔트리 `entries/dashboard.ts` 로 이관하며 밀도 계산 코드를 버리고, CSS 는 컨테이너 쿼리 단일 체계로 3열 그리드를 그린다.

**Tech Stack:** Python 3 · FastAPI · Jinja2 · pytest · Playwright / TypeScript · Vite · htmx 2 · Alpine · idiomorph · Vitest · Tailwind v4(PostCSS)

**Spec:** `docs/superpowers/specs/2026-08-23-dashboard-mission-control-design.md`

## Global Constraints

스펙에서 그대로 옮긴 프로젝트 전역 요구사항. **모든 태스크의 요구사항에 암묵적으로 포함된다.**

- **라이트 단일 팔레트.** 다크모드·테마 축을 만들지 않는다(스펙 §2.2 · D4).
- **FG-001:** 템플릿에 외부 CDN `<script>`/`<link>` 0건. 새 라이브러리는 반드시 npm self-host + Vite 엔트리.
- **FG-002:** `app/web/frontend/` 안에 하드코딩 hex 0건. 예외는 `primitives.css` · `tokens.generated.css` · `status.generated.ts` 뿐.
- **FG-003:** 상태 라벨은 `app/core/status_labels.py` 또는 `frontend/lib/status.generated.ts` 경유만.
- **FG-004:** `frontend/entries/` · `frontend/components/` 파일당 400줄 상한.
- **FG-005:** 템플릿의 `/static/*` 직접 참조 금지. `_assets.html` 매크로 경유.
- **FG-006:** 템플릿에 상태 키 맵 리터럴·상태 라벨 리터럴 금지. 서버 주입만.
- **`kpi_card` 매크로 시그니처 불변** — 상황판 `wall_fragment.html` 과 공유한다(D2).
- **신규 의존성은 `idiomorph` 하나뿐.** 모션 라이브러리·차트 라이브러리를 추가하지 않는다(D3 · 스펙 §2.2).
- **UI 문자열은 한국어 고정**(`AGENTS.md` 제약).
- 게이트 실행: `python3 scripts/check_frontend_gates.py` · `python3 scripts/ci/run_all_gates.py --profile full`

---

## File Structure

**신규 생성**

| 파일 | 책임 |
| --- | --- |
| `app/web/templates/dashboard/partials/zone_c_activity.html` | 활동 피드 프래그먼트 마크업 |
| `app/web/frontend/entries/dashboard.ts` | 대시보드 페이지 엔트리(드로어·새로고침·폴링) |
| `app/web/frontend/components/status-hero/index.ts` | 진행 링 각도 계산(순수 함수) |
| `app/web/frontend/components/status-hero/index.test.ts` | 위 함수 Vitest |
| `app/web/frontend/components/status-hero/styles.css` | 지배 상태 열 스타일 |
| `app/web/frontend/components/system-matrix/styles.css` | 매트릭스 열 스타일 |
| `app/web/frontend/components/activity-feed/styles.css` | 활동 피드 열 스타일 |
| `tests/test_daily_activity_feed.py` | `build_activity_feed` 순수 단위 테스트 |

**수정**

| 파일 | 변경 |
| --- | --- |
| `app/contexts/insights/application/daily_dashboard.py` | `build_activity_feed()` 추가 · 반환 dict 에 `activity` · `tz` 파라미터 |
| `app/orchestrator/queries/daily_queries.py` | 스케줄 타임존 해석 후 빌더에 전달 |
| `app/api/routes_daily.py` | `_FRAGMENT_TEMPLATES` 에 `activity` 존 추가 |
| `app/web/templates/dashboard.html` | 3열 호스트 구조 · morph 배선 · 엔트리 스크립트 교체 |
| `app/web/templates/dashboard/partials/zone_a_kpi.html` | 히어로를 숫자+링으로 |
| `app/web/templates/dashboard/partials/_macros.html` | `system_row` 셀 방식 재설계 |
| `app/web/frontend/styles/dashboard.css` | 3열 그리드 · 밀도 블록 제거 · 컴포넌트로 분할 |
| `app/web/frontend/entries/main.ts` | (변경 없음 — 확인만) |
| `vite.config.ts` | `dashboard` 엔트리 추가 |
| `package.json` | `idiomorph` 추가 |
| `scripts/check_frontend_gates.py` | `FG005_ALLOWLIST` 에서 `/static/dashboard.js` 제거 · `FG004_ALLOWLIST` 에서 `dashboard.css` 제거 |
| `tests/test_dashboard_viewport.py` | 밀도 테스트 교체 · 3열 테스트 추가 |
| `tests/test_dashboard_fragments_http.py` | `activity` 존 계약 테스트 추가 |

**삭제**

| 파일 | 시점 |
| --- | --- |
| `app/web/static/dashboard.js` | Task 4 |

---

## Task 1: 활동 피드 뷰모델

**Files:**
- Modify: `app/contexts/insights/application/daily_dashboard.py`
- Test: `tests/test_daily_activity_feed.py` (Create)

**Interfaces:**
- Consumes: `DailyStatusRow`(`day_key` · `system_code` · `module_id` · `last_status` · `last_run_id` · `duration_ms` · `updated_at` · `recovered`), `SystemDefinition`(`system_code` · `name` · `modules[].module_id` · `modules[].name`)
- Produces:
  ```python
  def build_activity_feed(
      status_rows: list[DailyStatusRow],
      systems: list[SystemDefinition],
      *,
      tz: ZoneInfo,
      limit: int = 20,
  ) -> list[dict[str, Any]]
  ```
  각 항목의 키: `system_code` · `system_name` · `module_id` · `module_name` · `status_label` · `tone` · `at`(로컬 `"HH:MM"`) · `at_iso`(로컬 ISO) · `run_id` · `recovered`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_daily_activity_feed.py` 생성:

```python
"""활동 피드 집계기 순수 단위 테스트.

브라우저·DB 없이 정렬·필터·포맷 규칙만 검증한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.contexts.insights.application.daily_dashboard import build_activity_feed
from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition, SystemDefinition
from tests.conftest import make_status_row

KST = ZoneInfo("Asia/Seoul")


def _sysdef(code: str, module_ids: list[str]) -> SystemDefinition:
    return SystemDefinition(
        system_code=code,
        name=code.upper(),
        description="",
        display_order=100,
        modules=[
            ModuleDefinition(
                module_id=mid,
                system_code=code,
                name=f"{mid}-이름",
                description="",
                group="g",
                order=i,
            )
            for i, mid in enumerate(module_ids)
        ],
    )


def _row_at(hour: int, minute: int, *, module_id: str, status: ModuleStatus, **kw):
    row = make_status_row(system_code="hom", module_id=module_id, last_status=status, **kw)
    return type(row)(
        day_key=row.day_key,
        system_code=row.system_code,
        module_id=row.module_id,
        last_status=row.last_status,
        last_run_id=row.last_run_id,
        duration_ms=row.duration_ms,
        updated_at=datetime(2026, 8, 15, hour, minute, tzinfo=UTC),
        recovered=row.recovered,
    )


def test_sorts_by_updated_at_descending():
    systems = [_sysdef("hom", ["login", "search", "order"])]
    rows = [
        _row_at(1, 0, module_id="login", status=ModuleStatus.PASSED),
        _row_at(3, 0, module_id="search", status=ModuleStatus.PASSED),
        _row_at(2, 0, module_id="order", status=ModuleStatus.PASSED),
    ]
    feed = build_activity_feed(rows, systems, tz=KST)
    assert [item["module_id"] for item in feed] == ["search", "order", "login"]


def test_respects_limit():
    systems = [_sysdef("hom", ["a", "b", "c"])]
    rows = [
        _row_at(1, 0, module_id="a", status=ModuleStatus.PASSED),
        _row_at(2, 0, module_id="b", status=ModuleStatus.PASSED),
        _row_at(3, 0, module_id="c", status=ModuleStatus.PASSED),
    ]
    feed = build_activity_feed(rows, systems, tz=KST, limit=2)
    assert len(feed) == 2
    assert [item["module_id"] for item in feed] == ["c", "b"]


def test_formats_time_in_given_timezone():
    systems = [_sysdef("hom", ["login"])]
    # UTC 00:30 == KST 09:30
    rows = [_row_at(0, 30, module_id="login", status=ModuleStatus.PASSED)]
    feed = build_activity_feed(rows, systems, tz=KST)
    assert feed[0]["at"] == "09:30"
    assert feed[0]["at_iso"].startswith("2026-08-15T09:30")


def test_excludes_non_result_statuses():
    systems = [_sysdef("hom", ["a", "b", "c", "d"])]
    rows = [
        _row_at(1, 0, module_id="a", status=ModuleStatus.PENDING),
        _row_at(2, 0, module_id="b", status=ModuleStatus.QUEUED),
        _row_at(3, 0, module_id="c", status=ModuleStatus.SKIPPED),
        _row_at(4, 0, module_id="d", status=ModuleStatus.PASSED),
    ]
    feed = build_activity_feed(rows, systems, tz=KST)
    assert [item["module_id"] for item in feed] == ["d"]


def test_carries_label_tone_run_id_and_recovered():
    systems = [_sysdef("hom", ["login"])]
    rows = [
        _row_at(
            5, 0, module_id="login", status=ModuleStatus.PASSED,
            last_run_id="run-42", recovered=True,
        )
    ]
    feed = build_activity_feed(rows, systems, tz=KST)
    item = feed[0]
    assert item["system_name"] == "HOM"
    assert item["module_name"] == "login-이름"
    assert item["status_label"] == "정상"
    assert item["tone"] == "passed"
    assert item["run_id"] == "run-42"
    assert item["recovered"] is True


def test_skips_rows_whose_module_is_not_in_registry():
    """레지스트리에서 모듈이 제거된 뒤 남은 과거 프로젝션 행은 조용히 버린다."""
    systems = [_sysdef("hom", ["login"])]
    rows = [_row_at(1, 0, module_id="deleted-module", status=ModuleStatus.PASSED)]
    assert build_activity_feed(rows, systems, tz=KST) == []


def test_empty_input_returns_empty_list():
    assert build_activity_feed([], [], tz=KST) == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_activity_feed.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_activity_feed'`

- [ ] **Step 3: 최소 구현을 넣는다**

`app/contexts/insights/application/daily_dashboard.py` 의 `build_attention_items` 정의 **바로 아래**에 추가한다. 파일 상단 import 에 `from zoneinfo import ZoneInfo` 를 `TYPE_CHECKING` 블록 **밖**에 더한다(런타임 타입 힌트가 아니라 시그니처 문서용이므로 `from __future__ import annotations` 아래에서는 문자열로 평가되지만, 명시적 import 가 가독성에 낫다).

```python
def build_activity_feed(
    status_rows: list[DailyStatusRow],
    systems: list[SystemDefinition],
    *,
    tz: ZoneInfo,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """최근 갱신된 모듈 상태를 시간 내림차순으로 — 대시보드 우측 활동 피드용.

    신규 프로젝션·쿼리를 만들지 않는다. ``daily_system_status`` 행이 이미 들고 있는
    ``updated_at``/``recovered`` 를 그대로 쓴다(설계 §3.4).
    """
    module_index: dict[tuple[str, str], str] = {
        (system.system_code, module.module_id): module.name
        for system in systems
        for module in system.modules
    }
    system_names = {system.system_code: system.name for system in systems}

    items: list[dict[str, Any]] = []
    for row in status_rows:
        if row.last_status in _NON_RESULT_STATUSES:
            continue
        module_name = module_index.get((row.system_code, row.module_id))
        if module_name is None:
            # 레지스트리에서 사라진 모듈의 잔여 행 — 이름을 지어내지 않고 버린다.
            continue
        local = row.updated_at.astimezone(tz)
        items.append(
            {
                "system_code": row.system_code,
                "system_name": system_names.get(row.system_code, row.system_code),
                "module_id": row.module_id,
                "module_name": module_name,
                "status_label": module_status_label(row.last_status),
                "tone": module_status_badge_tone(row.last_status),
                "at": local.strftime("%H:%M"),
                "at_iso": local.isoformat(),
                "run_id": row.last_run_id,
                "recovered": bool(row.recovered),
            }
        )

    items.sort(key=lambda it: it["at_iso"], reverse=True)
    return items[:limit]
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_daily_activity_feed.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 린트·타입 확인**

Run: `python3 -m ruff check app/contexts/insights/application/daily_dashboard.py tests/test_daily_activity_feed.py && python3 -m ruff format --check app/contexts/insights/application/daily_dashboard.py tests/test_daily_activity_feed.py`
Expected: 통과

- [ ] **Step 6: 커밋**

```bash
git add app/contexts/insights/application/daily_dashboard.py tests/test_daily_activity_feed.py
git commit -m "feat(dashboard): 활동 피드 집계기 — 기존 프로젝션 행만 사용"
```

---

## Task 2: 활동 피드를 대시보드 뷰모델에 연결 + 갱신 시각 타임존 교정

**Files:**
- Modify: `app/contexts/insights/application/daily_dashboard.py` (`build_daily_dashboard_from_projection`)
- Modify: `app/orchestrator/queries/daily_queries.py`
- Modify: `tests/test_daily_dashboard.py` · `tests/test_dashboard_fragments_http.py` · `tests/test_dashboard_viewport.py` (호출부 갱신)
- Test: `tests/test_daily_dashboard.py`

**Interfaces:**
- Consumes: Task 1 의 `build_activity_feed(status_rows, systems, *, tz, limit=20)`
- Produces: `build_daily_dashboard_from_projection(..., *, tz: ZoneInfo, ...)` — 반환 dict 에 `"activity": list[dict]` 추가. `"generated_at"` 은 **로컬 타임존 ISO** 로 바뀐다.

> **왜 타임존을 여기서 손대는가:** `daily_queries.py:62` 가 `generated_at=datetime.now(UTC)` 를 넣고 `zone_a_kpi.html:22` · `wall_fragment.html:32` 가 `[11:16]` 으로 잘라 "갱신 HH:MM" 을 표시한다. **즉 현재 두 화면 모두 UTC 시각을 보여주고 있다(KST 기준 9시간 오차).** Task 1 의 활동 피드가 바로 옆에 로컬 시각을 표시하므로, 고치지 않으면 한 화면에서 두 시각이 어긋난다. 템플릿 슬라이스는 그대로 두고 값만 로컬로 바꾸면 두 화면이 동시에 교정된다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_daily_dashboard.py` 끝에 추가:

```python
def test_dashboard_includes_activity_feed():
    from zoneinfo import ZoneInfo

    systems = [_sysdef("hom", ["login", "search"])]
    rows = [
        make_status_row(system_code="hom", module_id="login", last_status=ModuleStatus.PASSED),
        make_status_row(system_code="hom", module_id="search", last_status=ModuleStatus.ERROR),
    ]
    data = build_daily_dashboard_from_projection(
        systems,
        rows,
        [],
        generated_at=GEN_AT,
        date_label="2026-07-08",
        tz=ZoneInfo("Asia/Seoul"),
    )
    assert "activity" in data
    assert len(data["activity"]) == 2
    assert {item["module_id"] for item in data["activity"]} == {"login", "search"}


def test_generated_at_is_rendered_in_schedule_timezone():
    from zoneinfo import ZoneInfo

    # GEN_AT = 2026-07-08 03:00 UTC == 12:00 KST
    data = build_daily_dashboard_from_projection(
        [],
        [],
        [],
        generated_at=GEN_AT,
        date_label="2026-07-08",
        tz=ZoneInfo("Asia/Seoul"),
    )
    assert data["generated_at"][11:16] == "12:00"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_dashboard.py::test_dashboard_includes_activity_feed tests/test_daily_dashboard.py::test_generated_at_is_rendered_in_schedule_timezone -v`
Expected: FAIL — `TypeError: build_daily_dashboard_from_projection() got an unexpected keyword argument 'tz'`

- [ ] **Step 3: 빌더 시그니처와 반환을 바꾼다**

`build_daily_dashboard_from_projection` 의 시그니처에 `tz` 를 **키워드 전용 필수 인자**로 더한다(기본값을 두지 않는다 — 기본 UTC 는 조용히 틀린 시각을 만든다).

```python
def build_daily_dashboard_from_projection(
    systems: list[SystemDefinition],
    status_rows: list[DailyStatusRow],
    run_summaries: list[DailyRunSummaryRow],
    *,
    duration_by_module_run: dict[tuple[str, str], int | None] | None = None,
    generated_at: datetime,
    date_label: str,
    tz: ZoneInfo,
) -> dict[str, Any]:
```

반환 dict 를 다음과 같이 바꾼다(`generated_at` 한 줄 수정 + `activity` 한 줄 추가):

```python
    return {
        "generated_at": generated_at.astimezone(tz).isoformat(),
        "date_label": date_label,
        "totals": totals,
        "systems": system_views,
        "attention": build_attention_items(system_views),
        "activity": build_activity_feed(status_rows, systems, tz=tz),
    }
```

- [ ] **Step 4: 프로덕션 호출부를 고친다**

`app/orchestrator/queries/daily_queries.py` — import 에 타임존 해석기를 더한다:

```python
from app.core.schedule_time import resolve_schedule_timezone
```

`get_daily_dashboard` 의 반환문을 바꾼다:

```python
        tz, _ = resolve_schedule_timezone()
        return build_daily_dashboard_from_projection(
            systems,
            status_rows,
            run_summaries,
            duration_by_module_run=duration_by_module_run,
            generated_at=datetime.now(UTC),
            date_label=target_label,
            tz=tz,
        )
```

- [ ] **Step 5: 기존 테스트 호출부를 고친다**

`build_daily_dashboard_from_projection` 을 호출하는 모든 테스트에 `tz=ZoneInfo("Asia/Seoul")` 을 더한다. 대상을 먼저 찾는다:

Run: `grep -rn "build_daily_dashboard_from_projection(" tests/ | grep -v "^tests/test_daily_activity_feed"`

각 호출부에 `tz=ZoneInfo("Asia/Seoul"),` 를 마지막 키워드 인자로 추가하고, 해당 파일 상단에 `from zoneinfo import ZoneInfo` 를 더한다.

- [ ] **Step 6: 전체 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_daily_dashboard.py tests/test_daily_summary.py tests/test_dashboard_fragments_http.py -v`
Expected: PASS

- [ ] **Step 7: 아키텍처 게이트 확인**

`app.contexts.insights` → `app.core` 방향 의존은 기존에도 있으므로 새 위반이 없어야 한다.

Run: `python3 -m lint_imports --config pyproject.toml`
Expected: 통과

- [ ] **Step 8: 커밋**

```bash
git add app/contexts/insights/application/daily_dashboard.py app/orchestrator/queries/daily_queries.py tests/
git commit -m "feat(dashboard): 뷰모델에 활동 피드 + 갱신 시각을 스케줄 타임존으로 교정

generated_at 이 UTC ISO 로 나가 템플릿의 [11:16] 슬라이스가 KST 기준
9시간 어긋난 시각을 표시하고 있었다(대시보드·상황판 공통). 값을 로컬로
바꿔 템플릿 변경 없이 두 화면을 함께 교정한다."
```

---

## Task 3: 활동 피드 프래그먼트 존

**Files:**
- Create: `app/web/templates/dashboard/partials/zone_c_activity.html`
- Modify: `app/api/routes_daily.py:28-31` (`_FRAGMENT_TEMPLATES`)
- Test: `tests/test_dashboard_fragments_http.py`

**Interfaces:**
- Consumes: Task 2 의 `data["activity"]` — 항목 키는 Task 1 의 Produces 참조
- Produces: `GET /api/dashboard/daily/fragments/activity` → `<div id="dash-zone-activity" class="dash-activity">…</div>`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_dashboard_fragments_http.py` 끝에 추가한다. 이 파일의 기존 `client` 픽스처와 `_build_realistic_six_system_dashboard` 를 그대로 쓴다(파일 상단에서 이미 정의·임포트된다).

```python
def test_activity_fragment_renders_items(client):
    res = client.get("/api/dashboard/daily/fragments/activity")
    assert res.status_code == 200
    html = res.text
    assert 'id="dash-zone-activity"' in html
    assert 'class="dash-activity"' in html
    # 항목 하나 이상이 시각·시스템·모듈을 담는다
    assert "dash-activity__item" in html


def test_activity_fragment_unknown_zone_still_404(client):
    assert client.get("/api/dashboard/daily/fragments/nope").status_code == 404
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py::test_activity_fragment_renders_items -v`
Expected: FAIL — 404 (등록되지 않은 zone)

- [ ] **Step 3: 템플릿을 만든다**

`app/web/templates/dashboard/partials/zone_c_activity.html`:

```jinja
{# Zone C — 라이브 활동 피드. 상태 라벨·톤은 서버가 주입한다(FG-006). #}
<div id="dash-zone-activity" class="dash-activity">
  <p class="dash-activity__eyebrow">최근 활동</p>
  {% if not data.activity %}
  <p class="dash-activity__empty">오늘 기록된 점검 활동이 없습니다.</p>
  {% else %}
  <ol class="dash-activity__list">
    {% for item in data.activity %}
    <li class="dash-activity__item" data-tone="{{ item.tone }}" data-module="{{ item.system_code }}:{{ item.module_id }}">
      {% if item.run_id %}<a class="dash-activity__link" href="/runs/{{ item.run_id }}">{% endif %}
      <span class="dash-activity__time">{{ item.at }}</span>
      <span class="dash-activity__dot" aria-hidden="true"></span>
      <span class="dash-activity__text">
        <span class="dash-activity__where">{{ item.system_name }} · {{ item.module_name }}</span>
        <span class="dash-activity__status">{{ item.status_label }}</span>
      </span>
      {% if item.recovered %}<span class="dash-activity__recovered" title="자동 복구 발생">⟳</span>{% endif %}
      {% if item.run_id %}</a>{% endif %}
    </li>
    {% endfor %}
  </ol>
  {% endif %}
</div>
```

- [ ] **Step 4: 라우트에 존을 등록한다**

`app/api/routes_daily.py` 의 `_FRAGMENT_TEMPLATES` 를 바꾼다:

```python
_FRAGMENT_TEMPLATES = {
    "kpi": "dashboard/partials/zone_a_kpi.html",
    "matrix": "dashboard/partials/zone_b_matrix.html",
    "activity": "dashboard/partials/zone_c_activity.html",
}
```

`daily_dashboard_fragment` 의 분기는 그대로 둔다 — `zone != "kpi"` 이면 `_load_dashboard` 를 타므로 `activity` 존이 자동으로 대시보드 데이터를 받는다.

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py -v`
Expected: PASS

- [ ] **Step 6: 프론트엔드 게이트 확인**

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과 (FG-006 이 새 템플릿에서 상태 리터럴을 잡지 않아야 한다)

- [ ] **Step 7: 커밋**

```bash
git add app/web/templates/dashboard/partials/zone_c_activity.html app/api/routes_daily.py tests/test_dashboard_fragments_http.py
git commit -m "feat(dashboard): 활동 피드 프래그먼트 존 신설"
```

---

## Task 4: `dashboard.js` → `entries/dashboard.ts` 이관 + 밀도 시스템 철거

**Files:**
- Create: `app/web/frontend/entries/dashboard.ts`
- Delete: `app/web/static/dashboard.js`
- Modify: `vite.config.ts` · `app/web/templates/dashboard.html` · `scripts/check_frontend_gates.py` · `app/web/frontend/styles/dashboard.css`
- Modify: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: 전역 `htmx`(`entries/main.ts` 가 self-host), 커스텀 이벤트 `dash-refresh` · `dash-open-drawer` · `dash-close-drawer`
- Produces: Vite 엔트리 `entries/dashboard.ts` — `_assets.html` 의 `asset_script("entries/dashboard.ts")` 로 로드된다

> **왜 안전한가:** `dashboard.css:316` 의 `.dash-sys-row { flex: 1 1 0; min-height: 0 }` 가 이미 균등 분할을 한다. JS `applyRowFlexBasis()` 는 그 위에 인라인 px 를 덮어쓸 뿐이다. 지우면 CSS 로 되돌아간다.

- [ ] **Step 1: 밀도 관련 Playwright 테스트를 새 계약으로 바꾼다(실패하는 테스트)**

`tests/test_dashboard_viewport.py:393` 의 `test_density_downgrades_on_resize_to_568` 전체를 아래로 **교체**한다. 밀도 티어는 더 이상 존재하지 않으므로 티어 다운그레이드가 아니라 **결과**(넘치지 않음)를 검증한다.

```python
def test_no_density_dataset_and_still_fits_at_568(page, live_server: str) -> None:
    """밀도 티어 JS 철거 후에도 좁은 뷰포트에서 넘치지 않아야 한다."""
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(live_server, wait_until="networkidle")
    page.set_viewport_size({"width": 1280, "height": 568})
    page.wait_for_timeout(300)
    state = page.evaluate(
        """() => {
            const de = document.documentElement;
            const sys = document.querySelector('#dash-zone-matrix');
            return {
                density: sys ? sys.dataset.density ?? null : null,
                inlineFlex: sys
                    ? [...sys.querySelectorAll('.dash-sys-row')].some((r) => r.style.flex !== '')
                    : false,
                docOk: de.scrollHeight <= window.innerHeight + 1,
                zoneOk: sys ? sys.scrollHeight <= sys.clientHeight + 1 : false,
            };
        }"""
    )
    assert state["density"] is None, "data-density 가 남아 있다 — 밀도 JS 가 살아있음"
    assert state["inlineFlex"] is False, "행에 인라인 flex 가 남아 있다 — 밀도 JS 가 살아있음"
    assert state["docOk"], "문서가 세로로 넘친다"
    assert state["zoneOk"], "매트릭스 존이 내부 스크롤을 만든다"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_dashboard_viewport.py::test_no_density_dataset_and_still_fits_at_568 -v`
Expected: FAIL — `data-density 가 남아 있다`

- [ ] **Step 3: TypeScript 엔트리를 만든다**

`app/web/frontend/entries/dashboard.ts` 생성. 원본 `dashboard.js` 293줄 중 **밀도·분할 코드(약 190줄)를 버리고** 나머지를 타입과 함께 옮긴다.

```ts
// 일간 대시보드 페이지 엔트리. 드로어 · 새로고침 · 폴링만 맡는다.
// 밀도 계산은 CSS 컨테이너 쿼리가 담당하므로 여기 없다(설계 §3.6).
import "../components/status-hero/styles.css";
import "../components/system-matrix/styles.css";
import "../components/activity-feed/styles.css";

declare const htmx: {
  ajax: (verb: string, path: string, opts: { target: string; swap: string }) => void;
};

const REFRESH_MS = 30_000;

const root = document.querySelector<HTMLElement>(".dash");

function openDrawer(systemCode: string | undefined): void {
  if (!systemCode || typeof htmx === "undefined") return;
  htmx.ajax("GET", `/api/dashboard/daily/fragments/system/${systemCode}/panel`, {
    target: "#dash-drawer-body",
    swap: "innerHTML",
  });
  window.dispatchEvent(new CustomEvent("dash-open-drawer"));
}

function requestRefresh(): void {
  document.body.dispatchEvent(new CustomEvent("dash-refresh"));
}

// 행 안의 링크·CTA 는 드로어를 열지 않고 자기 목적지로 간다.
const PASSTHROUGH_SELECTORS = [".dash-cell--link", ".dash-sys-row__cta", ".dash-activity__link"];

function bind(dash: HTMLElement): void {
  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;
    if (!dash.contains(target) && target !== dash) return;
    document.querySelector("#dash-error")?.classList.add("hidden");
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    const detail = (event as CustomEvent<{ pathInfo?: { requestPath?: string } }>).detail;
    const path = detail?.pathInfo?.requestPath ?? "";
    if (!path.includes("/api/dashboard/daily")) return;
    document.querySelector("#dash-error")?.classList.remove("hidden");
  });

  dash.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;

    if (PASSTHROUGH_SELECTORS.some((sel) => target.closest(sel))) {
      event.stopPropagation();
      return;
    }

    const refreshBtn = target.closest<HTMLButtonElement>("#dash-refresh");
    if (refreshBtn) {
      refreshBtn.disabled = true;
      requestRefresh();
      window.setTimeout(() => {
        refreshBtn.disabled = false;
      }, 600);
      return;
    }

    const row = target.closest<HTMLElement>(".dash-sys-row");
    if (!row || !dash.contains(row)) return;
    openDrawer(row.dataset.systemCode);
  });

  dash.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = (event.target as HTMLElement | null)?.closest<HTMLElement>(".dash-sys-row");
    if (!row || !dash.contains(row)) return;
    event.preventDefault();
    openDrawer(row.dataset.systemCode);
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) requestRefresh();
  });

  window.setInterval(() => {
    if (!document.hidden) requestRefresh();
  }, REFRESH_MS);
}

if (root) bind(root);
```

> `.dash-mod--link` · `.dash-seg--link` 는 Task 6 에서 `.dash-cell--link` 로 통합되므로 위 목록에 미리 새 이름을 쓴다. Task 6 이전에는 해당 셀렉터가 매치되지 않을 뿐 오류가 아니다.

- [ ] **Step 4: 컴포넌트 CSS 자리표시를 만든다**

Step 3 의 import 가 깨지지 않도록 세 파일을 **빈 주석만 담아** 생성한다. 내용은 Task 6~8 이 채운다.

```bash
mkdir -p app/web/frontend/components/status-hero app/web/frontend/components/system-matrix app/web/frontend/components/activity-feed
printf '/* 지배 상태 열 — Task 6/7 에서 채운다. */\n' > app/web/frontend/components/status-hero/styles.css
printf '/* 시스템 매트릭스 열 — Task 8 에서 채운다. */\n' > app/web/frontend/components/system-matrix/styles.css
printf '/* 활동 피드 열 — Task 9 에서 채운다. */\n' > app/web/frontend/components/activity-feed/styles.css
```

- [ ] **Step 5: Vite 엔트리를 등록한다**

`vite.config.ts` 의 `rollupOptions.input` 에 한 줄을 더한다(`wall` 아래):

```ts
        dashboard: resolve(__dirname, "app/web/frontend/entries/dashboard.ts"),
```

- [ ] **Step 6: 템플릿의 스크립트 태그를 교체한다**

`app/web/templates/dashboard.html` 의 `{% block scripts %}` 를 바꾼다:

```jinja
{% block scripts %}
{% import "_assets.html" as dash_assets %}
{{ dash_assets.asset_script("entries/dashboard.ts") }}
{% endblock %}
```

> `base.html` 이 `_assets.html` 을 임포트해도 자식 블록에는 전달되지 않는다. 블록 안에서 별도 이름(`dash_assets`)으로 다시 임포트한다.

- [ ] **Step 7: 밀도 CSS 블록을 지운다**

`app/web/frontend/styles/dashboard.css` 에서 다음을 삭제한다:
- `[data-density="compact"]` · `[data-density="dense"]` · `[data-density="minimal"]` · `[data-density="micro"]` 를 포함하는 모든 규칙 블록
- `#dash-host-kpi[data-kpi-compress="true"]` 를 포함하는 모든 규칙 블록

삭제 후 확인:

Run: `grep -c "data-density\|data-kpi-compress" app/web/frontend/styles/dashboard.css`
Expected: `0`

- [ ] **Step 8: 레거시 파일을 지우고 allowlist 를 줄인다**

```bash
git rm app/web/static/dashboard.js
```

`scripts/check_frontend_gates.py` 의 `FG005_ALLOWLIST` 에서 `"/static/dashboard.js",` 한 줄을 삭제한다.

- [ ] **Step 9: 빌드하고 전체 검증**

```bash
npm run build && npm run typecheck && npm run lint && npm test
python3 scripts/check_frontend_gates.py
python3 -m pytest tests/frontend/ -v
python3 -m pytest tests/test_dashboard_viewport.py -v
```
Expected: 전부 통과. 특히 `test_no_density_dataset_and_still_fits_at_568` PASS.

> `tests/frontend/test_vendor_bundles.py` 는 **차트 vendor 엔트리 전용** 테스트다(`VENDOR_ENTRIES` 상수). `entries/dashboard.ts` 는 vendor 가 아니므로 등록하지 않는다. 이 엔트리의 방어선은 `npm run build` + FG-005(템플릿의 static 직접 참조 0) 두 가지다.

- [ ] **Step 10: 커밋**

```bash
git add -A
git commit -m "refactor(web): dashboard.js 를 Vite 엔트리로 이관 + 이중 밀도 시스템 철거

CSS 컨테이너 쿼리가 이미 하던 일을 JS 190줄이 덮어쓰고 있었다.
FG-005 allowlist 1건 감소."
```

---

## Task 5: idiomorph 도입 + 세 존 morph 전환

**Files:**
- Modify: `package.json` · `app/web/frontend/entries/dashboard.ts` · `app/web/templates/dashboard.html` · `app/web/frontend/styles/dashboard.css`
- Test: `tests/frontend/test_dashboard_morph_wiring.py` (Create)

**Interfaces:**
- Consumes: Task 4 의 `entries/dashboard.ts`
- Produces: `.dash` 에 `hx-ext="morph"`, 세 호스트가 `hx-swap="morph:innerHTML"`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/frontend/test_dashboard_morph_wiring.py` 생성. **앱을 띄우지 않고 템플릿 파일을 직접 읽는 정적 계약 테스트**다 — `check_frontend_gates.py` 와 같은 방식이며, `tests/test_dashboard_fragments_http.py` 의 픽스처 앱에는 대시보드 페이지 라우터가 마운트돼 있지 않다(`daily_router` 만 포함).

```python
"""대시보드 morph 배선 정적 계약.

30초 폴링이 innerHTML 통짜 교체를 하면 스크롤·포커스·진행 중 애니메이션이
매번 소실된다(설계 §1.3). 세 존이 morph 로 교체되는지 파일에서 직접 확인한다.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("app/web/templates/dashboard.html")

ZONE_HOSTS = ("dash-host-kpi", "dash-host-matrix", "dash-host-activity")


def test_dashboard_declares_morph_extension():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert 'hx-ext="morph"' in html, "idiomorph 확장이 선언되지 않았다"


def test_all_three_zone_hosts_exist():
    html = DASHBOARD.read_text(encoding="utf-8")
    for host in ZONE_HOSTS:
        assert f'id="{host}"' in html, f"{host} 호스트가 없다"


def test_every_zone_uses_morph_swap():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert html.count('hx-swap="morph:innerHTML"') == len(ZONE_HOSTS)
    assert 'hx-swap="innerHTML"' not in html, "통짜 innerHTML 교체가 남아 있다"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_dashboard_morph_wiring.py -v`
Expected: FAIL — `idiomorph 확장이 선언되지 않았다`

- [ ] **Step 3: 패키지를 설치하고 확장 엔트리 경로를 확인한다**

```bash
npm install idiomorph
ls node_modules/idiomorph/dist/
```

출력에서 htmx 확장 ESM 파일명을 확인한다(`idiomorph-ext.esm.js` 계열). **경로를 추측하지 말고 실제 파일명을 쓴다.** 확장 파일이 없고 `idiomorph.esm.js` 만 있으면, htmx 확장 등록 코드를 직접 쓰지 말고 그 시점에 보고한다.

- [ ] **Step 4: 엔트리에서 확장을 임포트한다**

`app/web/frontend/entries/dashboard.ts` 의 CSS import 아래에 한 줄을 더한다(Step 3 에서 확인한 실제 경로로):

```ts
import "idiomorph/dist/idiomorph-ext.esm.js";
```

- [ ] **Step 5: 템플릿을 배선한다**

`app/web/templates/dashboard.html` 을 바꾼다. `.dash` 루트에 `hx-ext="morph"` 를 더하고, 세 호스트의 `hx-swap` 을 `morph:innerHTML` 로 바꾸고, 활동 피드 호스트를 추가한다.

```jinja
<div class="dash"
     hx-ext="morph"
     x-data="{ drawerOpen: false }"
     @dash-close-drawer.window="drawerOpen = false"
     @dash-open-drawer.window="drawerOpen = true">

  <div id="dash-host-kpi"
       hx-get="/api/dashboard/daily/fragments/kpi"
       hx-trigger="load, dash-refresh from:body"
       hx-indicator="#dash-htmx-busy"
       hx-swap="morph:innerHTML">
    …기존 스켈레톤 유지…
  </div>

  <div id="dash-host-matrix"
       class="dash-host-matrix"
       hx-get="/api/dashboard/daily/fragments/matrix"
       hx-trigger="load, dash-refresh from:body"
       hx-indicator="#dash-htmx-busy"
       hx-swap="morph:innerHTML">
    …기존 스켈레톤 유지…
  </div>

  <div id="dash-host-activity"
       class="dash-host-activity"
       hx-get="/api/dashboard/daily/fragments/activity"
       hx-trigger="load, dash-refresh from:body"
       hx-indicator="#dash-htmx-busy"
       hx-swap="morph:innerHTML">
    <div class="dash-activity" aria-hidden="true">
      <p class="dash-activity__eyebrow">최근 활동</p>
    </div>
  </div>

  …기존 #dash-error · 드로어 유지…
</div>
```

- [ ] **Step 6: 30초마다 반복 재생되던 stagger 를 최초 1회로 제한한다**

`app/web/frontend/styles/dashboard.css` 에서 `.dash-sys-row` 의 `animation: dash-row-in ...` 선언과 `:nth-child` 지연 6줄을 지우고, 최초 렌더에만 붙는 형태로 바꾼다.

```css
/* 첫 로드에서만 재생한다. morph 는 노드를 보존하므로 갱신 시 재생될 신규 노드가
   없지만, 매트릭스가 통째로 새로 그려지는 경로(빈 상태 → 데이터)에서도 반복되지
   않도록 클래스로 한 번만 건다. */
.dash__systems[data-first-paint="true"] .dash-sys-row {
  animation: dash-row-in 0.35s var(--ease-out) both;
}
.dash__systems[data-first-paint="true"] .dash-sys-row:nth-child(1) { animation-delay: 0ms; }
.dash__systems[data-first-paint="true"] .dash-sys-row:nth-child(2) { animation-delay: 40ms; }
.dash__systems[data-first-paint="true"] .dash-sys-row:nth-child(3) { animation-delay: 80ms; }
.dash__systems[data-first-paint="true"] .dash-sys-row:nth-child(4) { animation-delay: 120ms; }
.dash__systems[data-first-paint="true"] .dash-sys-row:nth-child(5) { animation-delay: 160ms; }
.dash__systems[data-first-paint="true"] .dash-sys-row:nth-child(6) { animation-delay: 200ms; }

@media (prefers-reduced-motion: reduce) {
  .dash__systems[data-first-paint="true"] .dash-sys-row { animation: none; }
}
```

`app/web/frontend/entries/dashboard.ts` 의 `bind()` 안, `htmx:afterSwap` 리스너에 최초 1회 표시를 더한다:

```ts
  let firstPaintDone = false;
  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;
    if (target.id !== "dash-host-matrix") return;
    const list = target.querySelector<HTMLElement>(".dash__systems");
    if (!list) return;
    if (firstPaintDone) {
      delete list.dataset.firstPaint;
      return;
    }
    firstPaintDone = true;
    list.dataset.firstPaint = "true";
    window.setTimeout(() => delete list.dataset.firstPaint, 800);
  });
```

- [ ] **Step 7: 테스트가 통과하는지 확인한다**

```bash
npm run build && npm run typecheck && npm run lint
python3 -m pytest tests/frontend/test_dashboard_morph_wiring.py tests/test_dashboard_fragments_http.py -v
python3 scripts/check_frontend_gates.py
```
Expected: 전부 통과

- [ ] **Step 8: 드로어가 열린 채 갱신돼도 닫히지 않는지 손으로 확인한다**

앱을 띄우고 대시보드에서 시스템 행을 클릭해 드로어를 연 뒤, 새로고침 버튼을 눌러 갱신을 트리거한다. 드로어가 열린 채 남아 있어야 한다(드로어는 morph 대상 3존 바깥이므로 구조적으로 안전하지만, idiomorph 도입 첫 단계이므로 실물로 확인한다 — 스펙 §8).

- [ ] **Step 9: KPI 카운트업이 morph 이후에도 도는지 확인한다**

`entries/main.ts` 의 `htmx:afterSwap` 핸들러가 `bindKpiCards()` 를 다시 건다. idiomorph 도 같은 이벤트를 발화하므로 **코드 변경 없이** 동작해야 한다. 다만 morph 는 노드를 보존하므로 `kpi-card/index.ts` 의 `data-kpi-bound` 가드 때문에 값이 바뀐 카드도 재생되지 않을 수 있다.

브라우저 콘솔에서 확인한다:

```js
// 갱신 직후 — 값이 바뀐 카드는 data-target 과 표시 텍스트가 같아야 한다
[...document.querySelectorAll('.kpi-card__value')].map((el) => ({
  target: el.dataset.target, shown: el.textContent,
}))
```

`target` 과 `shown` 이 어긋나면 `bindKpiCards()` 를 고쳐 **`data-target` 이 바뀐 카드에 한해 가드를 통과**시킨다:

```ts
    if (card.dataset.kpiBound === "true" && card.dataset.kpiTarget === raw) return;
    card.dataset.kpiBound = "true";
    card.dataset.kpiTarget = raw;
```

(`raw` 를 읽는 줄보다 아래로 옮겨야 한다. 이 경우 `app/web/frontend/components/kpi-card/index.test.ts` 에 "값이 바뀌면 다시 카운트업한다" 케이스를 추가한다.)

- [ ] **Step 10: 커밋**

```bash
git add -A
git commit -m "feat(dashboard): idiomorph morph 교체 + stagger 반복 재생 제거

30초 폴링마다 innerHTML 통짜 교체로 6행 stagger 가 재생되고 스크롤·
포커스가 소실되던 것을 morph diff 교체로 바꾼다."
```

---

## Task 6: 3열 그리드 레이아웃

**Files:**
- Modify: `app/web/frontend/styles/dashboard.css`
- Test: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: Task 5 의 세 호스트 (`#dash-host-kpi` · `#dash-host-matrix` · `#dash-host-activity`)
- Produces: `.dash` 가 `display: grid` 3열. 활동 피드 열만 내부 스크롤.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_dashboard_viewport.py` 끝에 추가:

```python
def test_three_column_layout_at_1920(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(live_server, wait_until="networkidle")
    boxes = page.evaluate(
        """() => {
            const pick = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { left: Math.round(r.left), top: Math.round(r.top), w: Math.round(r.width) };
            };
            return {
                hero: pick('#dash-host-kpi'),
                matrix: pick('#dash-host-matrix'),
                activity: pick('#dash-host-activity'),
            };
        }"""
    )
    assert boxes["hero"] and boxes["matrix"] and boxes["activity"]
    # 세 열이 같은 행에 나란히 — 좌→우 순서
    assert boxes["hero"]["left"] < boxes["matrix"]["left"] < boxes["activity"]["left"]
    assert abs(boxes["hero"]["top"] - boxes["matrix"]["top"]) <= 2
    assert abs(boxes["matrix"]["top"] - boxes["activity"]["top"]) <= 2


def test_only_activity_column_scrolls_internally(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(live_server, wait_until="networkidle")
    state = page.evaluate(
        """() => {
            const ov = (sel) => {
                const el = document.querySelector(sel);
                return el ? getComputedStyle(el).overflowY : null;
            };
            return {
                doc: document.documentElement.scrollHeight <= window.innerHeight + 1,
                hero: ov('#dash-host-kpi'),
                matrix: ov('#dash-host-matrix'),
                activity: ov('#dash-host-activity'),
            };
        }"""
    )
    assert state["doc"], "문서가 세로로 넘친다"
    assert state["hero"] == "hidden"
    assert state["matrix"] == "hidden"
    assert state["activity"] in ("auto", "scroll")


def test_stacks_to_single_column_on_mobile(page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server, wait_until="networkidle")
    boxes = page.evaluate(
        """() => {
            const pick = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { left: Math.round(r.left), top: Math.round(r.top) };
            };
            return { hero: pick('#dash-host-kpi'), matrix: pick('#dash-host-matrix') };
        }"""
    )
    assert boxes["hero"]["left"] == boxes["matrix"]["left"], "모바일에서 열이 나란히 있다"
    assert boxes["matrix"]["top"] > boxes["hero"]["top"], "모바일에서 세로 스택이 아니다"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_dashboard_viewport.py::test_three_column_layout_at_1920 -v`
Expected: FAIL — 세 열이 세로로 쌓여 `left` 가 모두 같다

- [ ] **Step 3: 그리드로 바꾼다**

`app/web/frontend/styles/dashboard.css` 의 `.dash` 규칙을 바꾼다. `container-type` · `height` · `overflow` · `padding` · 색은 그대로 두고 레이아웃만 교체한다.

```css
.dash {
  container-type: size;
  container-name: dash;
  display: grid;
  grid-template-columns: minmax(16rem, 20rem) 1fr minmax(17.5rem, 21.25rem);
  grid-template-rows: minmax(0, 1fr);
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  gap: clamp(0.5rem, 1.2cqi, 1rem);
  padding: clamp(0.5rem, 1.5cqh, 1.5rem) clamp(0.75rem, 2cqi, 2rem);
  background: var(--pl-bg);
  color: var(--pl-text);
}

#dash-host-kpi {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  gap: clamp(0.25rem, 0.6cqh, 0.625rem);
  overflow: hidden;
}

.dash-host-matrix {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.dash-host-activity {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 1024~1440px — 피드를 좌측 열 하단으로 내린다(2열) */
@container dash (max-width: 1440px) {
  .dash {
    grid-template-columns: minmax(16rem, 20rem) 1fr;
    grid-template-rows: minmax(0, 1fr) minmax(0, 0.6fr);
  }
  #dash-host-kpi { grid-column: 1; grid-row: 1; }
  .dash-host-matrix { grid-column: 2; grid-row: 1 / span 2; }
  .dash-host-activity { grid-column: 1; grid-row: 2; }
}

/* 모바일 — 1열 스택 */
@media (max-width: 767px) {
  .dash {
    display: flex;
    flex-direction: column;
  }
  .dash-host-activity {
    flex: 0 0 auto;
    max-height: 30%;
  }
}
```

`#dash-host-kpi` 의 옛 `max-height: 42%` 선언은 삭제한다 — 세로 2단 시절의 예산이며 3열에서는 의미가 없다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

```bash
npm run build
python3 -m pytest tests/test_dashboard_viewport.py -v
```
Expected: 새 테스트 3개 PASS. **기존 뷰포트 테스트 중 세로 2단을 전제하던 것이 깨질 수 있다** — 깨진 테스트를 하나씩 열어 3열 전제로 고친다. 전제 자체가 사라진 테스트(예: KPI 존 42% 예산)는 삭제하고, 삭제 이유를 커밋 메시지에 남긴다.

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "feat(dashboard): 3열 관제탑 그리드 — 피드 열만 내부 스크롤"
```

---

## Task 7: 지배 상태 — 숫자 + 진행 링

**Files:**
- Create: `app/web/frontend/components/status-hero/index.ts` · `index.test.ts`
- Modify: `app/web/frontend/components/status-hero/styles.css` · `app/web/templates/dashboard/partials/zone_a_kpi.html` · `app/web/frontend/entries/dashboard.ts`

**Interfaces:**
- Consumes: `data.totals`(`passed` · `modules` · `pass_rate` · `error` · `anomaly` · `running` · `not_inspected`) · `data.cards` · `data.date_label` · `data.generated_at`
- Produces:
  ```ts
  export function passRateToDegrees(passed: number, total: number): number
  export function bindStatusHero(root?: ParentNode): void
  ```

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`app/web/frontend/components/status-hero/index.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { passRateToDegrees } from "./index";

describe("passRateToDegrees", () => {
  it("0 통과는 0도", () => {
    expect(passRateToDegrees(0, 31)).toBe(0);
  });

  it("전부 통과는 360도", () => {
    expect(passRateToDegrees(31, 31)).toBe(360);
  });

  it("절반 통과는 180도", () => {
    expect(passRateToDegrees(5, 10)).toBe(180);
  });

  it("모듈이 0개면 0도 — 0 나눗셈이 NaN 을 만들지 않는다", () => {
    expect(passRateToDegrees(0, 0)).toBe(0);
  });

  it("통과 수가 총계를 넘어도 360도를 넘지 않는다", () => {
    expect(passRateToDegrees(40, 31)).toBe(360);
  });

  it("음수 입력은 0도로 잘린다", () => {
    expect(passRateToDegrees(-3, 31)).toBe(0);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npm test -- status-hero`
Expected: FAIL — 모듈을 찾을 수 없음

- [ ] **Step 3: 구현한다**

`app/web/frontend/components/status-hero/index.ts`:

```ts
// 지배 상태 진행 링. conic-gradient 각도만 계산한다 — SVG·차트 라이브러리 없음.

const FULL_TURN_DEG = 360;

export function passRateToDegrees(passed: number, total: number): number {
  if (!Number.isFinite(passed) || !Number.isFinite(total) || total <= 0) return 0;
  const ratio = Math.min(Math.max(passed / total, 0), 1);
  return Math.round(ratio * FULL_TURN_DEG);
}

export function bindStatusHero(root: ParentNode = document): void {
  const rings = root.querySelectorAll<HTMLElement>(".status-hero__ring");
  rings.forEach((ring) => {
    const passed = Number(ring.dataset.passed ?? "0");
    const total = Number(ring.dataset.total ?? "0");
    ring.style.setProperty("--ring-deg", `${passRateToDegrees(passed, total)}deg`);
  });
}
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `npm test -- status-hero`
Expected: PASS (6 passed)

- [ ] **Step 5: 엔트리에서 바인딩한다**

`app/web/frontend/entries/dashboard.ts` 에 import 와 호출을 더한다.

```ts
import { bindStatusHero } from "../components/status-hero/index";
```

`bind()` 안의 `htmx:afterSwap` 리스너 본문 첫 줄에 다음을 더한다(존을 가리지 않고 매번 호출해도 idempotent 하다):

```ts
    bindStatusHero(target);
```

그리고 파일 끝의 `if (root) bind(root);` 앞에 최초 렌더용 호출을 더한다:

```ts
document.addEventListener("DOMContentLoaded", () => bindStatusHero());
```

- [ ] **Step 6: 스타일을 쓴다**

`app/web/frontend/components/status-hero/styles.css` 의 자리표시 주석을 지우고 채운다. **hex 금지(FG-002)** — 토큰만 쓴다.

```css
/* 지배 상태 열 — 대형 숫자 + conic-gradient 진행 링(설계 §3.2). */

.status-hero {
  display: flex;
  min-height: 0;
  flex-direction: column;
  align-items: center;
  gap: clamp(0.5rem, 1.2cqh, 1rem);
  padding: clamp(0.75rem, 2cqh, 1.5rem);
  border-radius: clamp(0.75rem, 1.4cqh, 1.25rem);
  background: var(--pl-surface);
  box-shadow: var(--pl-shadow-md), inset 0 0 0 1px var(--pl-border);
  text-align: center;
}

.status-hero__ring {
  position: relative;
  display: grid;
  width: min(100%, clamp(7rem, 26cqh, 14rem));
  aspect-ratio: 1;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(
    var(--ring-color, var(--st-pending-solid)) var(--ring-deg, 0deg),
    var(--pl-border) var(--ring-deg, 0deg)
  );
  transition: background 0.6s var(--ease-out);
}

/* 링 안쪽을 파내 도넛으로 만든다 — 추가 엘리먼트 없이 배경 한 겹으로. */
.status-hero__ring::before {
  content: "";
  position: absolute;
  inset: clamp(0.5rem, 1.6cqh, 0.9rem);
  border-radius: 50%;
  background: var(--pl-surface);
}

.status-hero__ring[data-tone="passed"] { --ring-color: var(--st-passed-solid); }
.status-hero__ring[data-tone="anomaly"] { --ring-color: var(--st-anomaly-solid); }
.status-hero__ring[data-tone="error"] { --ring-color: var(--st-error-solid); }
.status-hero__ring[data-tone="running"] { --ring-color: var(--st-running-solid); }
.status-hero__ring[data-tone="waiting_input"] { --ring-color: var(--st-waiting_input-solid); }
.status-hero__ring[data-tone="blocked"] { --ring-color: var(--st-blocked-solid); }
.status-hero__ring[data-tone="not_inspected"],
.status-hero__ring[data-tone="pending"] { --ring-color: var(--st-pending-solid); }

.status-hero__figure {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1;
}

.status-hero__value {
  font-size: clamp(1.75rem, 7cqh, 3.5rem);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
}

.status-hero__unit {
  margin-top: 0.25rem;
  font-size: clamp(0.6875rem, 1.6cqh, 0.875rem);
  color: var(--pl-text-muted);
}

.status-hero__headline {
  font-size: clamp(0.875rem, 2.2cqh, 1.125rem);
  font-weight: 700;
  text-wrap: balance;
}

.status-hero__meta {
  font-size: clamp(0.6875rem, 1.4cqh, 0.8125rem);
  color: var(--pl-text-muted);
}

.status-hero__cards {
  display: flex;
  width: 100%;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: clamp(0.25rem, 0.8cqh, 0.5rem);
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .status-hero__ring { transition: none; }
}
```

- [ ] **Step 7: 템플릿을 바꾼다**

`app/web/templates/dashboard/partials/zone_a_kpi.html` 을 다시 쓴다. **기존 문장형 히어로는 삭제하지 않고 `status-hero__headline` 으로 내려 보존한다**(D8). 새로고침 버튼과 htmx 인디케이터도 유지한다.

```jinja
{# Zone A — 지배 상태(숫자 + 진행 링) + KPI 스택. 문장 요약은 링 아래로 보존(D8). #}
{% import "components/kpi-card/macro.jinja" as kpi %}
{% set t = data.totals %}
{% set hero_tone =
     'error' if t.error > 0 else
     'anomaly' if t.anomaly > 0 else
     'running' if t.running > 0 else
     'not_inspected' if t.not_inspected == t.modules else
     'passed' %}
<section id="dash-zone-hero" class="status-hero">
  <div class="status-hero__ring"
       data-tone="{{ hero_tone }}"
       data-passed="{{ t.passed }}"
       data-total="{{ t.modules }}">
    <div class="status-hero__figure">
      <span class="status-hero__value">{{ t.passed }}/{{ t.modules }}</span>
      <span class="status-hero__unit">모듈 정상 · {{ t.pass_rate }}%</span>
    </div>
  </div>

  <h1 class="status-hero__headline">
    {% if t.modules == 0 %}점검 대상이 없습니다
    {% elif t.error > 0 %}점검실패 {{ t.error }}건 — 우선 확인이 필요합니다
    {% elif t.anomaly > 0 %}이상징후 {{ t.anomaly }}건이 감지되었습니다
    {% elif t.running > 0 %}{{ t.running }}개 모듈이 진행 중입니다
    {% elif t.not_inspected == t.modules %}오늘 아직 점검이 시작되지 않았습니다
    {% else %}오늘 점검은 정상입니다
    {% endif %}
  </h1>
  <p class="status-hero__meta">
    {{ data.date_label }}
    {% if data.generated_at %} · 갱신 {{ data.generated_at[11:16] }}{% endif %}
  </p>

  <div class="dash-hero__actions">
    <button id="dash-refresh" type="button" class="dash-refresh" aria-label="새로고침">
      <svg class="dash-refresh__icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
      새로고침
    </button>
    <span id="dash-htmx-busy" class="dash-htmx-indicator">갱신…</span>
  </div>

  <div class="status-hero__cards">
    {% for card in data.cards %}
    {{ kpi.kpi_card(card.key, card.label, card.value, card.unit, card.period, card.note, card.tone, card.href, card.estimated) }}
    {% endfor %}
  </div>
</section>

{% if data.attention %}
<section id="dash-zone-attention" class="dash-attention">
  …기존 attention 블록을 그대로 유지…
</section>
{% endif %}
```

> `kpi.kpi_band(...)` 호출은 사라지고 `kpi_card` 를 직접 반복한다. **매크로 시그니처는 건드리지 않는다**(D2) — 상황판이 같은 매크로를 쓴다.

- [ ] **Step 8: 검증**

```bash
npm run build && npm run typecheck && npm run lint && npm test
python3 scripts/check_frontend_gates.py
python3 -m pytest tests/test_dashboard_fragments_http.py tests/test_dashboard_viewport.py -v
```
Expected: 통과. `hero_tone` 계산이 템플릿 안에 있으므로 **FG-006 이 상태 키 맵으로 오탐하지 않는지** 특히 확인한다. 오탐하면 톤 계산을 `daily_summary.py` 로 옮겨 `data.hero_tone` 으로 주입하고 템플릿에서는 `{{ data.hero_tone }}` 만 쓴다.

- [ ] **Step 9: 커밋**

```bash
git add -A
git commit -m "feat(dashboard): 지배 상태를 숫자+conic-gradient 링으로 — 문장 요약은 보존"
```

---

## Task 8: 매트릭스 행 압축 — 모듈 셀

**Files:**
- Modify: `app/web/templates/dashboard/partials/_macros.html` · `app/web/frontend/components/system-matrix/styles.css` · `app/web/frontend/styles/dashboard.css`
- Test: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: `sys`(`system_code` · `system_name` · `module_total` · `inspected` · `modules[]`), `modules[]`(`module_id` · `name` · `tone` · `status_label` · `run_id` · `duration_ms` · `recovered`), 전역 `system_summary_badge()` · `tone_glyph()`
- Produces: `system_row(sys)` 매크로 — 한 행이 `[코드][이름][셀 × N][n/m]`. 셀 클래스는 `.dash-cell`, 링크 셀은 `.dash-cell--link`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_dashboard_viewport.py` 끝에 추가:

```python
def test_matrix_row_is_single_line_with_cells(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(live_server, wait_until="networkidle")
    shape = page.evaluate(
        """() => {
            const row = document.querySelector('.dash-sys-row');
            if (!row) return null;
            const cells = row.querySelectorAll('.dash-cell');
            const tops = [...cells].map((c) => Math.round(c.getBoundingClientRect().top));
            return {
                cellCount: cells.length,
                sameLine: tops.length > 0 && new Set(tops).size === 1,
                legacyPills: row.querySelectorAll('.dash-mod').length,
                legacySegments: row.querySelectorAll('.dash-seg').length,
            };
        }"""
    )
    assert shape is not None
    assert shape["cellCount"] > 0, "모듈 셀이 없다"
    assert shape["sameLine"], "셀이 한 줄에 있지 않다"
    assert shape["legacyPills"] == 0, "레거시 module_pill 이 남아 있다"
    assert shape["legacySegments"] == 0, "레거시 segment bar 가 남아 있다"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_dashboard_viewport.py::test_matrix_row_is_single_line_with_cells -v`
Expected: FAIL — `.dash-cell` 이 0개

- [ ] **Step 3: 매크로를 다시 쓴다**

`app/web/templates/dashboard/partials/_macros.html` 전체를 아래로 교체한다. `module_pill` · `module_segment_bar` · `module_glyph` 은 사라진다.

```jinja
{# Mission Control 매트릭스 매크로 — 한 행 = 코드 · 이름 · 모듈 셀 · 통과 수. #}

{% macro module_cell(mod) -%}
{% set tone = mod.tone or 'not_inspected' %}
{% set tip = mod.name ~ ' · ' ~ (mod.status_label or '') %}
{%- if mod.run_id -%}
<a href="/runs/{{ mod.run_id }}" class="dash-cell dash-cell--link" data-tone="{{ tone }}" title="{{ tip }}" aria-label="{{ tip }}"><span class="dash-cell__glyph" aria-hidden="true">{{ tone_glyph(tone) }}</span>{% if mod.duration_ms %}<span class="dash-cell__ms" style="--ms-ratio: {{ (mod.duration_ms / 60000) | round(3) }}" aria-hidden="true"></span>{% endif %}{% if mod.recovered %}<span class="dash-cell__flag" title="자동 복구 발생">⟳</span>{% endif %}</a>
{%- else -%}
<span class="dash-cell" data-tone="{{ tone }}" title="{{ tip }}" aria-label="{{ tip }}"><span class="dash-cell__glyph" aria-hidden="true">{{ tone_glyph(tone) }}</span></span>
{%- endif -%}
{%- endmacro %}


{% macro system_row(sys) -%}
{% set badge = system_summary_badge(sys) %}
{% set attention_tones = ['error', 'anomaly', 'running', 'waiting_input', 'blocked'] %}
{% set priority = 'attention' if badge.tone in attention_tones else 'normal' %}
{% set show_cta = badge.tone == 'not_inspected' and sys.inspected == 0 %}
<div class="dash-sys-row"
     data-system-code="{{ sys.system_code }}"
     data-priority="{{ priority }}"
     data-accent-tone="{{ badge.tone }}"
     tabindex="0"
     role="button"
     aria-label="{{ sys.system_name }} 상세 보기">
  <span class="dash-sys-row__icon" data-tone="{{ badge.tone }}">{{ sys.system_code | upper }}</span>
  <span class="dash-sys-row__name">{{ sys.system_name }}</span>
  <div class="dash-sys-row__cells">
    {% for mod in sys.modules %}{{ module_cell(mod) }}{% endfor %}
  </div>
  <span class="dash-sys-row__count">{{ sys.inspected }}/{{ sys.module_total }}</span>
  {% if show_cta %}
  <a href="/runs/execute" class="dash-sys-row__cta" data-action="execute">점검 실행</a>
  {% else %}
  <span class="dash-sys-row__badge" data-tone="{{ badge.tone }}">{{ badge.label }}</span>
  {% endif %}
</div>
{%- endmacro %}
```

- [ ] **Step 4: 스타일을 쓴다**

`app/web/frontend/components/system-matrix/styles.css` 의 자리표시를 지우고 채운다.

```css
/* 시스템 매트릭스 열 — 한 행에 코드·이름·셀·카운트(설계 §3.3). */

.dash-sys-row {
  display: grid;
  min-height: 0;
  flex: 1 1 0;
  /* 코드 · 이름 · 셀 · 카운트 · (뱃지 또는 점검실행 CTA) */
  grid-template-columns: auto minmax(0, 9rem) 1fr auto auto;
  align-items: center;
  gap: clamp(0.375rem, 1cqi, 0.75rem);
  padding: clamp(0.35rem, 1cqh, 0.875rem) clamp(0.5rem, 1.5cqi, 1.25rem);
  border-radius: clamp(0.625rem, 1.2cqh, 1rem);
  background: var(--pl-surface);
  box-shadow: var(--pl-shadow-sm), inset 0 0 0 1px var(--pl-border);
  cursor: pointer;
  overflow: hidden;
  transition: box-shadow 0.15s var(--ease-out), transform 0.15s var(--ease-out);
}

.dash-sys-row:hover {
  box-shadow: var(--pl-shadow-md), inset 0 0 0 1px var(--pl-border);
  transform: translateY(-1px);
}

.dash-sys-row:focus-visible {
  outline: 2px solid var(--st-running-solid);
  outline-offset: 2px;
}

.dash-sys-row__cells {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: clamp(2px, 0.4cqi, 6px);
  overflow: hidden;
}

.dash-cell {
  position: relative;
  display: grid;
  width: clamp(1.125rem, 2.6cqh, 2.25rem);
  min-width: 1.125rem;
  aspect-ratio: 1;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 0.25rem;
  background: var(--st-pending-surface);
  color: var(--pl-text-muted);
  font-size: clamp(0.5rem, 1.2cqh, 0.75rem);
  overflow: hidden;
}

.dash-cell[data-tone="passed"] { background: var(--st-passed-solid); color: var(--c-white); }
.dash-cell[data-tone="anomaly"] { background: var(--st-anomaly-solid); color: var(--c-white); }
.dash-cell[data-tone="error"] { background: var(--st-error-solid); color: var(--c-white); }
.dash-cell[data-tone="running"] { background: var(--st-running-solid); color: var(--c-white); }
.dash-cell[data-tone="waiting_input"] { background: var(--st-waiting_input-solid); color: var(--c-white); }
.dash-cell[data-tone="blocked"] { background: var(--st-blocked-solid); color: var(--c-white); }
.dash-cell[data-tone="skipped"] { background: var(--st-skipped-surface); color: var(--st-skipped-text); }
.dash-cell[data-tone="cancelled"] { background: var(--st-cancelled-surface); color: var(--st-cancelled-text); }
.dash-cell[data-tone="not_inspected"],
.dash-cell[data-tone="pending"] { background: var(--st-pending-surface); color: var(--st-pending-text); }

/* 소요시간 미세 바 — 셀 하단. --ms-ratio 는 분 단위 비율(1분 = 1.0). */
.dash-cell__ms {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 2px;
  width: calc(min(var(--ms-ratio, 0), 1) * 100%);
  background: var(--pl-surface);
  opacity: 0.55;
}

.dash-cell__flag {
  position: absolute;
  top: 0;
  right: 1px;
  font-size: 0.5rem;
  line-height: 1;
}

.dash-sys-row__icon {
  display: grid;
  min-width: 2.25rem;
  padding: 0.2rem 0.4rem;
  place-items: center;
  border-radius: 0.375rem;
  color: var(--c-white);
  font-size: clamp(0.5625rem, 1.2cqh, 0.75rem);
  font-weight: 800;
  letter-spacing: 0.02em;
}

.dash-sys-row__icon[data-tone="passed"] { background: var(--st-passed-solid); }
.dash-sys-row__icon[data-tone="anomaly"] { background: var(--st-anomaly-solid); }
.dash-sys-row__icon[data-tone="error"] { background: var(--st-error-solid); }
.dash-sys-row__icon[data-tone="running"] { background: var(--st-running-solid); }
.dash-sys-row__icon[data-tone="waiting_input"] { background: var(--st-waiting_input-solid); }
.dash-sys-row__icon[data-tone="blocked"] { background: var(--st-blocked-solid); }
.dash-sys-row__icon[data-tone="skipped"] { background: var(--st-skipped-solid); }
.dash-sys-row__icon[data-tone="cancelled"] { background: var(--st-cancelled-solid); }
.dash-sys-row__icon[data-tone="not_inspected"],
.dash-sys-row__icon[data-tone="pending"] { background: var(--st-pending-solid); }

.dash-sys-row__name {
  min-width: 0;
  overflow: hidden;
  font-size: clamp(0.75rem, 1.8cqh, 0.9375rem);
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dash-sys-row__count {
  font-size: clamp(0.6875rem, 1.4cqh, 0.8125rem);
  font-variant-numeric: tabular-nums;
  color: var(--pl-text-muted);
}
```

- [ ] **Step 5: 죽은 CSS 를 지운다**

`app/web/frontend/styles/dashboard.css` 에서 `.dash-mod` · `.dash-seg` · `.cell-flag` · `.dash-sys-row__segment` · `.dash-sys-row__modules` · `.dash-sys-row__header` · `.dash-sys-row__identity` · `.dash-sys-row__text` · `.dash-sys-row__meta` · `.dash-sys-row__chevron` 관련 규칙을 전부 삭제한다. Task 8 이 만든 `system-matrix/styles.css` 로 대체된 것들이다.

**`.dash-sys-row__cta` 와 `.dash-sys-row__badge` 는 삭제하지 않는다** — 새 매크로가 계속 쓴다. 두 규칙을 `system-matrix/styles.css` 로 옮긴다.

확인:

Run: `grep -c "dash-mod\|dash-seg\|cell-flag" app/web/frontend/styles/dashboard.css`
Expected: `0`

- [ ] **Step 6: 검증**

```bash
npm run build && npm run typecheck && npm run lint
python3 scripts/check_frontend_gates.py
python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py -v
```
Expected: 통과. `system_panel.html`(드로어)은 별도 매크로를 쓰지 않으므로 영향이 없어야 한다 — 드로어를 열어 손으로 확인한다.

- [ ] **Step 7: 커밋**

```bash
git add -A
git commit -m "feat(dashboard): 매트릭스 3단 행을 모듈 셀 1행으로 압축 + 소요시간 미세 바"
```

---

## Task 9: 활동 피드 스타일 + 진입 모션

**Files:**
- Modify: `app/web/frontend/components/activity-feed/styles.css`

**Interfaces:**
- Consumes: Task 3 의 `zone_c_activity.html` 마크업 (`.dash-activity` · `__item` · `__time` · `__dot` · `__where` · `__status` · `__recovered` · `__empty`)
- Produces: 없음(스타일 전용)

- [ ] **Step 1: 스타일을 쓴다**

`app/web/frontend/components/activity-feed/styles.css` 의 자리표시를 지우고 채운다.

```css
/* 라이브 활동 피드 열 — 새 항목이 위에서 흘러 들어온다(설계 §3.4). */

.dash-activity {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  gap: clamp(0.25rem, 0.8cqh, 0.5rem);
  padding: clamp(0.625rem, 1.6cqh, 1.125rem);
  border-radius: clamp(0.75rem, 1.4cqh, 1.25rem);
  background: var(--pl-surface);
  box-shadow: var(--pl-shadow-sm), inset 0 0 0 1px var(--pl-border);
}

.dash-activity__eyebrow {
  font-size: clamp(0.625rem, 1.2cqh, 0.75rem);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--pl-text-subtle);
}

.dash-activity__empty {
  display: grid;
  flex: 1 1 auto;
  place-items: center;
  font-size: clamp(0.6875rem, 1.4cqh, 0.8125rem);
  color: var(--pl-text-muted);
  text-align: center;
}

.dash-activity__list {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 1px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dash-activity__item {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  align-items: center;
  gap: 0.5rem;
  padding: clamp(0.3rem, 0.8cqh, 0.5rem) 0.25rem;
  border-radius: 0.375rem;
}

.dash-activity__item + .dash-activity__item {
  box-shadow: inset 0 1px 0 var(--pl-border);
}

.dash-activity__link {
  display: contents;
  color: inherit;
  text-decoration: none;
}

.dash-activity__item:hover {
  background: var(--pl-bg);
}

.dash-activity__time {
  font-size: clamp(0.625rem, 1.2cqh, 0.75rem);
  font-variant-numeric: tabular-nums;
  color: var(--pl-text-subtle);
}

.dash-activity__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--st-pending-solid);
}

.dash-activity__item[data-tone="passed"] .dash-activity__dot { background: var(--st-passed-solid); }
.dash-activity__item[data-tone="anomaly"] .dash-activity__dot { background: var(--st-anomaly-solid); }
.dash-activity__item[data-tone="error"] .dash-activity__dot { background: var(--st-error-solid); }
.dash-activity__item[data-tone="running"] .dash-activity__dot { background: var(--st-running-solid); }
.dash-activity__item[data-tone="waiting_input"] .dash-activity__dot { background: var(--st-waiting_input-solid); }
.dash-activity__item[data-tone="blocked"] .dash-activity__dot { background: var(--st-blocked-solid); }
.dash-activity__item[data-tone="skipped"] .dash-activity__dot { background: var(--st-skipped-solid); }
.dash-activity__item[data-tone="cancelled"] .dash-activity__dot { background: var(--st-cancelled-solid); }

.dash-activity__text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  line-height: 1.25;
}

.dash-activity__where {
  overflow: hidden;
  font-size: clamp(0.6875rem, 1.3cqh, 0.8125rem);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dash-activity__status {
  font-size: clamp(0.625rem, 1.1cqh, 0.75rem);
  color: var(--pl-text-muted);
}

.dash-activity__recovered {
  font-size: 0.75rem;
  color: var(--st-passed-text);
}

/* 진입 — morph 가 새로 삽입한 항목만 애니메이션된다(기존 노드는 보존되므로). */
@starting-style {
  .dash-activity__item {
    opacity: 0;
    transform: translateY(-6px);
  }
}

.dash-activity__item {
  transition: opacity 0.35s var(--ease-out), transform 0.35s var(--ease-out),
    background 0.15s var(--ease-out);
}

@media (prefers-reduced-motion: reduce) {
  .dash-activity__item { transition: background 0.15s var(--ease-out); }
  @starting-style {
    .dash-activity__item { opacity: 1; transform: none; }
  }
}
```

- [ ] **Step 2: 검증**

```bash
npm run build
python3 scripts/check_frontend_gates.py
python3 -m pytest tests/test_dashboard_viewport.py -v
```
Expected: 통과. FG-002(hex 0) 특히 확인.

- [ ] **Step 3: 실물 확인**

앱을 띄우고 대시보드에서 활동 피드가 우측 열에 렌더되는지, 항목이 시각 내림차순인지, `⟳` 가 복구된 항목에만 붙는지 확인한다.

- [ ] **Step 4: 커밋**

```bash
git add -A
git commit -m "feat(dashboard): 활동 피드 스타일 + 진입 모션(@starting-style)"
```

---

## Task 10: 상태 전이 모션 + 지속 모션

**Files:**
- Modify: `app/web/frontend/components/system-matrix/styles.css`

**Interfaces:**
- Consumes: Task 8 의 `.dash-cell[data-tone]`
- Produces: 없음(스타일 전용)

- [ ] **Step 1: 모션을 더한다**

`app/web/frontend/components/system-matrix/styles.css` 끝에 추가한다.

```css
/* ── 모션 4계층 중 전이·지속(설계 §3.5) ──
   morph 가 노드를 보존하므로 data-tone 변화가 transition 을 탄다. */

.dash-cell {
  transition: background-color 0.4s var(--ease-out), color 0.4s var(--ease-out);
}

/* 진행 중 — shimmer. 맥동은 waiting_input 만 쓴다(wall.css 결정 승계). */
@keyframes dash-cell-shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.62; }
}

.dash-cell[data-tone="running"] {
  animation: dash-cell-shimmer 1.8s ease-in-out infinite;
}

@keyframes dash-cell-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.92); }
}

.dash-cell[data-tone="waiting_input"] {
  animation: dash-cell-pulse 1.4s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .dash-cell {
    transition: none;
    animation: none;
  }
}
```

- [ ] **Step 2: 실패하지 않는지 확인한다**

```bash
npm run build
python3 scripts/check_frontend_gates.py
python3 -m pytest tests/test_dashboard_viewport.py -v
```
Expected: 통과

- [ ] **Step 3: reduced-motion 을 실제로 확인한다**

Playwright 로 확인한다. `tests/test_dashboard_viewport.py` 끝에 추가:

```python
def test_reduced_motion_disables_cell_animation(browser, live_server: str) -> None:
    context = browser.new_context(reduced_motion="reduce", viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    page.goto(live_server, wait_until="networkidle")
    names = page.evaluate(
        """() => [...document.querySelectorAll('.dash-cell')]
            .map((c) => getComputedStyle(c).animationName)"""
    )
    context.close()
    assert names, "셀이 없다"
    assert all(name == "none" for name in names), f"reduced-motion 인데 애니메이션이 산다: {names}"
```

Run: `python3 -m pytest tests/test_dashboard_viewport.py::test_reduced_motion_disables_cell_animation -v`
Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add -A
git commit -m "feat(dashboard): 셀 상태 전이·지속 모션 + reduced-motion 전면 정지"
```

---

## Task 11: CSS 컴포넌트 분할 마무리 + FG-004 allowlist 정리

**Files:**
- Modify: `app/web/frontend/styles/dashboard.css` · `scripts/check_frontend_gates.py`
- Test: `tests/frontend/test_frontend_gates.py`

**Interfaces:**
- Consumes: Task 7~10 이 만든 세 컴포넌트 스타일시트
- Produces: `dashboard.css` 400줄 이하 → `FG004_ALLOWLIST` 에서 제거

- [ ] **Step 1: 현재 줄 수를 잰다**

Run: `wc -l app/web/frontend/styles/dashboard.css app/web/frontend/components/*/styles.css`

`dashboard.css` 가 400줄을 넘으면 Step 2 로, 이미 이하면 Step 3 으로 간다.

- [ ] **Step 2: 남은 블록을 컴포넌트로 옮긴다**

`dashboard.css` 에 남아야 하는 것은 **레이아웃 골격뿐**이다: `body:has(.dash)` 미디어쿼리 · `.dash` 그리드 · 세 호스트 · `.dash__systems` · `.dash__empty` · `#dash-error` · 드로어(`.dash-drawer*`) · `.dash-refresh` · `.dash-htmx-indicator`.

그 외는 옮긴다:
- `.dash-attention*` → `app/web/frontend/components/activity-feed/styles.css` 끝(같은 "무슨 일이 있었나" 계열이다)
- `.dash-panel*`(드로어 내용) → `app/web/frontend/components/system-matrix/styles.css` 끝

각 이동 후 빌드해 화면이 그대로인지 확인한다:

Run: `npm run build && python3 -m pytest tests/test_dashboard_viewport.py -v`

- [ ] **Step 3: allowlist 에서 지운다**

`scripts/check_frontend_gates.py` 의 `FG004_ALLOWLIST` 에서 `"app/web/frontend/styles/dashboard.css",` 한 줄을 삭제한다. `app.css` 는 남긴다(P4 의 몫).

- [ ] **Step 4: 게이트가 통과하는지 확인한다**

```bash
python3 scripts/check_frontend_gates.py
python3 -m pytest tests/frontend/ -v
```
Expected: 통과. FG-004 가 `dashboard.css` 와 세 컴포넌트 모두를 400줄 이하로 확인해야 한다.

- [ ] **Step 5: 전체 게이트를 돌린다**

```bash
npm run build && npm run typecheck && npm run lint && npm test
python3 scripts/ci/run_all_gates.py --profile full
```
Expected: 전부 통과

- [ ] **Step 6: 커밋**

```bash
git add -A
git commit -m "refactor(web): dashboard.css 를 컴포넌트 3종으로 분할 — FG-004 allowlist 1건 감소"
```

---

## 완료 확인

1단계가 끝났을 때 아래가 전부 참이어야 한다(스펙 §2.3).

- [ ] 1366 · 1920 · 2560 px 에서 세로 스크롤바 0, 활동 피드 열만 내부 스크롤
- [ ] 세 존 모두 `hx-swap="morph:innerHTML"`, `hx-swap="innerHTML"` 0건
- [ ] 폴링 갱신 후 `.dash-sys-row` stagger 재생 없음
- [ ] `dashboard.js` 파일 부재, `data-density` 0건, 인라인 `flex` 0건
- [ ] `FG005_ALLOWLIST` 에서 `/static/dashboard.js` 제거됨
- [ ] `FG004_ALLOWLIST` 에서 `dashboard.css` 제거됨
- [ ] "갱신 HH:MM" 이 스케줄 타임존 기준 시각(대시보드·상황판 공통)
- [ ] 드로어를 연 채 갱신해도 닫히지 않음
- [ ] KPI 카운트업이 값이 바뀐 카드에서 재생됨
- [ ] `prefers-reduced-motion: reduce` 에서 셀 애니메이션 정지
- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과

**2단계(타입 스케일)·3단계(차트 통합)는 이 계획의 범위가 아니다.** 스펙 §3.7 · §3.8 을 각각 별도 계획으로 만든다.
