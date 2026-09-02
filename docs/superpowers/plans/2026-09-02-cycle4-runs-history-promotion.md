# Run 이력 승격 (Cycle 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run 이력 화면의 지배 요소를 "실행된 것만 그리는 목록"에서 **시스템 × 7일 커버리지 격자**로 바꿔, 점검이 **안 돌아간 날·시스템이 화면에 드러나게** 한다.

**Architecture:** 새 read model 을 만들지 않는다. 관리자 전용이던 커버리지 매트릭스(`build_admin_coverage_dashboard`)를 쿼리 계층에 시스템 필터를 더해 사용자 권한으로 재사용하고, 화면은 `app/web/frontend/runs-history/` 로 승격한다. 드릴다운은 셀에 실린 대표 `run_id` 가 아니라 별도 조회로 그 날·그 시스템의 Run 전량을 가져온다.

**Tech Stack:** FastAPI · Jinja2 · TypeScript 5.6 · Vite 6(다중 엔트리) · Vitest 3 + jsdom · pytest · Playwright

**Spec:** `docs/superpowers/specs/2026-09-02-runs-history-promotion-design.md`

## Global Constraints

- **SPA 로 만들지 않는다.** 서버 렌더 + 엔트리 스크립트. React·Vue·차트/모션 라이브러리 추가 금지.
- **색은 SSOT 에서만.** `app/core/status_colors.py` `PALETTE` → `tokens.generated.css` 의 `--st-{tone}-{solid|surface|text|border}`. 템플릿·TS·CSS 에 hex 리터럴 금지(FG-002).
- **`PALETTE` 에 톤을 추가하지 않는다.** 커버리지의 `not_checked` 는 관리자 히트맵 선례(`app/web/templates/admin/index.html:194`)대로 `--st-pending-surface` · `--st-pending-border` 를 쓴다.
- **상태 라벨은 서버가 준 `status_label` 을 그대로 쓴다.** TS 에 상태→한글 맵을 만들지 않는다(FG-003).
- **파일 400줄 상한**(FG-004). `runs-history/` 의 어떤 파일도 넘지 않는다.
- **`/static/` 직접 참조 금지**(FG-005). 새 템플릿 코드는 `_assets.html` 매크로만 쓴다.
- **템플릿에 상태→표현 맵 금지**(FG-006).
- **`execute.html` 의 "진행 중 / 최근 Run" 은 회귀 없이 그대로 동작해야 한다.** `app.js` 의 스트립 8함수 · `createRunListItem` · `bindRunsOverview` · `refreshRunList` · `renderRunList` · `formatRunTimestamp` 를 **삭제하지 않는다**(D10).
- **`/api/admin/dashboard` 의 응답과 `require_admin` 가드는 바뀌지 않는다.**
- 커밋은 태스크마다. 커밋 메시지 본문은 한국어, 식별자·경로는 원문.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `app/orchestrator/queries/admin_dashboard_queries.py` (수정) | `get_coverage_dashboard(system_codes=…)` — 시스템 축 필터 |
| `app/api/routes_runs.py` (수정) | `GET /api/runs/coverage` · `GET /api/runs/day` 두 라우트 |
| `app/web/templates/runs_history.html` (재작성) | 격자 + 드릴다운 골격, JS 훅만 |
| `app/web/frontend/runs-history/coverage.ts` (신규) | 커버리지 응답 → 하루 한 칸 격자 모델·렌더 |
| `app/web/frontend/runs-history/drilldown.ts` (신규) | 셀 선택 · 목록 조회 · 렌더 |
| `app/web/frontend/runs-history/format.ts` (신규) | `formatRunTime` — `app.js` 에서 복제 |
| `app/web/frontend/runs-history/styles.css` (신규) | 격자 · 드릴다운 CSS |
| `app/web/frontend/entries/runs-history.ts` (신규) | 배선만 |
| `app/web/frontend/styles/shell.css` (수정) | 다섯 번째 소비자 — 셀렉터 목록화 |
| `vite.config.ts` (수정) | 엔트리 1줄 |
| `app/web/static/app.js` (수정) | `bindRunsHistory` · `RUN_HISTORY_LIMIT` · 호출 제거 |

**태스크 순서:** 서버(1–2) → 셸(3) → 격자(4–5) → 드릴다운(6–7) → 배선·템플릿(8) → 레거시 절단(9) → 좌표 계약(10) → 게이트(11).

---

### Task 1: 커버리지 쿼리에 시스템 축 필터

**Files:**
- Modify: `app/orchestrator/queries/admin_dashboard_queries.py:61-76`
- Test: `tests/test_admin_coverage_dashboard.py`

**Interfaces:**
- Produces: `AdminDashboardQueries.get_coverage_dashboard(*, system_codes: frozenset[str] | None = None) -> dict[str, Any]` — `None` 이면 전 시스템(기존 동작 불변).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_admin_coverage_dashboard.py` 끝에 추가한다. 그 파일이 이미 쓰는 가짜 registry·summary query 구성 방식을 그대로 따르고, 아래 두 헬퍼가 없으면 기존 테스트의 구성 코드를 그대로 뽑아 만든 뒤 기존 테스트도 그것을 쓰게 고친다(동작 변경 없음).

```python
@pytest.mark.asyncio
async def test_coverage_dashboard_filters_by_system_codes():
    queries = _build_queries(
        systems=[_system("hom", "HOM", 1), _system("mhm", "MHM", 2)],
        rows=[],
    )

    scoped = await queries.get_coverage_dashboard(system_codes=frozenset({"hom"}))

    assert [s["system_code"] for s in scoped["systems"]] == ["hom"]
    assert scoped["totals"]["systems"] == 1


@pytest.mark.asyncio
async def test_coverage_dashboard_without_filter_keeps_all_systems():
    queries = _build_queries(
        systems=[_system("hom", "HOM", 1), _system("mhm", "MHM", 2)],
        rows=[],
    )

    everything = await queries.get_coverage_dashboard()

    assert [s["system_code"] for s in everything["systems"]] == ["hom", "mhm"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/test_admin_coverage_dashboard.py -v`
Expected: FAIL — `get_coverage_dashboard() got an unexpected keyword argument 'system_codes'`

- [ ] **Step 3: 최소 구현**

`get_coverage_dashboard` 를 이렇게 고친다.

```python
    async def get_coverage_dashboard(
        self, *, system_codes: frozenset[str] | None = None
    ) -> dict[str, Any]:
        tz = _schedule_tz()
        now = datetime.now(UTC)
        since = coverage_window_start_utc(now, tz)
        rows = await self._list_summaries_since(since)
        run_rows = [
            CoverageRunRow(
                run_id=row.run_id,
                system_code=row.system_code,
                status=row.status,
                requested_at=row.requested_at,
            )
            for row in rows
            if system_codes is None or row.system_code in system_codes
        ]
        systems = [
            system
            for system in self._registry.list_systems()
            if system_codes is None or system.system_code in system_codes
        ]
        return build_admin_coverage_dashboard(systems, run_rows, now=now, tz=tz)
```

빌더(`build_admin_coverage_dashboard`)는 손대지 않는다 — 필터는 쿼리 계층의 책임이다(설계 D2).

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/test_admin_coverage_dashboard.py tests/test_admin_dashboard_runs.py -v`
Expected: PASS — 신규 2건 포함, 기존 전부 유지

- [ ] **Step 5: 커밋**

```bash
git add app/orchestrator/queries/admin_dashboard_queries.py tests/test_admin_coverage_dashboard.py
git commit -m "feat(runs-history): 커버리지 쿼리에 시스템 축 필터 추가"
```

---

### Task 2: 사용자용 커버리지·드릴다운 라우트

**Files:**
- Modify: `app/api/routes_runs.py` — `list_runs`(`:21-33`) 바로 아래
- Test: `tests/test_runs_coverage_api.py` (신규)

**Interfaces:**
- Consumes: Task 1 의 `get_coverage_dashboard(system_codes=…)`
- Produces:
  - `GET /api/runs/coverage` → Task 1 의 dict 그대로
  - `GET /api/runs/day?system_code=<code>&day=<YYYY-MM-DD>` → `list[dict]` — `summarize_row` 결과에서 `created_by_user_id` · `created_by_user_name` 를 뺀 것

**라우트 등록 순서 주의:** `routes_runs.py` 에는 `@router.get("/{run_id}")` 계열 경로가 있다. `/coverage` 와 `/day` 는 **그보다 위**에 선언해야 `run_id` 로 잡아먹히지 않는다. `@router.get("")` 바로 아래에 넣는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_runs_coverage_api.py` 를 새로 만든다.

```python
"""사용자용 커버리지·드릴다운 라우트 — 권한 축과 노출 필드 계약(설계 D2·D8·D9)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_admin_dashboard_queries, get_run_queries
from app.api.routes_runs import router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User


class _StubAdminQueries:
    def __init__(self) -> None:
        self.seen: frozenset[str] | None = None

    async def get_coverage_dashboard(self, *, system_codes=None):
        self.seen = system_codes
        return {"systems": [], "columns": [], "totals": {}, "window": {}}


class _StubRunQueries:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def list_run_summaries_page(self, **kwargs):
        self.kwargs = kwargs
        return {
            "items": [
                {
                    "run_id": "run_1",
                    "system_code": "hom",
                    "status": "passed",
                    "status_label": "정상",
                    "requested_at": datetime(2026, 9, 1, 13, 0, tzinfo=UTC).isoformat(),
                    "module_total": 3,
                    "module_passed": 3,
                    "suite_id": None,
                    "created_by_user_id": "u_other",
                    "created_by_user_name": "다른 사용자",
                }
            ],
            "total": 1,
        }


def _user() -> User:
    return User(
        user_id="u_1",
        name="사용자",
        email="user@example.com",
        role="user",
        allowed_system_codes=["hom"],
    )


def _client(admin_queries, run_queries) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_admin_dashboard_queries] = lambda: admin_queries
    app.dependency_overrides[get_run_queries] = lambda: run_queries
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_coverage_scopes_to_allowed_systems():
    admin_queries = _StubAdminQueries()
    async with _client(admin_queries, _StubRunQueries()) as client:
        response = await client.get("/api/runs/coverage")

    assert response.status_code == 200
    assert admin_queries.seen == frozenset({"hom"})


@pytest.mark.asyncio
async def test_day_rejects_system_outside_permission():
    async with _client(_StubAdminQueries(), _StubRunQueries()) as client:
        response = await client.get(
            "/api/runs/day", params={"system_code": "mhm", "day": "2026-09-01"}
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_day_hides_actor_fields():
    async with _client(_StubAdminQueries(), _StubRunQueries()) as client:
        response = await client.get(
            "/api/runs/day", params={"system_code": "hom", "day": "2026-09-01"}
        )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["run_id"] == "run_1"
    assert "created_by_user_name" not in item
    assert "created_by_user_id" not in item


@pytest.mark.asyncio
async def test_day_filters_by_system_not_requester():
    run_queries = _StubRunQueries()
    async with _client(_StubAdminQueries(), run_queries) as client:
        await client.get("/api/runs/day", params={"system_code": "hom", "day": "2026-09-01"})

    assert run_queries.kwargs["system_code"] == "hom"
    assert run_queries.kwargs.get("user_id") is None
```

마지막 테스트가 D8 의 핵심이다 — 요청자 축으로 거르면 **예약 실행 Run 이 목록에서 사라져 격자와 어긋난다.**

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/test_runs_coverage_api.py -v`
Expected: FAIL — 404(라우트 없음)

- [ ] **Step 3: 최소 구현**

`app/api/routes_runs.py` 의 `list_runs` 바로 아래에 넣고, import 는 파일 상단에 더한다.

```python
from datetime import UTC, datetime, timedelta

from app.api.dependencies import get_admin_dashboard_queries
from app.orchestrator.queries.admin_dashboard_queries import (
    AdminDashboardQueries,
    _schedule_tz,
)

_ACTOR_FIELDS = ("created_by_user_id", "created_by_user_name")


def _permitted_codes(user: User) -> frozenset[str] | None:
    """admin 은 전 시스템, 그 외는 허용 목록. None 은 '필터 없음'."""
    if user.role == "admin":
        return None
    return frozenset(user.allowed_system_codes)


@router.get("/coverage")
async def runs_coverage(
    current_user: User = Depends(get_current_user),
    admin_queries: AdminDashboardQueries = Depends(get_admin_dashboard_queries),
):
    """시스템 x 7일 점검 커버리지(사용자 권한 범위, PII 없음)."""
    return await admin_queries.get_coverage_dashboard(system_codes=_permitted_codes(current_user))


@router.get("/day")
async def runs_of_day(
    system_code: str,
    day: str,
    current_user: User = Depends(get_current_user),
    run_queries: RunQueries = Depends(get_run_queries),
):
    """격자 셀 드릴다운 — 그 날 그 시스템의 Run 전량.

    셀에 실린 대표 run_id 를 쓰지 않는 이유는 서버가 슬롯당 한 건으로 접기
    때문이다(설계 D4). 권한 축은 격자와 같은 시스템 축이고(D8), 실행자
    필드는 싣지 않는다(D9).
    """
    permitted = _permitted_codes(current_user)
    if permitted is not None and system_code not in permitted:
        raise HTTPException(status_code=403, detail="해당 시스템에 대한 접근 권한이 없습니다.")
    try:
        day_start_local = datetime.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="day 는 YYYY-MM-DD 형식이어야 합니다.") from exc
    tz = _schedule_tz()
    since = day_start_local.replace(tzinfo=tz).astimezone(UTC)
    before = since + timedelta(days=1)
    page = await run_queries.list_run_summaries_page(
        limit=200,
        system_code=system_code,
        requested_since=since,
        requested_before=before,
    )
    return [
        {key: value for key, value in item.items() if key not in _ACTOR_FIELDS}
        for item in page["items"]
    ]
```

`get_admin_dashboard_queries` 는 `app/api/dependencies.py:62` 에 있다 — `get_run_queries` 와 같은 모듈이므로 기존 import 줄에 이름만 더하면 된다. `AdminDashboardQueries` 타입은 `routes_admin.py:12` 가 쓰는 경로를 그대로 따른다.

`_schedule_tz` 가 비공개 이름이라 import 가 걸리면, `admin_dashboard_queries.py` 에서 밑줄을 떼어 공개 함수로 올리고 그 파일 안의 호출부도 함께 고친다 — **타임존 판정 로직을 복제하지 않는다.**

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/test_runs_coverage_api.py tests/test_admin_runs_api.py tests/test_run_list_scope.py -v`
Expected: PASS — 신규 4건 + 기존 회귀 없음

- [ ] **Step 5: 관리자 경로 불변을 확인한다**

Run: `python -m pytest tests/test_admin_coverage_dashboard.py tests/test_admin_dashboard_runs.py tests/test_admin_runs_http.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/api/routes_runs.py app/orchestrator/queries/admin_dashboard_queries.py tests/test_runs_coverage_api.py
git commit -m "feat(runs-history): 사용자용 커버리지/드릴다운 라우트 추가"
```

---

### Task 3: 넌스크롤 셸 다섯 번째 소비자

**Files:**
- Modify: `app/web/frontend/styles/shell.css` (전체 교체)
- Test: 기존 `tests/test_dashboard_viewport.py` · `test_execute_viewport.py` · `test_suite_viewport.py` · `test_run_viewport.py` 회귀

**Interfaces:**
- Produces: `.rhist` 루트 클래스가 넌스크롤 셸 규칙을 받는다.

- [ ] **Step 1: 셀렉터를 목록으로 접는다**

지금은 소비자 4개를 블록마다 나열해 같은 규칙이 4번씩 반복된다. 다섯 번째를 같은 방식으로 더하면 25줄이 또 붙는다. `:has()` 는 셀렉터 목록을 받으므로 접는다. 파일 전체를 아래로 교체한다.

```css
/* 넌스크롤 셸 — 관제탑 화면 공통(설계 D7).

   .dash(일간 대시보드) · .exec(점검 실행) · .suite(수트 상세) · .run(런 상세) ·
   .rhist(Run 이력)가 같은 규칙을 쓴다. 소비자가 다섯이 되면서 블록마다
   나열하던 것을 :has() 셀렉터 목록으로 접었다 — 여섯 번째는 목록에만
   추가하면 된다. */

body:has(.dash, .exec, .suite, .run, .rhist) {
  overflow: hidden;
  height: 100dvh;
  max-height: 100dvh;
  min-height: 0;
}

body:has(.dash, .exec, .suite, .run, .rhist) main,
body:has(.dash, .exec, .suite, .run, .rhist) main > div {
  max-width: none;
  padding-top: 0;
  padding-right: 0;
  padding-bottom: 0;
  height: 100dvh;
  overflow: hidden;
  box-sizing: border-box;
}

/* .dash 고유 — 셸이 아니라 대시보드의 컨테이너 컨텍스트다. 테스트가
   dashboard.css 에서 body:has( 를 금지해 여기에만 둔다. */
body:has(.dash) main > div {
  container-type: inline-size;
  container-name: dash-shell;
}

@media (min-width: 768px) {
  body:has(.dash, .exec, .suite, .run, .rhist) main {
    padding-left: 16rem;
    width: 100%;
  }

  body:has(.dash, .exec, .suite, .run, .rhist) main > div {
    padding-left: 0;
    width: 100%;
    max-width: none;
  }
}

@media (max-width: 767px) {
  body:has(.dash, .exec, .suite, .run, .rhist) {
    display: flex;
    flex-direction: column;
  }

  body:has(.dash, .exec, .suite, .run, .rhist) > header {
    flex-shrink: 0;
  }

  body:has(.dash, .exec, .suite, .run, .rhist) main {
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    overflow: hidden;
  }

  body:has(.dash, .exec, .suite, .run, .rhist) main > div {
    height: 100%;
    overflow: hidden;
  }

  body:has(.dash, .exec, .suite, .run, .rhist) main,
  body:has(.dash, .exec, .suite, .run, .rhist) main > div {
    padding-left: 0;
    width: 100%;
  }
}
```

- [ ] **Step 2: 기존 네 화면의 좌표 계약이 그대로인지 확인한다**

Run: `python -m pytest tests/test_dashboard_viewport.py tests/test_execute_viewport.py tests/test_suite_viewport.py tests/test_run_viewport.py -v`
Expected: PASS — 넷 다 회귀 없음.

**하나라도 깨지면 이 리팩터링을 되돌리고**, 기존 방식대로 블록마다 `.rhist` 셀렉터를 나열하는 것으로 바꾼다. 이 태스크의 목적은 다섯 번째 소비자를 얹는 것이지 리팩터링 자체가 아니다.

- [ ] **Step 3: 커밋**

```bash
git add app/web/frontend/styles/shell.css
git commit -m "refactor(shell): :has() 셀렉터 목록화 후 .rhist 추가"
```

---

### Task 4: 커버리지 격자 모델 — 하루 한 칸 · 2단계 톤 규칙

**Files:**
- Create: `app/web/frontend/runs-history/coverage.ts`
- Test: `app/web/frontend/runs-history/coverage.test.ts`

**Interfaces:**
- Produces:

```ts
export type CoverageCell = { day_key: string; slot_id: string; status: string; status_label: string | null; tone: string | null; run_id: string | null; checked_at: string | null };
export type CoverageSystem = { system_code: string; system_name: string; cells: CoverageCell[] };
export type CoverageResponse = { window: { day_keys: string[] }; systems: CoverageSystem[] };
export type DayCell = { day_key: string; tone: string; slots: string[]; ran: number };
export type GridRow = { system_code: string; system_name: string; days: DayCell[] };
export function buildGrid(payload: CoverageResponse): GridRow[];
export function renderGrid(root: HTMLElement, rows: GridRow[], dayKeys: string[]): void;
```

`DayCell.tone` 은 셀 대표 톤, `slots` 는 그 날 슬롯 톤 배열(색 조각용, 서버가 준 순서 그대로), `ran` 은 실제로 돈 슬롯 수.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```ts
import { describe, expect, it } from "vitest";
import { buildGrid, renderGrid } from "./coverage";

const cell = (day: string, slot: string, tone: string | null, status: string) => ({
  day_key: day,
  slot_id: slot,
  status,
  status_label: null,
  tone,
  run_id: null,
  checked_at: null,
});

const payload = (cells: ReturnType<typeof cell>[]) => ({
  window: { day_keys: ["2026-09-01", "2026-09-02"] },
  systems: [{ system_code: "hom", system_name: "HOM", cells }],
});

describe("buildGrid", () => {
  it("하루 3슬롯이 모두 비면 not_checked 다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "not_checked", "not_checked"),
      cell("2026-09-01", "afternoon", "not_checked", "not_checked"),
      cell("2026-09-01", "evening", "not_checked", "not_checked"),
    ]));

    expect(rows[0].days[0].tone).toBe("not_checked");
    expect(rows[0].days[0].ran).toBe(0);
  });

  it("한 슬롯만 돌고 둘이 비면 그 슬롯의 톤을 따른다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "not_checked", "not_checked"),
      cell("2026-09-01", "evening", "not_checked", "not_checked"),
    ]));

    expect(rows[0].days[0].tone).toBe("passed");
    expect(rows[0].days[0].ran).toBe(1);
  });

  it("돌아간 것들 중 최악을 고른다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "error", "error"),
      cell("2026-09-01", "evening", "anomaly", "anomaly"),
    ]));

    expect(rows[0].days[0].tone).toBe("error");
  });

  it("anomaly 는 passed 를 이긴다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "anomaly", "anomaly"),
    ]));

    expect(rows[0].days[0].tone).toBe("anomaly");
  });

  it("running 은 passed 보다 앞선다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-02", "morning", "passed", "passed"),
      cell("2026-09-02", "afternoon", "running", "running"),
    ]));

    expect(rows[0].days[1].tone).toBe("running");
  });

  it("응답에 없는 날도 열을 만든다", () => {
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "passed", "passed")]));

    expect(rows[0].days.map((d) => d.day_key)).toEqual(["2026-09-01", "2026-09-02"]);
    expect(rows[0].days[1].tone).toBe("not_checked");
  });

  it("슬롯 톤을 순서대로 보존한다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "error", "error"),
    ]));

    expect(rows[0].days[0].slots).toEqual(["passed", "error"]);
  });
});

describe("renderGrid", () => {
  it("셀에 톤과 좌표를 data 속성으로 싣는다", () => {
    const root = document.createElement("div");
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "error", "error")]));

    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);

    const target = root.querySelector<HTMLElement>('[data-day="2026-09-01"][data-system="hom"]');
    expect(target).not.toBeNull();
    expect(target!.dataset.tone).toBe("error");
  });

  it("다시 그려도 셀이 쌓이지 않는다", () => {
    const root = document.createElement("div");
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "passed", "passed")]));

    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);
    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);

    expect(root.querySelectorAll("[data-day]").length).toBe(2);
  });

  it("시스템이 하나여도 성립한다", () => {
    const root = document.createElement("div");
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "passed", "passed")]));

    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);

    expect(root.querySelectorAll("[data-system]").length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npx vitest run app/web/frontend/runs-history/coverage.test.ts`
Expected: FAIL — `Cannot find module './coverage'`

- [ ] **Step 3: 최소 구현**

```ts
/** 커버리지 응답(시스템 x 21슬롯) → 화면 격자(시스템 x 7일).
 *
 *  하루를 한 칸으로 접되 슬롯 톤은 조각으로 보존한다(설계 D5). 대표 톤은
 *  2단계다(D6): 3슬롯이 모두 비면 not_checked, 하나라도 돌았으면 돌아간
 *  것들 중 최악. 단순 최악 규칙이면 시스템당 하루 1 Run 인 현 운영에서
 *  정상인 날도 전부 미실행으로 보인다. */

export type CoverageCell = {
  day_key: string;
  slot_id: string;
  status: string;
  status_label: string | null;
  tone: string | null;
  run_id: string | null;
  checked_at: string | null;
};

export type CoverageSystem = {
  system_code: string;
  system_name: string;
  cells: CoverageCell[];
};

export type CoverageResponse = {
  window: { day_keys: string[] };
  systems: CoverageSystem[];
};

export type DayCell = { day_key: string; tone: string; slots: string[]; ran: number };
export type GridRow = { system_code: string; system_name: string; days: DayCell[] };

const NOT_CHECKED = "not_checked";

/** 나쁜 것이 먼저 눈에 들어와야 한다 — 앞일수록 나쁘다. */
const SEVERITY = [
  "error",
  "anomaly",
  "waiting_input",
  "running",
  "blocked",
  "cancelled",
  "skipped",
  "passed",
];

function worst(tones: string[]): string {
  for (const tone of SEVERITY) {
    if (tones.includes(tone)) {
      return tone;
    }
  }
  return tones[0] ?? NOT_CHECKED;
}

export function buildGrid(payload: CoverageResponse): GridRow[] {
  const dayKeys = payload.window.day_keys;
  return payload.systems.map((system) => {
    const byDay = new Map<string, CoverageCell[]>();
    for (const cell of system.cells) {
      const bucket = byDay.get(cell.day_key);
      if (bucket) {
        bucket.push(cell);
      } else {
        byDay.set(cell.day_key, [cell]);
      }
    }

    const days = dayKeys.map((dayKey) => {
      const slots = (byDay.get(dayKey) ?? []).map((cell) => cell.tone ?? NOT_CHECKED);
      const ranTones = slots.filter((tone) => tone !== NOT_CHECKED);
      return {
        day_key: dayKey,
        tone: ranTones.length === 0 ? NOT_CHECKED : worst(ranTones),
        slots,
        ran: ranTones.length,
      };
    });

    return { system_code: system.system_code, system_name: system.system_name, days };
  });
}

export function renderGrid(root: HTMLElement, rows: GridRow[], dayKeys: string[]): void {
  root.replaceChildren();
  root.style.setProperty("--rhist-days", String(dayKeys.length));

  const corner = document.createElement("div");
  corner.className = "rhist-grid__corner";
  root.appendChild(corner);

  for (const dayKey of dayKeys) {
    const head = document.createElement("div");
    head.className = "rhist-grid__day";
    head.textContent = dayKey.slice(5).replace("-", "/");
    root.appendChild(head);
  }

  for (const row of rows) {
    const name = document.createElement("div");
    name.className = "rhist-grid__system";
    name.textContent = row.system_name;
    root.appendChild(name);

    for (const day of row.days) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "rhist-cell";
      cell.dataset.tone = day.tone;
      cell.dataset.day = day.day_key;
      cell.dataset.system = row.system_code;
      cell.setAttribute(
        "aria-label",
        `${row.system_name} ${day.day_key} ${day.ran === 0 ? "미실행" : `${day.ran}건`}`,
      );

      for (const slotTone of day.slots) {
        const piece = document.createElement("span");
        piece.className = "rhist-cell__slot";
        piece.dataset.tone = slotTone;
        cell.appendChild(piece);
      }

      root.appendChild(cell);
    }
  }
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `npx vitest run app/web/frontend/runs-history/coverage.test.ts`
Expected: PASS — 10건

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/runs-history/coverage.ts app/web/frontend/runs-history/coverage.test.ts
git commit -m "feat(runs-history): 커버리지 격자 모델과 렌더"
```

---

### Task 5: 격자·드릴다운 CSS

**Files:**
- Create: `app/web/frontend/runs-history/styles.css`
- Test: 단위 테스트 없음 — Task 10 의 좌표 계약이 검증한다

**Interfaces:**
- Consumes: Task 4 가 붙이는 클래스와 `data-tone`
- Produces: `.rhist` 루트 · `.rhist-grid` · `.rhist-cell` · `.rhist-legend` · `.rhist-drill`

- [ ] **Step 1: 스타일시트를 쓴다**

hex 리터럴을 쓰지 않는다. `not_checked` 는 `--st-pending-*` 을 쓴다(관리자 히트맵 선례).

```css
/* Run 이력 — 시스템 x 7일 격자 + 드릴다운(설계 §3.1).
   격자는 고정, 스크롤은 드릴다운 하나만 갖는다(스크롤 소유권). */

.rhist {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 1rem;
  height: 100%;
  min-height: 0;
  padding: 1.25rem 1.5rem;
  box-sizing: border-box;
}

.rhist-crumb {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--st-pending-text);
}

.rhist-head__title {
  margin-top: 0.25rem;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.rhist-head__sub {
  margin-top: 0.375rem;
  font-size: 0.875rem;
  color: var(--st-pending-text);
}

.rhist-grid {
  display: grid;
  grid-template-columns: minmax(6rem, auto) repeat(var(--rhist-days, 7), minmax(0, 1fr));
  gap: 0.375rem;
  align-items: stretch;
}

.rhist-grid__day,
.rhist-grid__system {
  display: flex;
  align-items: center;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--st-pending-text);
}

.rhist-grid__day {
  justify-content: center;
}

.rhist-cell {
  display: flex;
  gap: 2px;
  min-height: 2.75rem;
  padding: 3px;
  border-radius: 0.5rem;
  border: 1px solid var(--st-pending-border);
  background: var(--st-pending-surface);
  cursor: pointer;
}

/* 미실행은 이 화면의 주인공이다 — 파선으로 "비어 있음"을 말한다. */
.rhist-cell[data-tone="not_checked"] {
  border-style: dashed;
}

.rhist-cell[data-selected="true"] {
  outline: 2px solid var(--st-running-solid);
  outline-offset: 1px;
}

.rhist-cell__slot,
.rhist-legend__swatch {
  border-radius: 0.25rem;
  background: var(--st-pending-surface);
}

.rhist-cell__slot {
  flex: 1 1 0;
}

.rhist-cell__slot[data-tone="passed"],
.rhist-legend__swatch[data-tone="passed"] { background: var(--st-passed-solid); }
.rhist-cell__slot[data-tone="anomaly"],
.rhist-legend__swatch[data-tone="anomaly"] { background: var(--st-anomaly-solid); }
.rhist-cell__slot[data-tone="error"],
.rhist-legend__swatch[data-tone="error"] { background: var(--st-error-solid); }
.rhist-cell__slot[data-tone="running"],
.rhist-legend__swatch[data-tone="running"] { background: var(--st-running-solid); }
.rhist-cell__slot[data-tone="waiting_input"] { background: var(--st-waiting_input-solid); }
.rhist-cell__slot[data-tone="blocked"] { background: var(--st-blocked-solid); }
.rhist-cell__slot[data-tone="skipped"] { background: var(--st-skipped-solid); }
.rhist-cell__slot[data-tone="cancelled"] { background: var(--st-cancelled-solid); }

.rhist-legend__swatch[data-tone="not_checked"] {
  border: 1px dashed var(--st-pending-border);
}

.rhist-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.625rem;
  font-size: 0.75rem;
  color: var(--st-pending-text);
}

.rhist-legend__swatch {
  display: inline-block;
  width: 0.75rem;
  height: 0.75rem;
  margin-right: 0.25rem;
  vertical-align: -1px;
}

.rhist-drill {
  min-height: 0;
  overflow-y: auto;
  border-top: 1px solid var(--st-pending-border);
  padding-top: 0.75rem;
}

.rhist-drill__head {
  font-size: 0.8125rem;
  font-weight: 600;
}

.rhist-drill__row {
  display: grid;
  grid-template-columns: 5rem 6rem 1fr auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.5rem 0;
  font-size: 0.875rem;
}

.rhist-drill__empty {
  font-size: 0.875rem;
  color: var(--st-pending-text);
}
```

`--st-waiting_input-solid` 의 실제 생성 이름은 `app/web/frontend/styles/tokens.generated.css` 에서 확인한다. 토큰 생성기가 밑줄을 다르게 다루면 그 파일에 실제로 있는 이름을 쓴다. **없는 토큰을 새로 만들지 않는다.**

- [ ] **Step 2: 게이트로 색 위반이 없는지 확인한다**

Run: `python scripts/check_frontend_gates.py`
Expected: FG-002 위반 0

- [ ] **Step 3: 커밋**

```bash
git add app/web/frontend/runs-history/styles.css
git commit -m "feat(runs-history): 격자/드릴다운 스타일시트"
```

---

### Task 6: 시각 포맷 — `app.js` 에서 복제

**Files:**
- Create: `app/web/frontend/runs-history/format.ts`
- Test: `app/web/frontend/runs-history/format.test.ts`

**Interfaces:**
- Produces: `export function formatRunTime(isoString: string | null | undefined): string`

`app.js` 의 `formatRunTimestamp` 를 옮기지 **않고 복제**한다 — 예약 코드(`app.js:697` · `:728` · `:741`)가 원본을 계속 쓴다(설계 §3.4). 드릴다운 목록은 이미 하루 안이라 "오늘" 분기가 필요 없다. 시각만 낸다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```ts
import { describe, expect, it } from "vitest";
import { formatRunTime } from "./format";

describe("formatRunTime", () => {
  it("빈 값은 빈 문자열", () => {
    expect(formatRunTime(null)).toBe("");
    expect(formatRunTime(undefined)).toBe("");
    expect(formatRunTime("")).toBe("");
  });

  it("깨진 값도 던지지 않는다", () => {
    expect(formatRunTime("not-a-date")).toBe("");
  });

  it("시:분 을 24시간으로 낸다", () => {
    expect(formatRunTime("2026-09-01T13:05:00+09:00")).toMatch(/^\d{2}:\d{2}$/);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npx vitest run app/web/frontend/runs-history/format.test.ts`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 최소 구현**

```ts
/** 드릴다운 행의 시각 표기.
 *
 *  app.js 의 formatRunTimestamp 를 복제했다 — 예약 코드가 원본을 계속 쓰므로
 *  옮길 수 없다(설계 §3.4). 목록이 이미 하루 안이라 날짜 분기는 뺐다.
 *  중복 1건은 Cycle 6 에서 원본과 함께 사라진다. */
export function formatRunTime(isoString: string | null | undefined): string {
  if (!isoString) {
    return "";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `npx vitest run app/web/frontend/runs-history/format.test.ts`
Expected: PASS — 3건

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/runs-history/format.ts app/web/frontend/runs-history/format.test.ts
git commit -m "feat(runs-history): 드릴다운 시각 포맷"
```

---

### Task 7: 드릴다운 — 선택 · 조회 · 렌더

**Files:**
- Create: `app/web/frontend/runs-history/drilldown.ts`
- Test: `app/web/frontend/runs-history/drilldown.test.ts`

**Interfaces:**
- Consumes: Task 6 의 `formatRunTime`, Task 2 의 `GET /api/runs/day`
- Produces:

```ts
export type DayRun = { run_id: string; status: string; status_label: string; requested_at: string; module_total: number; module_passed: number; suite_id: string | null };
export function renderDrilldown(panel: HTMLElement, systemName: string, dayKey: string, runs: DayRun[]): void;
export function renderDrilldownError(panel: HTMLElement): void;
export function bindDrilldown(grid: HTMLElement, panel: HTMLElement, nameOf: (systemCode: string) => string): void;
```

`bindDrilldown` 은 격자에 클릭 위임을 걸고 선택된 셀에 `data-selected="true"` 를 준다(한 번에 하나).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { bindDrilldown, renderDrilldown, renderDrilldownError, type DayRun } from "./drilldown";

const run = (overrides: Partial<DayRun> = {}): DayRun => ({
  run_id: "run_1",
  status: "passed",
  status_label: "정상",
  requested_at: "2026-09-01T13:00:00+09:00",
  module_total: 3,
  module_passed: 3,
  suite_id: null,
  ...overrides,
});

function grid(): HTMLElement {
  const root = document.createElement("div");
  const cell = document.createElement("button");
  cell.className = "rhist-cell";
  cell.dataset.day = "2026-09-01";
  cell.dataset.system = "hom";
  root.appendChild(cell);
  return root;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("renderDrilldown", () => {
  it("Run 한 건마다 한 줄과 상세 링크를 낸다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", [run(), run({ run_id: "run_2" })]);

    expect(panel.querySelectorAll(".rhist-drill__row").length).toBe(2);
    expect(panel.querySelector<HTMLAnchorElement>('a[href="/runs/run_1"]')).not.toBeNull();
  });

  it("빈 날은 미실행이라고 말한다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", []);

    expect(panel.querySelector(".rhist-drill__empty")?.textContent).toContain(
      "실행된 Run 이 없습니다",
    );
  });

  it("서버가 준 status_label 을 그대로 쓴다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", [
      run({ status_label: "이상징후", status: "anomaly" }),
    ]);

    expect(panel.textContent).toContain("이상징후");
  });

  it("다시 그려도 행이 쌓이지 않는다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", [run()]);
    renderDrilldown(panel, "HOM", "2026-09-01", [run()]);

    expect(panel.querySelectorAll(".rhist-drill__row").length).toBe(1);
  });
});

describe("bindDrilldown", () => {
  it("셀을 누르면 그 날/시스템으로 조회한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [run()] });
    vi.stubGlobal("fetch", fetchMock);
    const root = grid();
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    await vi.waitFor(() => expect(panel.querySelectorAll(".rhist-drill__row").length).toBe(1));

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("system_code=hom");
    expect(url).toContain("day=2026-09-01");
  });

  it("선택한 셀만 표시된다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    const root = grid();
    const second = document.createElement("button");
    second.className = "rhist-cell";
    second.dataset.day = "2026-09-02";
    second.dataset.system = "hom";
    root.appendChild(second);
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    second.click();
    await vi.waitFor(() =>
      expect(root.querySelectorAll('[data-selected="true"]').length).toBe(1),
    );

    expect(second.dataset.selected).toBe("true");
  });

  it("조회가 실패해도 격자는 살아 있다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    const root = grid();
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    await vi.waitFor(() => expect(panel.textContent).toContain("불러오지 못했습니다"));

    expect(root.querySelectorAll(".rhist-cell").length).toBe(1);
  });

  it("응답이 실패 상태여도 패널에만 표시한다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => [] }));
    const root = grid();
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    await vi.waitFor(() => expect(panel.textContent).toContain("불러오지 못했습니다"));
  });
});

describe("renderDrilldownError", () => {
  it("실패 문구를 낸다", () => {
    const panel = document.createElement("div");

    renderDrilldownError(panel);

    expect(panel.textContent).toContain("불러오지 못했습니다");
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npx vitest run app/web/frontend/runs-history/drilldown.test.ts`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 최소 구현**

```ts
/** 격자 셀 드릴다운 — 그 날 그 시스템의 Run 목록.
 *
 *  셀에 실린 대표 run_id 를 쓰지 않는다(설계 D4). 서버가 슬롯당 한 건으로
 *  접기 때문에 재실행 이력이 숨는다. 별도 조회로 전량을 가져온다. */

import { formatRunTime } from "./format";

export type DayRun = {
  run_id: string;
  status: string;
  status_label: string;
  requested_at: string;
  module_total: number;
  module_passed: number;
  suite_id: string | null;
};

export function renderDrilldown(
  panel: HTMLElement,
  systemName: string,
  dayKey: string,
  runs: DayRun[],
): void {
  panel.replaceChildren();

  const head = document.createElement("p");
  head.className = "rhist-drill__head";
  head.textContent = `${dayKey} · ${systemName}`;
  panel.appendChild(head);

  if (runs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "rhist-drill__empty";
    empty.textContent = "이 날 실행된 Run 이 없습니다.";
    panel.appendChild(empty);
    return;
  }

  for (const item of runs) {
    const row = document.createElement("div");
    row.className = "rhist-drill__row";
    row.dataset.tone = item.status;

    const time = document.createElement("span");
    time.textContent = formatRunTime(item.requested_at);

    const status = document.createElement("span");
    status.textContent = item.status_label;

    const modules = document.createElement("span");
    modules.textContent = `모듈 ${item.module_passed}/${item.module_total}`;

    const link = document.createElement("a");
    link.href = `/runs/${item.run_id}`;
    link.textContent = "Run 상세 →";

    row.append(time, status, modules, link);
    panel.appendChild(row);
  }
}

export function renderDrilldownError(panel: HTMLElement): void {
  panel.replaceChildren();
  const message = document.createElement("p");
  message.className = "rhist-drill__empty";
  message.textContent = "Run 목록을 불러오지 못했습니다.";
  panel.appendChild(message);
}

export function bindDrilldown(
  grid: HTMLElement,
  panel: HTMLElement,
  nameOf: (systemCode: string) => string,
): void {
  grid.addEventListener("click", (event) => {
    const cell = (event.target as HTMLElement | null)?.closest<HTMLElement>(".rhist-cell");
    if (!cell || !grid.contains(cell)) {
      return;
    }
    const { day, system } = cell.dataset;
    if (!day || !system) {
      return;
    }

    for (const selected of grid.querySelectorAll<HTMLElement>('[data-selected="true"]')) {
      delete selected.dataset.selected;
    }
    cell.dataset.selected = "true";

    void loadDay(panel, system, day, nameOf(system));
  });
}

async function loadDay(
  panel: HTMLElement,
  systemCode: string,
  dayKey: string,
  systemName: string,
): Promise<void> {
  try {
    const params = new URLSearchParams({ system_code: systemCode, day: dayKey });
    const response = await fetch(`/api/runs/day?${params.toString()}`);
    if (!response.ok) {
      renderDrilldownError(panel);
      return;
    }
    renderDrilldown(panel, systemName, dayKey, (await response.json()) as DayRun[]);
  } catch {
    // 격자는 이미 그려져 있다 — 실패는 패널 안에서만 말한다(설계 §3.3).
    renderDrilldownError(panel);
  }
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `npx vitest run app/web/frontend/runs-history/`
Expected: PASS — coverage 10 + format 3 + drilldown 8

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/runs-history/drilldown.ts app/web/frontend/runs-history/drilldown.test.ts
git commit -m "feat(runs-history): 셀 드릴다운 조회와 렌더"
```

---

### Task 8: 템플릿 재작성 · 엔트리 배선

**Files:**
- Rewrite: `app/web/templates/runs_history.html`
- Create: `app/web/frontend/entries/runs-history.ts`
- Modify: `vite.config.ts` — `input` 목록의 `run:` 줄 아래
- Test: `tests/test_runs_history_layout.py` (신규)

**Interfaces:**
- Consumes: Task 4 `buildGrid`·`renderGrid`, Task 5 스타일, Task 7 `bindDrilldown`, Task 2 `GET /api/runs/coverage`

- [ ] **Step 1: 실패하는 템플릿 테스트를 쓴다**

```python
"""Run 이력 격자 레이아웃 계약 — 승격 규격(설계 §3.1·D1)."""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path("app/web/templates/runs_history.html")

COLOR_UTILITY = re.compile(
    r"\b(?:bg|text|border)-(?:gray|slate|zinc|indigo|emerald|green|amber|yellow|red|blue)-\d{2,3}\b"
)


def test_uses_promotion_shell_root():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert 'class="rhist"' in markup


def test_declares_grid_and_drilldown_hooks():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="rhist-grid"' in markup
    assert 'id="rhist-drill"' in markup


def test_legacy_hooks_are_gone():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert "runs-history-list" not in markup
    assert "runs-history-status" not in markup


def test_no_color_utilities():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert COLOR_UTILITY.findall(markup) == []


def test_loads_own_entry_without_static_reference():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert "entries/runs-history.ts" in markup
    assert "/static/" not in markup
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/test_runs_history_layout.py -v`
Expected: FAIL — 5건 전부

- [ ] **Step 3: 템플릿을 재작성한다**

```jinja
{% extends "base.html" %}

{% block title %}Run 이력{% endblock %}

{% block head_extra %}
{% import "_assets.html" as rhist_assets %}
{{ rhist_assets.asset_styles("entries/runs-history.ts") }}
{% endblock %}

{% block content %}
<div class="rhist" id="rhist-root">
  <header class="rhist-head">
    <nav class="rhist-crumb">
      <a href="/">대시보드</a>
      <span aria-hidden="true">/</span>
      <span class="rhist-crumb__here">Run 이력</span>
    </nav>
    <h1 class="rhist-head__title">Run 이력</h1>
    <p class="rhist-head__sub">최근 7일 점검 커버리지 · 빈칸은 점검이 돌지 않은 날입니다. 칸을 누르면 그 날 실행된 Run 이 아래에 나옵니다.</p>
  </header>

  <section class="rhist-board">
    <div class="rhist-grid" id="rhist-grid" aria-label="시스템별 최근 7일 점검 커버리지"></div>
    <p class="rhist-legend">
      <span><span class="rhist-legend__swatch" data-tone="passed"></span>정상</span>
      <span><span class="rhist-legend__swatch" data-tone="anomaly"></span>이상징후</span>
      <span><span class="rhist-legend__swatch" data-tone="error"></span>점검실패</span>
      <span><span class="rhist-legend__swatch" data-tone="running"></span>진행 중</span>
      <span><span class="rhist-legend__swatch" data-tone="not_checked"></span>미실행</span>
    </p>
  </section>

  <section class="rhist-drill" id="rhist-drill">
    <p class="rhist-drill__empty">칸을 선택하면 그 날 실행된 Run 이 표시됩니다.</p>
  </section>
</div>
{% endblock %}

{% block scripts %}
{% import "_assets.html" as rhist_assets %}
{{ rhist_assets.asset_script("entries/runs-history.ts") }}
{% endblock %}
```

범례 라벨은 고정 문구다 — 상태→표현 맵이 아니라 색 견본 설명이므로 FG-006 에 걸리지 않는다. 걸리면 `status_badge_view` 를 쓰지 말고 문구를 그대로 두되 게이트가 지적한 패턴을 피해 다시 쓴다.

- [ ] **Step 4: 엔트리를 쓴다**

`app/web/frontend/entries/runs-history.ts`:

```ts
/** Run 이력 화면 배선 — 로직은 runs-history/ 안에 있다. */
import "../runs-history/styles.css";
import { buildGrid, renderGrid, type CoverageResponse } from "../runs-history/coverage";
import { bindDrilldown } from "../runs-history/drilldown";

async function boot(): Promise<void> {
  const grid = document.getElementById("rhist-grid");
  const panel = document.getElementById("rhist-drill");
  if (!grid || !panel) {
    return;
  }

  const names = new Map<string, string>();
  bindDrilldown(grid, panel, (code) => names.get(code) ?? code);

  try {
    const response = await fetch("/api/runs/coverage");
    if (!response.ok) {
      grid.textContent = "점검 커버리지를 불러오지 못했습니다.";
      return;
    }
    const payload = (await response.json()) as CoverageResponse;
    for (const system of payload.systems) {
      names.set(system.system_code, system.system_name);
    }
    renderGrid(grid, buildGrid(payload), payload.window.day_keys);
  } catch {
    grid.textContent = "점검 커버리지를 불러오지 못했습니다.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void boot();
});
```

- [ ] **Step 5: Vite 엔트리를 등록한다**

`vite.config.ts` 의 `input` 에서 `run:` 줄 바로 아래에 한 줄 더한다.

```ts
        "runs-history": resolve(__dirname, "app/web/frontend/entries/runs-history.ts"),
```

- [ ] **Step 6: 통과를 확인한다**

```bash
npx tsc --noEmit
npx vitest run app/web/frontend/runs-history/
npm run build
python -m pytest tests/test_runs_history_layout.py -v
```

Expected: 전부 PASS. `npm run build` 를 돌려야 매니페스트에 `runs-history` 엔트리가 생기고 템플릿이 스크립트를 찾는다.

- [ ] **Step 7: 커밋**

```bash
git add app/web/templates/runs_history.html app/web/frontend/entries/runs-history.ts app/web/frontend/runs-history/styles.css vite.config.ts tests/test_runs_history_layout.py
git commit -m "feat(runs-history): 격자 화면 템플릿과 엔트리 배선"
```

---

### Task 9: 레거시 절단 — `app.js` 에서 `bindRunsHistory` 제거

**Files:**
- Modify: `app/web/static/app.js` — `RUN_HISTORY_LIMIT` · `bindRunsHistory`(`:422-462`) · `DOMContentLoaded` 호출(`:862-866`)
- Test: `tests/test_runs_history_legacy_cut.py` (신규)

**절대 지우지 말 것(D10):** `formatRunTimestamp` · `createRunListItem` · `buildExecutionGroups` · `isExecutionGroupActive` · `runChipToneKey` · `createRunChip` · `createRunChipConnector` · `summarizeSuiteFromRuns` · `createSuiteStripRow` · `renderExecutionGroups` · `renderRunList` · `refreshRunList` · `bindRunsOverview`. **`execute.html:385` 의 "진행 중 / 최근 Run" 이 이것들을 쓴다.**

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
"""Cycle 4 레거시 절단 계약 — 지운 것과 남긴 것(설계 §3.4·D10)."""

from __future__ import annotations

from pathlib import Path

APP_JS = Path("app/web/static/app.js")

# execute.html:385 의 "진행 중 / 최근 Run" 이 쓰는 코드 — 지우면 그 화면이 깨진다.
SHARED_WITH_EXECUTE = (
    "function formatRunTimestamp",
    "function createRunListItem",
    "function buildExecutionGroups",
    "function createSuiteStripRow",
    "function renderExecutionGroups",
    "function renderRunList",
    "async function refreshRunList",
    "function bindRunsOverview",
)


def test_runs_history_binding_is_gone():
    source = APP_JS.read_text(encoding="utf-8")
    assert "bindRunsHistory" not in source
    assert "runs-history-list" not in source
    assert "RUN_HISTORY_LIMIT" not in source


def test_execute_screen_code_survives():
    source = APP_JS.read_text(encoding="utf-8")
    for marker in SHARED_WITH_EXECUTE:
        assert marker in source, f"{marker} 는 execute.html 이 쓴다 — 지우면 안 된다"


def test_execute_template_still_declares_runs_list():
    markup = Path("app/web/templates/execute.html").read_text(encoding="utf-8")
    assert 'id="runs-list"' in markup
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/test_runs_history_legacy_cut.py -v`
Expected: FAIL — 첫 테스트만 실패(나머지 둘은 이미 통과)

- [ ] **Step 3: 제거한다**

`app/web/static/app.js` 에서 두 곳만 지운다.

1. `const RUN_HISTORY_LIMIT = 100;` 부터 `bindRunsHistory` 함수의 닫는 `}` 까지
2. `DOMContentLoaded` 안의 `bindRunsHistory();` 한 줄

남은 리스너는 이렇게 된다.

```javascript
document.addEventListener("DOMContentLoaded", () => {
    bindRunsOverview();
    bindSchedulesOverview();
});
```

- [ ] **Step 4: 통과와 회귀를 확인한다**

```bash
python -m pytest tests/test_runs_history_legacy_cut.py tests/test_legacy_js_status_labels.py tests/test_execute_layout.py -v
python scripts/check_frontend_gates.py
```

Expected: PASS · 게이트 통과. `app.js` 는 약 826줄이 된다 — `wc -l` 로 눈으로만 확인하고 테스트로 못 박지 않는다(다른 사이클이 이 숫자를 흔든다).

- [ ] **Step 5: 커밋**

```bash
git add app/web/static/app.js tests/test_runs_history_legacy_cut.py
git commit -m "refactor(runs-history): app.js 에서 bindRunsHistory 제거"
```

---

### Task 10: 넌스크롤 좌표 계약(Playwright)

**Files:**
- Create: `tests/test_runs_history_viewport.py`
- Test: 자기 자신

**Interfaces:**
- Consumes: Task 2 의 두 라우트, Task 8 의 템플릿·엔트리

`tests/test_run_viewport.py` 의 골격을 그대로 쓴다 — `_free_port` · `_wait_for_server` · 스레드 uvicorn 기동 · `StaticFiles` 마운트 · 의존성 오버라이드가 그 파일에 있다. 바꾸는 것은 라우터·오버라이드 대상·단언뿐이다. 픽스처를 공유 모듈로 빼지 않는다(그 파일도 자기 것을 갖고 있다).

**가짜 데이터:** 시스템 2개 × 7일. 그중 **하루는 3슬롯을 전부 비워** 미실행 칸이 실제로 그려지는지 본다. 드릴다운이 붙을 수 있게 Run 이 있는 날도 최소 하나 둔다.

- [ ] **Step 1: 테스트를 쓴다**

```python
VIEWPORTS = [(1366, 768), (1920, 1080), (2560, 1440)]


@pytest.mark.asyncio
@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
async def test_runs_history_does_not_scroll(page_factory, width, height):
    page = await page_factory(width, height)
    await page.goto(f"{BASE_URL}/runs/history")
    await page.wait_for_selector(".rhist-cell")

    overflow = await page.evaluate(
        "() => document.documentElement.scrollHeight - window.innerHeight"
    )
    assert overflow <= 0

    box = await page.locator("#rhist-grid").bounding_box()
    assert box is not None
    assert box["y"] + box["height"] <= height


@pytest.mark.asyncio
async def test_only_drilldown_scrolls(page_factory):
    page = await page_factory(1920, 1080)
    await page.goto(f"{BASE_URL}/runs/history")
    await page.wait_for_selector(".rhist-cell")

    scrollers = await page.evaluate(
        """() => Array.from(document.querySelectorAll('.rhist *'))
            .filter((el) => {
              const style = getComputedStyle(el);
              const scrolls = style.overflowY === 'auto' || style.overflowY === 'scroll';
              return scrolls && el.scrollHeight > el.clientHeight + 1;
            })
            .map((el) => el.id || el.className)"""
    )
    assert scrollers in ([], ["rhist-drill"])


@pytest.mark.asyncio
async def test_not_checked_cell_is_rendered(page_factory):
    page = await page_factory(1920, 1080)
    await page.goto(f"{BASE_URL}/runs/history")
    await page.wait_for_selector(".rhist-cell")

    blanks = await page.locator('.rhist-cell[data-tone="not_checked"]').count()
    assert blanks >= 1


@pytest.mark.asyncio
async def test_cell_click_opens_drilldown(page_factory):
    page = await page_factory(1920, 1080)
    await page.goto(f"{BASE_URL}/runs/history")
    await page.wait_for_selector(".rhist-cell")

    await page.locator(".rhist-cell").first.click()
    await page.wait_for_selector('.rhist-cell[data-selected="true"]')

    assert await page.locator("#rhist-drill").count() == 1
```

`is_visible()` 로 가시성을 단언하지 않는다 — 뷰포트 밖 요소를 통과시킨다(상위 설계 §8.2.1).

- [ ] **Step 2: 돌린다**

Run: `python -m pytest tests/test_runs_history_viewport.py -v`
Expected: PASS — 6건(뷰포트 3 + 스크롤 소유권 1 + 미실행 1 + 클릭 1)

실패하면 CSS 를 고친다. **테스트를 느슨하게 만들지 않는다** — 넌스크롤은 이 프로그램의 규격이다.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_runs_history_viewport.py
git commit -m "test(runs-history): 넌스크롤 좌표와 미실행 가시화 계약"
```

---

### Task 11: 전체 게이트

- [ ] **Step 1: 전 구간을 돌린다**

```bash
npx tsc --noEmit
npx eslint app/web/frontend
npx vitest run
npm run build
python -m ruff check .
python -m ruff format --check .
python scripts/check_frontend_gates.py
python -m pytest -q
```

**주의:** `vite build --watch` 프로세스가 떠 있으면 `emptyOutDir` 가 `app/web/static/dist/.vite/manifest.json` 을 지워 **pytest 가 거짓으로 실패한다**(Cycle 3 실측). 실패하면 먼저 `--watch` 프로세스가 있는지 확인하고 죽인 뒤 다시 돌린다.

Expected: 전부 PASS

- [ ] **Step 2: 성공 기준을 눈으로 확인한다**

설계 §2.3 의 표를 한 줄씩 확인한다. 특히 이 셋:

- `/admin` 커버리지 히트맵이 그대로 뜨는가
- `execute.html` 의 "진행 중 / 최근 Run" 이 그대로 뜨는가 — **이 사이클에서 가장 깨지기 쉬운 곳이다**
- Run 이력에서 미실행 칸이 실제로 보이는가

- [ ] **Step 3: 커밋**

```bash
git commit --allow-empty -m "chore(runs-history): Cycle 4 전체 게이트 통과 확인"
```
