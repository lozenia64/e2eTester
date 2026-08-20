# 프론트엔드 고도화 P2 (일간 현황) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 계산되고 있으나 묻혀 있던 자산(자동 복구·승인 대기·절감 시간)을 일간 현황 메인 화면의 KPI 카드 4장으로 올린다.

**Architecture:** 죽어 있던 레거시 `totals` 빌더를 먼저 제거해 테스트가 프로덕션을 검증하게 만든 뒤, 세 컨텍스트(insights·healing·stats)를 조립하는 순수 함수 `build_daily_summary` 와 읽기 핸들러 `DailySummaryQueries` 를 추가한다. 화면은 넌스크롤 뷰포트 불변식을 지키기 위해 기존 `dash-stats` 4타일을 `KpiCard` 4장으로 **교체**한다(추가 아님).

**Tech Stack:** Python 3.13 · FastAPI · Jinja2 · pytest · TypeScript · Vitest · htmx · Alpine

**Spec:** `docs/superpowers/specs/2026-08-19-frontend-elevation-p2-design.md`

## Global Constraints

- UI·로그·README 문자열은 **한국어**. (`AGENTS.md`)
- **라이트 단일 팔레트.** 다크모드·테마 분기 금지.
- **톤 축은 정확히 9개**: `passed` `anomaly` `error` `running` `waiting_input` `blocked` `skipped` `cancelled` `pending`
- `app/web/frontend/**` 내 하드코딩 hex 금지 (FG-002). 색은 토큰만.
- 상태 라벨은 `app/web/frontend/lib/status.generated.ts` 경유만 (FG-003).
- 엔트리·컴포넌트 파일 **400줄 상한** (FG-004).
- **넌스크롤 불변식:** `body:has(.dash) { overflow:hidden; height:100dvh }`. 일간 현황에 세로 공간을 순증시키지 않는다.
- **프라이버시 계약:** `/api/dashboard/daily/summary` 응답에 `user_id`·`email`·`user_name` 을 담은 리스트를 포함하지 않는다.
- **정직성 계약:** `estimated=true` 인 지표는 `note`(산출 근거)가 반드시 함께 존재한다.
- **기간 라벨:** KPI 4장 모두 기간 라벨을 갖는다. 라벨 없는 숫자를 두지 않는다.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full` + `npm run build && npm run typecheck && npm run lint && npm run test`.
- 새 CI 게이트를 추가하지 않는다. P1 이 배선한 6종이 자동 적용된다.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `app/contexts/insights/application/daily_dashboard.py` (수정) | 레거시 빌더 4개 함수 삭제 |
| `app/contexts/healing/metrics.py` (수정) | `day_label` 선택 인자 추가 (타임존 일치) |
| `app/contexts/healing/service.py` (수정) | `metrics()` 가 `day_label` 을 전달 |
| `app/contexts/scheduling/scheduler.py` (수정) | `schedule_month_start_utc()` 추가 |
| `app/core/stats_models.py` (수정) | `SavingsSummary` 모델 추가 |
| `app/contexts/insights/application/stats_service.py` (수정) | `get_savings_summary()` 추가 |
| `app/contexts/insights/application/daily_summary.py` (신규) | `build_daily_summary()` 순수 조립 |
| `app/orchestrator/queries/daily_summary_queries.py` (신규) | `DailySummaryQueries` 읽기 핸들러 |
| `app/composition/container.py` (수정) | `daily_summary_queries` 조립·app.state 노출 |
| `app/api/dependencies.py` (수정) | `get_daily_summary_queries` 프로바이더 |
| `app/api/routes_daily.py` (수정) | `/daily/summary` 라우트 + kpi 프래그먼트 배선 |
| `app/web/frontend/components/kpi-card/` (신규) | `macro.jinja` · `index.ts` · `styles.css` · `index.test.ts` |
| `app/web/templates/dashboard/partials/zone_a_kpi.html` (수정) | 히어로 재구성 + 밴드 교체 |
| `app/web/frontend/styles/dashboard.css` (수정) | `.dash-stats*` 제거, 압축 훅을 `.kpi-card` 로 이관 |
| `app/web/static/dashboard.js` (수정) | 카운트업 로직 제거(컴포넌트로 이관) |
| `app/web/templates/self_healing.html` (수정) | `id="patches"` 앵커 |
| `tests/test_daily_dashboard.py` 외 3파일 (수정) | 프로젝션 빌더로 이관 |
| `tests/test_daily_summary.py` (신규) | 조립·프라이버시·정직성 |
| `tests/test_daily_summary_http.py` (신규) | 라우트·권한 |
| `tests/test_healing_day_boundary.py` (신규) | 타임존 경계 |

---

## Task 1: 레거시 `totals` 빌더 제거 + 테스트 이관

**Files:**
- Modify: `app/contexts/insights/application/daily_dashboard.py` (150·168·188·231행 함수 삭제)
- Modify: `tests/test_daily_dashboard.py`, `tests/test_dashboard_fragments_http.py`, `tests/test_dashboard_viewport.py`

**Interfaces:**
- Produces: `build_daily_dashboard_from_projection` 이 `daily_dashboard.py` 의 **유일한** 대시보드 빌더가 된다. 시그니처는 변하지 않는다:
  ```python
  build_daily_dashboard_from_projection(
      systems: list[SystemDefinition],
      status_rows: list[DailyStatusRow],
      run_summaries: list[DailyRunSummaryRow],
      *,
      duration_by_module_run: dict[tuple[str, str], int | None] | None = None,
      generated_at: datetime,
      date_label: str,
  ) -> dict[str, Any]
  ```

- [ ] **Step 1: 죽은 코드임을 증명하는 테스트를 먼저 쓴다**

`tests/test_daily_dashboard.py` 맨 위에 추가:

```python
def test_only_one_dashboard_builder_exists():
    """레거시 빌더가 되살아나면 테스트가 프로덕션을 검증하지 못하게 된다."""
    import app.contexts.insights.application.daily_dashboard as mod

    assert not hasattr(mod, "build_daily_dashboard"), (
        "build_daily_dashboard 는 프로덕션에서 쓰이지 않는다. "
        "build_daily_dashboard_from_projection 만 남겨야 테스트가 실제 경로를 검증한다."
    )
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_dashboard.py::test_only_one_dashboard_builder_exists -v`
Expected: FAIL — `AssertionError: build_daily_dashboard 는 프로덕션에서 쓰이지 않는다`

- [ ] **Step 3: 테스트 픽스처 헬퍼를 만든다**

`tests/conftest.py` 에 추가한다. 세 테스트 파일이 공유한다.

```python
from datetime import UTC, datetime

from app.contexts.insights.contracts.query_rows import DailyRunSummaryRow, DailyStatusRow
from app.core.enums import ModuleStatus, RunStatus


def make_status_row(
    *,
    system_code: str,
    module_id: str,
    last_status: ModuleStatus,
    day_key: str = "2026-08-15",
    last_run_id: str | None = "run-1",
    duration_ms: int | None = 1000,
    recovered: bool = False,
) -> DailyStatusRow:
    """일간 프로젝션 행 픽스처. Run 객체 대신 이걸 쓴다(프로덕션 경로와 동일)."""
    return DailyStatusRow(
        day_key=day_key,
        system_code=system_code,
        module_id=module_id,
        last_status=last_status,
        last_run_id=last_run_id,
        duration_ms=duration_ms,
        updated_at=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
        recovered=recovered,
    )


def make_run_summary_row(
    *,
    system_code: str,
    run_id: str = "run-1",
    status: RunStatus = RunStatus.PASSED,
    triggered_by: str = "tester",
    requested_at: datetime | None = None,
) -> DailyRunSummaryRow:
    return DailyRunSummaryRow(
        run_id=run_id,
        system_code=system_code,
        status=status,
        requested_at=requested_at or datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
        triggered_by=triggered_by,
    )
```

- [ ] **Step 4: `tests/test_daily_dashboard.py` 의 호출 6곳을 이관한다**

64·89·124·133·148·171행. 변환 규칙:

```python
# 이전
data = build_daily_dashboard(systems, [run], generated_at=GEN_AT, date_label="d")

# 이후
data = build_daily_dashboard_from_projection(
    systems,
    [make_status_row(system_code="HOM", module_id="login", last_status=ModuleStatus.PASSED)],
    [make_run_summary_row(system_code="HOM")],
    generated_at=GEN_AT,
    date_label="d",
)
```

각 케이스가 원래 검증하던 **상태 조합을 그대로 재현**한다. `Run` 객체가 모듈 3개를 담고 있었다면 `make_status_row` 3개를 만든다. 빈 Run 목록(`[]`)이었던 케이스는 `status_rows=[]`, `run_summaries=[]` 로 옮긴다.

import 문도 교체:

```python
from app.contexts.insights.application.daily_dashboard import (
    build_daily_dashboard_from_projection,
)
from tests.conftest import make_run_summary_row, make_status_row
```

- [ ] **Step 5: 이관 결과를 확인한다**

Run: `python3 -m pytest tests/test_daily_dashboard.py -v`
Expected: `test_only_one_dashboard_builder_exists` 만 FAIL(아직 함수가 살아 있음), 나머지 PASS

나머지가 실패하면 상태 조합 재현이 틀린 것이다. 실패 케이스의 원래 `Run` 픽스처를 다시 읽고 `last_status` 를 맞춘다.

- [ ] **Step 6: `tests/test_dashboard_fragments_http.py` 의 호출 4곳을 이관한다**

54·90·226·247행. 같은 변환 규칙을 적용한다. 이 파일은 프래그먼트 HTML 을 렌더하므로, **이관 후 렌더 결과가 이전과 같은지**가 중요하다.

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py -v`
Expected: PASS

- [ ] **Step 7: `tests/test_dashboard_viewport.py` 의 호출 1곳을 이관한다**

211행. 같은 규칙.

Run: `python3 -m pytest tests/test_dashboard_viewport.py -v`
Expected: PASS

- [ ] **Step 8: 레거시 함수 4개를 삭제한다**

`app/contexts/insights/application/daily_dashboard.py` 에서 삭제:

- `_pick_module_status` (150행)
- `_module_view` (168행)
- `_system_view` (188행)
- `build_daily_dashboard` (231행)

`_module_view_from_row` · `_system_view_from_projection` · `build_daily_dashboard_from_projection` 은 **남긴다.**

삭제 후 사용하지 않게 된 import 를 정리한다:

Run: `python3 -m ruff check app/contexts/insights/application/daily_dashboard.py`
Expected: 에러 0건 (F401 이 뜨면 해당 import 삭제)

- [ ] **Step 9: 전체 통과를 확인한다**

Run: `python3 -m pytest tests/ -q`
Expected: 전부 PASS

Run: `grep -rn "build_daily_dashboard\b" app tests --include=*.py | grep -v "_from_projection"`
Expected: 출력 없음

- [ ] **Step 10: 커밋**

```bash
git add app/contexts/insights/application/daily_dashboard.py tests/
git commit -m "refactor(insights): 죽은 레거시 대시보드 빌더 제거 + 테스트를 프로덕션 경로로 이관"
```

---

## Task 2: healing 지표의 날짜 경계를 스케줄 타임존에 맞춘다

**Files:**
- Modify: `app/contexts/healing/metrics.py`
- Modify: `app/contexts/healing/service.py:215-223`
- Modify: `app/contexts/scheduling/scheduler.py`
- Test: `tests/test_healing_day_boundary.py`

**Interfaces:**
- Produces:
  - `build_healing_metrics(events, patches, *, now, trend_days=30, day_label=_utc_day_label)` — `day_label: Callable[[datetime], str]`
  - `app.contexts.scheduling.scheduler.schedule_month_start_utc() -> datetime`

- [ ] **Step 1: 날짜 경계 테스트를 작성한다**

`tests/test_healing_day_boundary.py`:

```python
"""healing 지표의 '오늘'이 일간 대시보드의 '오늘'과 같은 날인지 검증.

build_healing_metrics 는 UTC 로 버킷을 만들고, 일간 대시보드는 스케줄 타임존
(기본 Asia/Seoul)으로 날짜를 정한다. KST 00:00~09:00 구간에는 UTC 가 아직 전날이라
자동 복구 건수가 어긋난다 — 사람들이 실제로 대시보드를 보는 아침 시간대다.
"""

from datetime import UTC, datetime

from app.contexts.healing.metrics import build_healing_metrics
from app.contexts.healing.models import HealingAction, HealingEvent
from app.core.schedule_time import schedule_day_label

# KST 2026-08-19 08:00 == UTC 2026-08-18 23:00
KST_MORNING_UTC = datetime(2026, 8, 18, 23, 0, tzinfo=UTC)


def _event(created_at: datetime, event_id: str = "e1") -> HealingEvent:
    return HealingEvent(
        event_id=event_id,
        run_id="run-1",
        module_id="login",
        system_code="HOM",
        broken_selector="#old",
        healed_selector="#new",
        action=HealingAction.AUTO_HEALED,
        retry_succeeded=True,
        created_at=created_at,
    )


def test_utc_default_buckets_by_utc_date():
    """기본 동작(기존 호출자)은 UTC 로 유지된다."""
    metrics = build_healing_metrics(
        [_event(KST_MORNING_UTC)], [], now=KST_MORNING_UTC, trend_days=3
    )
    days = [row["date"] for row in metrics["trend"]]
    assert "2026-08-18" in days


def test_schedule_timezone_buckets_by_kst_date():
    """day_label 을 넘기면 KST 기준 오늘(08-19)에 집계된다."""
    metrics = build_healing_metrics(
        [_event(KST_MORNING_UTC)],
        [],
        now=KST_MORNING_UTC,
        trend_days=3,
        day_label=schedule_day_label,
    )
    today = {row["date"]: row for row in metrics["trend"]}
    assert "2026-08-19" in today, list(today)
    assert today["2026-08-19"]["auto"] == 1


def test_kst_today_bucket_matches_dashboard_date_label():
    """healing 의 오늘 == 일간 대시보드의 date_label."""
    dashboard_today = schedule_day_label(KST_MORNING_UTC)
    metrics = build_healing_metrics(
        [_event(KST_MORNING_UTC)],
        [],
        now=KST_MORNING_UTC,
        trend_days=3,
        day_label=schedule_day_label,
    )
    bucket = next(row for row in metrics["trend"] if row["date"] == dashboard_today)
    assert bucket["auto"] == 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_healing_day_boundary.py -v`
Expected: `test_utc_default_buckets_by_utc_date` PASS, 나머지 2건 FAIL — `TypeError: build_healing_metrics() got an unexpected keyword argument 'day_label'`

- [ ] **Step 3: `build_healing_metrics` 에 `day_label` 을 추가한다**

`app/contexts/healing/metrics.py` 상단에 추가:

```python
from collections.abc import Callable


def _utc_day_label(moment: datetime) -> str:
    """기본 날짜 라벨 — 기존 동작(UTC) 유지."""
    return _as_utc(moment).date().isoformat()
```

시그니처를 바꾼다:

```python
def build_healing_metrics(
    events: list[HealingEvent],
    patches: list[HealingPatch],
    *,
    now: datetime,
    trend_days: int = 30,
    day_label: Callable[[datetime], str] = _utc_day_label,
) -> dict[str, Any]:
```

함수 본문에서 날짜를 만드는 두 곳을 `day_label` 로 바꾼다:

```python
    # 버킷 초기화
    for offset in range(trend_days):
        day = day_label(day_start + timedelta(days=offset))
        buckets[day] = {"auto": 0, "other": 0}

    # 이벤트 귀속
    for event in events:
        day = day_label(event.created_at)
        bucket = buckets.get(day)
```

`day_start` 계산도 라벨 기준과 어긋나지 않게 한다 — `now` 에서 `trend_days - 1` 일을 뺀 시각을 그대로 쓰되, 라벨링만 `day_label` 에 위임한다(현행 구조 유지).

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_healing_day_boundary.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 기존 healing 테스트가 깨지지 않았는지 확인한다**

Run: `python3 -m pytest tests/test_healing_metrics.py -v`
Expected: PASS — `build_healing_metrics` 의 기본 인자가 현행 UTC 동작이므로 변화가 없어야 한다

`tests/test_healing_service.py` 는 Step 6 에서 서비스가 KST 를 쓰도록 바꾼 뒤 날짜 기대값이 달라질 수 있다. 그때 실패하는 케이스는 **KST 기준으로 기대값을 고친다**(회귀가 아니라 의도된 변경).

- [ ] **Step 6: `HealingService.metrics()` 가 스케줄 타임존을 쓰게 한다**

`app/contexts/healing/service.py:218`:

```python
        payload = build_healing_metrics(
            events,
            patches,
            now=datetime.now(UTC),
            day_label=schedule_day_label,
        )
```

import 추가: `from app.core.schedule_time import schedule_day_label`

**이유:** `/api/healing/metrics` 도 사람이 보는 화면이므로 일간 현황과 같은 날짜 기준이어야 한다. 기본 인자는 순수 함수의 하위호환을 위해 UTC 로 남긴다.

> **스펙과의 의도적 차이:** 설계 §3.4.1 은 "기존 `/api/healing/metrics` 호출자는 동작이 바뀌지 않는다"고 적었다. 그것은 **순수 함수의 기본 인자**에 대한 진술이고, 서비스 계층은 여기서 의도적으로 KST 로 바꾼다. 자가 치유 화면이 UTC 날짜를, 일간 현황이 KST 날짜를 보여주는 상태 자체가 버그이기 때문이다. 설계 문서 §5 의 "기존 healing API 무변경" 항목은 이 결정에 맞춰 갱신되었다.

- [ ] **Step 7: 월초 헬퍼를 추가한다**

`app/contexts/scheduling/scheduler.py` 의 `schedule_today_start_utc` 아래에 추가:

```python
def schedule_month_start_utc() -> datetime:
    """스케줄 타임존 기준 '이번 달' 1일 00:00:00 을 UTC 로 반환한다."""
    tz, _ = _resolve_timezone()
    now_local = datetime.now(tz)
    month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start_local.astimezone(UTC)
```

- [ ] **Step 8: 커밋**

```bash
git add app/contexts/healing/metrics.py app/contexts/healing/service.py \
        app/contexts/scheduling/scheduler.py tests/test_healing_day_boundary.py
git commit -m "fix(healing): 지표 날짜 버킷을 스케줄 타임존에 맞춤 — 아침 시간대 오집계 해소"
```

---

## Task 3: `SavingsSummary` + `StatsService.get_savings_summary`

**Files:**
- Modify: `app/core/stats_models.py`
- Modify: `app/contexts/insights/application/stats_service.py`
- Test: `tests/test_savings_summary.py`

**Interfaces:**
- Consumes: Task 2 의 `schedule_month_start_utc()`
- Produces:
  ```python
  class SavingsSummary(BaseModel):
      total_seconds: int
      my_seconds: int
      run_count: int
      module_count: int
      basis_updated_at: datetime | None
      estimated: bool
      note: str

  async def StatsService.get_savings_summary(
      self, *, from_dt: datetime, to_dt: datetime, user_id: str | None
  ) -> SavingsSummary
  ```

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_savings_summary.py`:

```python
from datetime import UTC, datetime

import pytest

from app.core.stats_models import SavingsSummary

FROM_DT = datetime(2026, 8, 1, tzinfo=UTC)
TO_DT = datetime(2026, 8, 19, tzinfo=UTC)


def test_summary_never_carries_user_identifiers():
    """프라이버시 계약 — 사용자별 분해는 관리자 전용에만 남는다."""
    summary = SavingsSummary(
        total_seconds=1116000,
        my_seconds=72000,
        run_count=1240,
        module_count=36,
        basis_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
        estimated=True,
        note="1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)",
    )
    payload = summary.model_dump()
    forbidden = {"user_id", "email", "user_name", "by_user"}
    assert forbidden.isdisjoint(payload.keys())
    # 중첩 구조에도 없어야 한다
    assert "email" not in str(payload)


def test_estimated_requires_note():
    """근거 없는 추정치를 만들 수 없다(정직성 계약)."""
    with pytest.raises(ValueError, match="note"):
        SavingsSummary(
            total_seconds=1,
            my_seconds=0,
            run_count=1,
            module_count=1,
            basis_updated_at=None,
            estimated=True,
            note="",
        )


def test_not_estimated_allows_empty_note():
    summary = SavingsSummary(
        total_seconds=0,
        my_seconds=0,
        run_count=0,
        module_count=0,
        basis_updated_at=None,
        estimated=False,
        note="",
    )
    assert summary.note == ""


def _service_with_usage(stats: UsageStats, *, settings_rows=()) -> StatsService:
    """get_savings_summary 만 검증한다 — get_usage_stats 는 이미 다른 테스트가 덮는다.

    StatsQueryPort 전체를 스텁하는 대신 get_usage_stats 를 대체한다. 새로 추가된
    로직(합산·본인 몫 추출·근거 문자열)만 좁게 검증하기 위해서다.
    """

    class _Registry:
        def list_systems(self):
            return [
                SimpleNamespace(system_code="HOM", name="대표홈", modules=[1, 2]),
                SimpleNamespace(system_code="FP", name="위촉서류", modules=[3]),
            ]

    class _SettingsRepo:
        async def list(self):
            return list(settings_rows)

    service = StatsService(
        stats_query=SimpleNamespace(),
        suite_summary_query=SimpleNamespace(),
        registry=_Registry(),
        module_settings_repo=_SettingsRepo(),
    )

    async def _fake_usage(from_dt=None, to_dt=None):
        return stats

    service.get_usage_stats = _fake_usage  # type: ignore[method-assign]
    return service


def _usage_stats() -> UsageStats:
    def _sys(code: str, name: str, saved: int) -> SystemUsageStat:
        return SystemUsageStat(
            system_code=code,
            system_name=name,
            runs=1,
            modules_passed=1,
            modules_failed=0,
            total_duration_ms=1000,
            manual_seconds_saved=saved,
        )

    return UsageStats(
        period_from=FROM_DT,
        period_to=TO_DT,
        generated_at=TO_DT,
        total_runs=3,
        total_users=2,
        by_user=[
            UserUsageStat(
                user_id="user-a",
                user_name="가",
                email="a@example.com",
                total_runs=2,
                total_modules_passed=2,
                total_modules_failed=0,
                total_duration_ms=2000,
                manual_seconds_saved=600,
                by_system=[],
            ),
            UserUsageStat(
                user_id="user-b",
                user_name="나",
                email="b@example.com",
                total_runs=1,
                total_modules_passed=1,
                total_modules_failed=0,
                total_duration_ms=1000,
                manual_seconds_saved=300,
                by_system=[],
            ),
        ],
        by_system=[_sys("HOM", "대표홈", 600), _sys("FP", "위촉서류", 300)],
    )


@pytest.mark.asyncio
async def test_get_savings_summary_sums_systems_and_picks_my_share():
    """전사 합계는 by_system 합, 내 기여분은 로그인 사용자의 것만."""
    service = _service_with_usage(_usage_stats())
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="user-a")
    assert summary.total_seconds == 900  # HOM 600 + FP 300
    assert summary.my_seconds == 600  # user-a 몫만
    assert summary.run_count == 3
    assert summary.module_count == 3  # HOM 2 + FP 1
    assert summary.estimated is True
    assert "3회" in summary.note


@pytest.mark.asyncio
async def test_unknown_user_gets_zero_my_seconds():
    service = _service_with_usage(_usage_stats())
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="nobody")
    assert summary.total_seconds == 900
    assert summary.my_seconds == 0


@pytest.mark.asyncio
async def test_returned_summary_drops_the_user_list():
    """by_user 를 받아 계산하되 응답에는 남기지 않는다."""
    service = _service_with_usage(_usage_stats())
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="user-a")
    assert "a@example.com" not in str(summary.model_dump())


@pytest.mark.asyncio
async def test_zero_savings_is_not_estimated():
    """추정치 미설정 → estimated=False, note 없이도 유효하다."""
    stats = _usage_stats().model_copy(
        update={
            "by_system": [
                SystemUsageStat(
                    system_code="HOM",
                    system_name="대표홈",
                    runs=1,
                    modules_passed=1,
                    modules_failed=0,
                    total_duration_ms=1000,
                    manual_seconds_saved=0,
                )
            ]
        }
    )
    service = _service_with_usage(stats)
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="user-a")
    assert summary.total_seconds == 0
    assert summary.estimated is False
```

파일 상단 import:

```python
from types import SimpleNamespace

from app.contexts.insights.application.stats_service import StatsService
from app.core.stats_models import (
    SavingsSummary,
    SystemUsageStat,
    UsageStats,
    UserUsageStat,
)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_savings_summary.py -v`
Expected: FAIL — `ImportError: cannot import name 'SavingsSummary'`

- [ ] **Step 3: `SavingsSummary` 모델을 추가한다**

`app/core/stats_models.py` 끝에 추가:

```python
class SavingsSummary(BaseModel):
    """절감 시간 요약(비관리자 노출용).

    사용자별 분해를 담지 않는다 — ``UserUsageStat`` 은 이름·이메일을 포함하므로
    전직원에게 열면 "누가 얼마나 돌렸나"가 노출된다. 전사 합계와 본인 기여분만 담는다.
    """

    total_seconds: int
    my_seconds: int
    run_count: int
    module_count: int
    basis_updated_at: datetime | None
    estimated: bool
    note: str

    @model_validator(mode="after")
    def _estimated_requires_note(self) -> SavingsSummary:
        if self.estimated and not self.note.strip():
            msg = "estimated=True 인 지표는 산출 근거(note)가 있어야 한다."
            raise ValueError(msg)
        return self
```

import 추가: `from pydantic import BaseModel, Field, model_validator`

- [ ] **Step 4: `get_savings_summary` 를 구현한다**

`app/contexts/insights/application/stats_service.py` 의 `StatsService` 에 추가:

```python
class StatsService:  # 기존 클래스에 메서드만 추가한다
    async def get_savings_summary(
        self,
        *,
        from_dt: datetime,
        to_dt: datetime,
        user_id: str | None,
    ) -> SavingsSummary:
        """전사 절감 합계 + 본인 기여분. 사용자별 분해는 담지 않는다.

        기존 get_usage_stats 를 재사용하고 사용자 목록은 버린다 — 계산 로직을
        두 벌로 만들지 않기 위해서다.
        """
        stats = await self.get_usage_stats(from_dt, to_dt)

        total_seconds = sum(s.manual_seconds_saved for s in stats.by_system)
        my_seconds = next(
            (u.manual_seconds_saved for u in stats.by_user if u.user_id == user_id),
            0,
        )
        module_count = sum(len(s.modules) for s in self._registry.list_systems())

        basis_updated_at: datetime | None = None
        if self._module_settings_repo is not None:
            settings_rows = await self._module_settings_repo.list()
            if settings_rows:
                basis_updated_at = max(row.updated_at for row in settings_rows)

        estimated = total_seconds > 0
        note = ""
        if estimated:
            basis_label = (
                f" (기준 {basis_updated_at.strftime('%-m/%-d')})"
                if basis_updated_at is not None
                else ""
            )
            note = f"{stats.total_runs:,}회 · {module_count}개 모듈 × 수동 추정치{basis_label}"

        return SavingsSummary(
            total_seconds=total_seconds,
            my_seconds=my_seconds,
            run_count=stats.total_runs,
            module_count=module_count,
            basis_updated_at=basis_updated_at,
            estimated=estimated,
            note=note,
        )
```

import 추가: `from app.core.stats_models import SavingsSummary`

**Windows 주의:** `strftime('%-m/%-d')` 는 glibc 확장이라 Windows 에서 실패한다. 대신 다음을 쓴다:

```python
basis_label = (
    f" (기준 {basis_updated_at.month}/{basis_updated_at.day})"
    if basis_updated_at is not None
    else ""
)
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python3 -m pytest tests/test_savings_summary.py -v`
Expected: PASS (7 passed — 모델 3건 + 서비스 4건)

- [ ] **Step 6: 관리자 경로가 그대로인지 확인한다**

Run: `python3 -m pytest tests/test_admin_dashboard_runs.py tests/test_admin_runs_api.py -q`
Expected: PASS — `get_usage_stats` 는 변경하지 않았으므로 영향이 없어야 한다

- [ ] **Step 7: 커밋**

```bash
git add app/core/stats_models.py app/contexts/insights/application/stats_service.py \
        tests/test_savings_summary.py tests/conftest.py
git commit -m "feat(insights): 비관리자용 절감 요약(SavingsSummary) 추가 — 사용자별 분해 제외"
```

---

## Task 4: `build_daily_summary` 순수 조립 + `DailySummaryQueries`

**Files:**
- Create: `app/contexts/insights/application/daily_summary.py`
- Create: `app/orchestrator/queries/daily_summary_queries.py`
- Test: `tests/test_daily_summary.py`

**Interfaces:**
- Consumes: Task 2 의 `schedule_month_start_utc()` · `schedule_day_label`, Task 3 의 `SavingsSummary`
- Produces:
  ```python
  def build_daily_summary(
      totals: dict[str, Any],
      healing_metrics: dict[str, Any],
      savings: SavingsSummary,
      *,
      today_label: str,
  ) -> dict[str, Any]
  # → {"cards": [ {key,label,value,unit,period,note,tone,href,estimated}, ... ]}

  class DailySummaryQueries:
      async def get_daily_summary(
          self, *, user_id: str | None, allowed_system_codes: list[str] | None
      ) -> dict[str, Any]
  ```
  카드 `key` 는 정확히 `"pass_rate"` · `"self_healed"` · `"pending_patches"` · `"savings"` 4개, 이 순서.

- [ ] **Step 1: 조립 테스트를 작성한다**

`tests/test_daily_summary.py`:

```python
from datetime import UTC, datetime

from app.contexts.insights.application.daily_summary import build_daily_summary
from app.core.stats_models import SavingsSummary

TOTALS = {"modules": 36, "passed": 34, "pass_rate": 94, "anomaly": 2, "error": 0}
HEALING = {
    "kpi": {"month_auto_recovered": 21, "unattended_rate": 82.0, "pending_patches": 2},
    "trend": [
        {"date": "2026-08-18", "auto": 3, "other": 1},
        {"date": "2026-08-19", "auto": 7, "other": 0},
    ],
}
SAVINGS = SavingsSummary(
    total_seconds=1116000,
    my_seconds=72000,
    run_count=1240,
    module_count=36,
    basis_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    estimated=True,
    note="1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)",
)


def _cards(**overrides):
    kwargs = {
        "totals": TOTALS,
        "healing_metrics": HEALING,
        "savings": SAVINGS,
        "today_label": "2026-08-19",
    }
    kwargs.update(overrides)
    summary = build_daily_summary(
        kwargs["totals"],
        kwargs["healing_metrics"],
        kwargs["savings"],
        today_label=kwargs["today_label"],
    )
    return {card["key"]: card for card in summary["cards"]}


def test_produces_exactly_four_cards_in_order():
    summary = build_daily_summary(TOTALS, HEALING, SAVINGS, today_label="2026-08-19")
    assert [c["key"] for c in summary["cards"]] == [
        "pass_rate",
        "self_healed",
        "pending_patches",
        "savings",
    ]


def test_self_healed_uses_today_bucket_not_month():
    """오늘 버킷(7)을 쓴다. 이번 달 누적(21)은 부연으로만."""
    card = _cards()["self_healed"]
    assert card["value"] == 7
    assert "21" in card["note"]


def test_self_healed_is_zero_when_today_bucket_absent():
    card = _cards(healing_metrics={"kpi": HEALING["kpi"], "trend": []})["self_healed"]
    assert card["value"] == 0


def test_every_card_has_a_period_label():
    for key, card in _cards().items():
        assert card["period"], key


def test_only_pending_patches_uses_anomaly_tone():
    cards = _cards()
    assert cards["pending_patches"]["tone"] == "anomaly"
    assert cards["pass_rate"]["tone"] != "anomaly"
    assert cards["self_healed"]["tone"] != "anomaly"
    assert cards["savings"]["tone"] != "anomaly"


def test_pending_patches_links_to_patch_list():
    assert _cards()["pending_patches"]["href"] == "/self-healing#patches"


def test_estimated_card_always_carries_note():
    for card in _cards().values():
        if card["estimated"]:
            assert card["note"].strip(), card["key"]


def test_only_savings_is_estimated():
    cards = _cards()
    assert cards["savings"]["estimated"] is True
    assert cards["pass_rate"]["estimated"] is False
    assert cards["self_healed"]["estimated"] is False
    assert cards["pending_patches"]["estimated"] is False


def test_unset_basis_shows_guidance_instead_of_zero_hours():
    """추정치 미설정 상태에서 0h 를 성과처럼 띄우지 않는다."""
    empty = SavingsSummary(
        total_seconds=0,
        my_seconds=0,
        run_count=0,
        module_count=36,
        basis_updated_at=None,
        estimated=False,
        note="",
    )
    card = _cards(savings=empty)["savings"]
    assert card["value"] == "추정치 미설정"
    assert card["href"] == "/admin/modules"


def test_summary_has_no_user_identifiers():
    summary = build_daily_summary(TOTALS, HEALING, SAVINGS, today_label="2026-08-19")
    assert "email" not in str(summary)
    assert "user_id" not in str(summary)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.contexts.insights.application.daily_summary'`

- [ ] **Step 3: 조립 함수를 구현한다**

`app/contexts/insights/application/daily_summary.py`:

```python
"""KPI 카드 조립 — 일간·치유·사용량 세 컨텍스트의 읽기 결과를 카드 4장으로 만든다.

I/O 없음. ``DailySummaryQueries`` 가 스토어에서 읽은 것을 넘겨 호출한다
(``build_healing_metrics`` 와 같은 순수 빌더 패턴).

정직성 규율(설계 §3.8): 추정 지표는 근거(note)를 반드시 동반한다. 실측(통과율·복구
건수·승인 대기)과 추정(절감 시간)을 estimated 플래그로 구분한다.
"""

from __future__ import annotations

from typing import Any

from app.core.stats_models import SavingsSummary

# 추정치가 설정되지 않았을 때 0h 를 성과처럼 표시하지 않기 위한 안내 문구.
SAVINGS_UNSET_LABEL = "추정치 미설정"
MODULE_SETTINGS_URL = "/admin/modules"
PATCH_LIST_URL = "/self-healing#patches"


def _today_auto_healed(healing_metrics: dict[str, Any], today_label: str) -> int:
    for row in healing_metrics.get("trend", []):
        if row.get("date") == today_label:
            return int(row.get("auto", 0))
    return 0


def _savings_card(savings: SavingsSummary) -> dict[str, Any]:
    if not savings.estimated or savings.total_seconds <= 0:
        return {
            "key": "savings",
            "label": "이번 달 절감",
            "value": SAVINGS_UNSET_LABEL,
            "unit": "",
            "period": "이번 달",
            "note": "모듈별 수동 소요 추정치를 설정하면 집계됩니다",
            "tone": "pending",
            "href": MODULE_SETTINGS_URL,
            "estimated": False,
        }
    return {
        "key": "savings",
        "label": "이번 달 절감",
        "value": round(savings.total_seconds / 3600),
        "unit": "h",
        "period": "이번 달",
        "note": savings.note,
        "tone": "passed",
        "href": MODULE_SETTINGS_URL,
        "estimated": True,
    }


def build_daily_summary(
    totals: dict[str, Any],
    healing_metrics: dict[str, Any],
    savings: SavingsSummary,
    *,
    today_label: str,
) -> dict[str, Any]:
    """KPI 카드 4장(순서 고정: 통과율 · 스스로 복구 · 승인 대기 · 절감)."""
    kpi = healing_metrics.get("kpi", {})
    today_healed = _today_auto_healed(healing_metrics, today_label)
    month_healed = int(kpi.get("month_auto_recovered", 0) or 0)
    pending = int(kpi.get("pending_patches", 0) or 0)

    cards: list[dict[str, Any]] = [
        {
            "key": "pass_rate",
            "label": "통과율",
            "value": totals.get("pass_rate", 0),
            "unit": "%",
            "period": "오늘",
            "note": f"{totals.get('passed', 0)}/{totals.get('modules', 0)} 모듈 정상",
            "tone": "passed",
            "href": "",
            "estimated": False,
        },
        {
            "key": "self_healed",
            "label": "스스로 복구",
            "value": today_healed,
            "unit": "건",
            "period": "오늘",
            "note": f"이번 달 누적 {month_healed}건",
            "tone": "running",
            "href": "/self-healing",
            "estimated": False,
        },
        {
            # 유일하게 '행동을 요구하는' 숫자 — 톤을 분리한다(설계 §3.7).
            "key": "pending_patches",
            "label": "내 승인 대기",
            "value": pending,
            "unit": "건",
            "period": "패치",
            "note": "자동 생성된 수정 diff 검토",
            "tone": "anomaly",
            "href": PATCH_LIST_URL,
            "estimated": False,
        },
        _savings_card(savings),
    ]
    return {"cards": cards}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_summary.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 읽기 핸들러를 구현한다**

`app/orchestrator/queries/daily_summary_queries.py`:

```python
"""KPI 요약 질의 핸들러 — 일간·치유·사용량을 조립한다(읽기 전용).

DailyDashboardQueries 에 합치지 않는 이유: 일간 쿼리가 3방향 fan-out 을 하게 되어
매트릭스·패널 등 KPI 와 무관한 경로까지 치유·통계 스토어에 의존하게 된다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.contexts.insights.application.daily_summary import build_daily_summary
from app.contexts.scheduling.scheduler import schedule_month_start_utc, schedule_today_label

if TYPE_CHECKING:
    from app.contexts.healing.service import HealingService
    from app.contexts.insights.application.stats_service import StatsService
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries


class DailySummaryQueries:
    def __init__(
        self,
        daily_queries: DailyDashboardQueries,
        healing_service: HealingService,
        stats_service: StatsService,
    ) -> None:
        self._daily_queries = daily_queries
        self._healing = healing_service
        self._stats = stats_service

    async def get_daily_summary(
        self,
        *,
        user_id: str | None,
        allowed_system_codes: list[str] | None,
    ) -> dict[str, Any]:
        dashboard = await self._daily_queries.get_daily_dashboard(
            allowed_system_codes=allowed_system_codes
        )
        healing_metrics = await self._healing.metrics(allowed_system_codes=allowed_system_codes)
        savings = await self._stats.get_savings_summary(
            from_dt=schedule_month_start_utc(),
            to_dt=datetime.now(UTC),
            user_id=user_id,
        )
        summary = build_daily_summary(
            dashboard["totals"],
            healing_metrics,
            savings,
            today_label=schedule_today_label(),
        )
        # 프래그먼트가 히어로 문장·메타에 쓰는 원본도 함께 넘긴다.
        summary["totals"] = dashboard["totals"]
        summary["date_label"] = dashboard["date_label"]
        summary["generated_at"] = dashboard["generated_at"]
        summary["attention"] = dashboard["attention"]
        return summary
```

- [ ] **Step 6: 아키텍처 게이트를 확인한다**

Run: `python3 scripts/check_architecture_gates.py`
Expected: 통과

Run: `python3 -m importlinter.cli lint`
Expected: 통과 — `orchestrator/queries` 가 `contexts/*/application` 을 참조하는 것은 기존 `daily_queries.py` 와 같은 방향이다. 위반이 뜨면 `importlinter` 설정의 계약 이름을 확인하고 기존 `daily_queries` 가 어떻게 허용되는지 맞춘다.

- [ ] **Step 7: 커밋**

```bash
git add app/contexts/insights/application/daily_summary.py \
        app/orchestrator/queries/daily_summary_queries.py tests/test_daily_summary.py
git commit -m "feat(insights): KPI 카드 조립기 + DailySummaryQueries 추가"
```

---

## Task 5: API 노출 — `/daily/summary` + kpi 프래그먼트 배선

**Files:**
- Modify: `app/composition/container.py:200-205, 281`
- Modify: `app/api/dependencies.py`
- Modify: `app/api/routes_daily.py`
- Test: `tests/test_daily_summary_http.py`

**Interfaces:**
- Consumes: Task 4 의 `DailySummaryQueries.get_daily_summary(user_id=..., allowed_system_codes=...)`
- Produces:
  - `app.state.daily_summary_queries`
  - `app.api.dependencies.get_daily_summary_queries(connection) -> DailySummaryQueries`
  - `GET /api/dashboard/daily/summary`

- [ ] **Step 1: HTTP 테스트를 작성한다**

`tests/test_daily_summary_http.py`:

기존 HTTP 테스트(`tests/test_dashboard_fragments_http.py`)와 같이 실제 로그인 대신 `app.dependency_overrides` + Fake 질의 핸들러를 쓴다.

```python
"""KPI 요약 라우트 계약 테스트 — 권한·프라이버시.

로그인 플로우 대신 dependency_overrides 로 사용자를 주입한다
(tests/test_dashboard_fragments_http.py 와 같은 방식).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_daily_queries, get_daily_summary_queries
from app.api.routes_daily import router as daily_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User

SUMMARY = {
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
            "href": "/self-healing",
            "estimated": False,
        },
        {
            "key": "pending_patches",
            "label": "내 승인 대기",
            "value": 2,
            "unit": "건",
            "period": "패치",
            "note": "자동 생성된 수정 diff 검토",
            "tone": "anomaly",
            "href": "/self-healing#patches",
            "estimated": False,
        },
        {
            "key": "savings",
            "label": "이번 달 절감",
            "value": 310,
            "unit": "h",
            "period": "이번 달",
            "note": "1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)",
            "tone": "passed",
            "href": "/admin/modules",
            "estimated": True,
        },
    ],
    "totals": {
        "modules": 36,
        "passed": 34,
        "pass_rate": 94,
        "anomaly": 2,
        "error": 0,
        "running": 0,
        "not_inspected": 0,
    },
    "date_label": "2026-08-19",
    "generated_at": "2026-08-19T00:14:00+00:00",
    "attention": [],
}


class FakeDailySummaryQueries:
    def __init__(self) -> None:
        self.seen: list[tuple[str | None, list[str] | None]] = []

    async def get_daily_summary(self, *, user_id, allowed_system_codes):
        self.seen.append((user_id, allowed_system_codes))
        return SUMMARY


def _member() -> User:
    """비관리자(일반 담당자) 사용자."""
    return User(
        user_id="user-a",
        email="a@example.com",
        name="가",
        role="member",
        allowed_system_codes=["HOM"],
    )


@pytest.fixture()
def client_and_fake():
    app = FastAPI()
    app.include_router(daily_router)
    fake = FakeDailySummaryQueries()
    app.dependency_overrides[get_daily_summary_queries] = lambda: fake
    app.dependency_overrides[get_daily_queries] = lambda: None
    app.dependency_overrides[get_current_user] = _member
    with TestClient(app) as client:
        yield client, fake


def test_summary_returns_four_cards(client_and_fake):
    client, _ = client_and_fake
    response = client.get("/api/dashboard/daily/summary")
    assert response.status_code == 200
    assert [c["key"] for c in response.json()["cards"]] == [
        "pass_rate",
        "self_healed",
        "pending_patches",
        "savings",
    ]


def test_non_admin_can_read_savings(client_and_fake):
    """경영진·담당자가 관리자 권한 없이 절감 지표를 볼 수 있어야 한다."""
    client, _ = client_and_fake
    response = client.get("/api/dashboard/daily/summary")
    savings = next(c for c in response.json()["cards"] if c["key"] == "savings")
    assert savings["value"] == 310
    assert savings["estimated"] is True
    assert savings["note"]


def test_summary_response_has_no_user_identifiers(client_and_fake):
    """프라이버시 계약 — 사용자별 분해는 관리자 전용에만."""
    client, _ = client_and_fake
    body = client.get("/api/dashboard/daily/summary").text
    for forbidden in ("email", "user_id", "user_name", "by_user"):
        assert forbidden not in body, forbidden


def test_non_admin_is_scoped_to_allowed_systems(client_and_fake):
    """관리자가 아니면 allowed_system_codes 로 스코프가 걸려야 한다."""
    client, fake = client_and_fake
    client.get("/api/dashboard/daily/summary")
    user_id, allowed = fake.seen[-1]
    assert user_id == "user-a"
    assert allowed == ["HOM"]


def test_kpi_fragment_uses_summary(client_and_fake):
    """kpi 프래그먼트가 요약 핸들러를 쓴다(matrix 는 기존 핸들러 유지)."""
    client, fake = client_and_fake
    response = client.get("/api/dashboard/daily/fragments/kpi")
    assert response.status_code == 200
    assert fake.seen, "요약 핸들러가 호출되지 않았다"
```

`User` 의 실제 필드명(`user_id`·`role`·`allowed_system_codes`)은 `app/contexts/identity/models.py` 를 열어 확인하고 다르면 맞춘다.

**관리자 전용 경로가 그대로인지**는 별도 파일에서 이미 검증된다 — `tests/test_admin_*` 이 `require_admin` 을 덮고 있다. 새로 추가하지 않는다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_summary_http.py -v`
Expected: FAIL — 404 (라우트 없음)

- [ ] **Step 3: 컨테이너에 조립한다**

`app/composition/container.py` 의 `self.insights.daily_queries = DailyDashboardQueries(...)` (200행) 아래에 추가:

```python
        self.insights.daily_summary_queries = DailySummaryQueries(
            self.insights.daily_queries,
            self.healing.healing_service,
            self.insights.stats_service,
        )
```

281행 근처 `app.state.daily_queries = self.insights.daily_queries` 아래에 추가:

```python
        app.state.daily_summary_queries = self.insights.daily_summary_queries
```

import 추가: `from app.orchestrator.queries.daily_summary_queries import DailySummaryQueries`

**주의:** `healing_service` 와 `stats_service` 가 이 시점에 이미 만들어져 있어야 한다. 컨테이너에서 생성 순서를 확인하고, 아직이면 `daily_summary_queries` 조립을 두 서비스 생성 **뒤로** 옮긴다.

- [ ] **Step 4: DI 프로바이더를 추가한다**

`app/api/dependencies.py` 의 `get_daily_queries` 아래:

```python
def get_daily_summary_queries(connection: HTTPConnection) -> DailySummaryQueries:
    """KPI 요약 질의 핸들러(읽기 전용)."""
    return connection.app.state.daily_summary_queries
```

TYPE_CHECKING import 를 함께 추가한다.

- [ ] **Step 5: 라우트를 추가하고 kpi 프래그먼트를 배선한다**

`app/api/routes_daily.py`:

```python
async def _load_summary(
    summary_queries: DailySummaryQueries,
    current_user: User,
) -> dict:
    allowed = None if current_user.role == "admin" else current_user.allowed_system_codes
    return await summary_queries.get_daily_summary(
        user_id=current_user.user_id,
        allowed_system_codes=allowed,
    )


@router.get("/daily/summary")
async def daily_summary(
    current_user: User = Depends(get_current_user),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """KPI 카드 4장(통과율·스스로 복구·승인 대기·절감). 사용자별 분해는 담지 않는다."""
    return await _load_summary(summary_queries, current_user)
```

`daily_dashboard_fragment` 의 `kpi` 분기가 요약을 쓰도록 바꾼다:

```python
@router.get("/daily/fragments/{zone}", response_class=HTMLResponse)
async def daily_dashboard_fragment(
    zone: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    daily_queries: DailyDashboardQueries = Depends(get_daily_queries),
    summary_queries: DailySummaryQueries = Depends(get_daily_summary_queries),
):
    """HTMX용 일간 대시보드 zone partial."""
    template_name = _FRAGMENT_TEMPLATES.get(zone)
    if template_name is None:
        raise HTTPException(status_code=404, detail="unknown fragment zone")
    if zone == "kpi":
        data = await _load_summary(summary_queries, current_user)
    else:
        data = await _load_dashboard(daily_queries, current_user)
    return templates.TemplateResponse(
        request,
        template_name,
        {"data": data, "request": request},
    )
```

`current_user.user_id` 의 실제 속성명은 `app/contexts/identity/models.py` 의 `User` 를 확인해 맞춘다. 다른 이름이면 그 이름을 쓴다.

- [ ] **Step 6: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_summary_http.py -v`
Expected: PASS (5 passed)

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py -v`
Expected: PASS — kpi 프래그먼트가 아직 `data.totals` 를 쓰므로 `DailySummaryQueries` 가 넘기는 `totals` 로 계속 렌더된다

- [ ] **Step 7: 커밋**

```bash
git add app/composition/container.py app/api/dependencies.py app/api/routes_daily.py \
        tests/test_daily_summary_http.py
git commit -m "feat(api): /api/dashboard/daily/summary 추가 + kpi 프래그먼트 배선"
```

---

## Task 6: `KpiCard` 컴포넌트

**Files:**
- Create: `app/web/frontend/components/kpi-card/macro.jinja`
- Create: `app/web/frontend/components/kpi-card/index.ts`
- Create: `app/web/frontend/components/kpi-card/styles.css`
- Create: `app/web/frontend/components/kpi-card/index.test.ts`
- Modify: `app/web/frontend/entries/main.ts`

**Interfaces:**
- Consumes: P1 의 토큰 `--st-{tone}-{solid|surface|text|border}`
- Produces:
  - Jinja: `{% macro kpi_card(key, label, value, unit="", period="", note="", tone="pending", href="", estimated=false) %}`
  - TS: `animateCountUp(el: HTMLElement, target: number, durationMs?: number): void` · `bindKpiCards(root?: ParentNode): void`

- [ ] **Step 1: Vitest 테스트를 작성한다**

`app/web/frontend/components/kpi-card/index.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { animateCountUp, bindKpiCards } from "./index";

function makeCard(value: string): HTMLElement {
  const card = document.createElement("article");
  card.className = "kpi-card";
  card.dataset.tone = "passed";
  const el = document.createElement("span");
  el.className = "kpi-card__value";
  el.dataset.target = value;
  el.textContent = "0";
  card.appendChild(el);
  document.body.appendChild(card);
  return card;
}

beforeEach(() => {
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("animateCountUp", () => {
  it("최종적으로 목표값에 도달한다", async () => {
    const el = document.createElement("span");
    animateCountUp(el, 94, 0);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(el.textContent).toBe("94");
  });

  it("목표가 0 이면 0 을 표시한다", async () => {
    const el = document.createElement("span");
    animateCountUp(el, 0, 0);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(el.textContent).toBe("0");
  });
});

describe("bindKpiCards", () => {
  it("data-target 이 숫자인 카드만 애니메이션한다", async () => {
    makeCard("94");
    const textCard = makeCard("추정치 미설정");
    bindKpiCards(document);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    const textValue = textCard.querySelector(".kpi-card__value")!;
    expect(textValue.textContent).toBe("추정치 미설정");
  });

  it("이미 바인딩된 카드를 두 번 처리하지 않는다", () => {
    const card = makeCard("7");
    bindKpiCards(document);
    bindKpiCards(document);
    expect(card.dataset.kpiBound).toBe("true");
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npm run test`
Expected: FAIL — `Failed to resolve import "./index"`

- [ ] **Step 3: 컴포넌트를 구현한다**

`app/web/frontend/components/kpi-card/index.ts`:

```ts
// KPI 카드 동작. 마크업은 macro.jinja 가 SSOT 이며, 여기서는 값 카운트업만 맡는다
// (dashboard.js 의 animateCountUp 을 컴포넌트로 이관).

const DEFAULT_DURATION_MS = 600;

export function animateCountUp(
  el: HTMLElement,
  target: number,
  durationMs: number = DEFAULT_DURATION_MS,
): void {
  if (durationMs <= 0 || Number.isNaN(target)) {
    el.textContent = String(target);
    return;
  }
  const start = performance.now();
  const step = (now: number): void => {
    const progress = Math.min((now - start) / durationMs, 1);
    // ease-out cubic — 토큰 --ease-out 과 같은 감각
    const eased = 1 - (1 - progress) ** 3;
    el.textContent = String(Math.round(target * eased));
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export function bindKpiCards(root: ParentNode = document): void {
  const cards = root.querySelectorAll<HTMLElement>(".kpi-card");
  cards.forEach((card) => {
    if (card.dataset.kpiBound === "true") return;
    card.dataset.kpiBound = "true";
    const valueEl = card.querySelector<HTMLElement>(".kpi-card__value");
    if (!valueEl) return;
    const raw = valueEl.dataset.target ?? "";
    const target = Number(raw);
    // 숫자가 아닌 값(예: "추정치 미설정")은 그대로 둔다.
    if (raw === "" || Number.isNaN(target)) return;
    animateCountUp(valueEl, target);
  });
}
```

`app/web/frontend/components/kpi-card/styles.css`:

```css
/* 색은 전부 토큰(FG-002). 밴드는 기존 dash-stats 와 같은 4열 그리드를 유지해
   넌스크롤 뷰포트 예산을 바꾸지 않는다. */
.kpi-band {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  width: 100%;
  min-width: 0;
  gap: 1px;
  border-radius: clamp(0.625rem, 1.2cqh, 1rem);
  overflow: hidden;
  background: var(--pl-border);
}

.kpi-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.125rem;
  min-width: 0;
  padding: 0.625rem 0.75rem;
  background: var(--pl-surface);
  color: inherit;
  text-decoration: none;
}

.kpi-card__label {
  font-size: 0.6875rem;
  color: var(--pl-text-muted);
}

.kpi-card__value {
  font-size: clamp(1.125rem, 3cqh, 1.75rem);
  font-weight: 800;
  line-height: 1.1;
  color: var(--pl-text);
}

.kpi-card__unit {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--pl-text-muted);
}

.kpi-card__note {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.625rem;
  color: var(--pl-text-subtle);
}

.kpi-card__badge {
  margin-left: 0.25rem;
  padding: 0 0.25rem;
  border-radius: 0.25rem;
  background: var(--st-pending-surface);
  color: var(--st-pending-text);
  font-size: 0.5625rem;
  font-weight: 700;
}

/* 행동을 요구하는 카드만 톤으로 분리한다(설계 §3.7). */
.kpi-card[data-tone="anomaly"] .kpi-card__label,
.kpi-card[data-tone="anomaly"] .kpi-card__value,
.kpi-card[data-tone="anomaly"] .kpi-card__note {
  color: var(--st-anomaly-text);
}

.kpi-card[data-tone="anomaly"] {
  background: var(--st-anomaly-surface);
}

/* 뷰포트 압축 — dashboard.js 의 syncKpiCompress() 가 붙이는 훅.
   기존 .dash-stats__tile 규칙을 그대로 계승한다. */
#dash-host-kpi[data-kpi-compress="true"] .kpi-card {
  padding-top: 0.375rem;
  padding-bottom: 0.375rem;
}

#dash-host-kpi[data-kpi-compress="true"] .kpi-card__note {
  display: none;
}
```

`app/web/frontend/components/kpi-card/macro.jinja`:

```jinja
{% macro kpi_card(key, label, value, unit="", period="", note="", tone="pending", href="", estimated=false) -%}
{% set tag = "a" if href else "article" %}
<{{ tag }} class="kpi-card" data-tone="{{ tone }}" data-key="{{ key }}"{% if href %} href="{{ href }}"{% endif %}>
  <span class="kpi-card__label">{{ label }}{% if period %} · {{ period }}{% endif %}{% if estimated %}<span class="kpi-card__badge">추정</span>{% endif %}</span>
  <span class="kpi-card__value-wrap">
    <span class="kpi-card__value"{% if value is number %} data-target="{{ value }}"{% endif %}>{{ value }}</span>{% if unit %}<span class="kpi-card__unit">{{ unit }}</span>{% endif %}
  </span>
  {% if note %}<span class="kpi-card__note">{{ note }}</span>{% endif %}
</{{ tag }}>
{%- endmacro %}

{% macro kpi_band(cards) -%}
<section id="dash-zone-stats" class="kpi-band">
  {% for card in cards %}
  {{ kpi_card(card.key, card.label, card.value, card.unit, card.period, card.note, card.tone, card.href, card.estimated) }}
  {% endfor %}
</section>
{%- endmacro %}
```

- [ ] **Step 4: 엔트리에 등록한다**

`app/web/frontend/entries/main.ts` 에 추가:

```ts
import "../components/kpi-card/styles.css";
import { bindKpiCards } from "../components/kpi-card/index";
```

그리고 파일 끝에:

```ts
// htmx 가 KPI 프래그먼트를 갈아끼운 뒤에도 카운트업이 다시 걸려야 한다.
document.addEventListener("DOMContentLoaded", () => bindKpiCards());
document.body.addEventListener("htmx:afterSwap", (event) => {
  bindKpiCards((event.target as ParentNode) ?? document);
});
```

- [ ] **Step 5: 통과를 확인한다**

Run: `npm run test`
Expected: PASS

Run: `npm run typecheck && npm run lint && npm run build`
Expected: 전부 통과

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과 (FG-002 hex 0건, FG-004 400줄 이하)

- [ ] **Step 6: 커밋**

```bash
git add app/web/frontend/components/kpi-card/ app/web/frontend/entries/main.ts
git commit -m "feat(frontend): KpiCard 컴포넌트 추가(매크로·카운트업·토큰 스타일)"
```

---

## Task 7: `zone_a_kpi.html` 재구성 + 밴드 교체

**Files:**
- Modify: `app/web/templates/dashboard/partials/zone_a_kpi.html`
- Modify: `app/web/frontend/styles/dashboard.css` (98행, 256~305행)
- Modify: `app/web/static/dashboard.js:207-236`
- Modify: `app/web/templates/self_healing.html`
- Modify: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: Task 4 의 카드 계약(`key`·`label`·`value`·`unit`·`period`·`note`·`tone`·`href`·`estimated`), Task 6 의 `kpi_band` 매크로

- [ ] **Step 1: 뷰포트·렌더 테스트를 작성한다**

`tests/test_dashboard_viewport.py` 에 추가:

```python
def test_kpi_band_replaces_stats_band(kpi_fragment_html):
    """밴드를 더하지 않고 교체한다 — 넌스크롤 예산이 늘면 안 된다."""
    assert "kpi-band" in kpi_fragment_html
    assert "dash-stats" not in kpi_fragment_html


def test_kpi_band_renders_exactly_four_cards(kpi_fragment_html):
    assert kpi_fragment_html.count('class="kpi-card"') == 4


def test_hero_no_longer_duplicates_pass_rate(kpi_fragment_html):
    """통과율은 밴드 1번 칸에만 있다(설계 D2)."""
    assert "dash-hero__rate" not in kpi_fragment_html


def test_estimated_card_shows_badge_and_note(kpi_fragment_html):
    assert "kpi-card__badge" in kpi_fragment_html
    assert "추정" in kpi_fragment_html


def test_pending_patches_card_links_to_patches(kpi_fragment_html):
    assert 'href="/self-healing#patches"' in kpi_fragment_html
```

픽스처는 Task 5 의 `tests/test_daily_summary_http.py` 와 같은 방식으로 만든다.

```python
@pytest.fixture()
def kpi_fragment_html():
    from tests.test_daily_summary_http import SUMMARY, FakeDailySummaryQueries, _member
    from app.api.dependencies import get_daily_queries, get_daily_summary_queries
    from app.api.routes_daily import router as daily_router
    from app.contexts.identity.dependencies import get_current_user

    app = FastAPI()
    app.include_router(daily_router)
    app.dependency_overrides[get_daily_summary_queries] = lambda: FakeDailySummaryQueries()
    app.dependency_overrides[get_daily_queries] = lambda: None
    app.dependency_overrides[get_current_user] = _member
    with TestClient(app) as client:
        response = client.get("/api/dashboard/daily/fragments/kpi")
        assert response.status_code == 200, response.text
        return response.text
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_dashboard_viewport.py -v -k kpi`
Expected: FAIL — `kpi-band` 없음

- [ ] **Step 3: `zone_a_kpi.html` 을 재구성한다**

전체를 다음으로 교체한다:

```jinja
{# Zone A hero + KPI 밴드 + attention strip.
   밴드는 기존 dash-stats(상태 4타일)를 교체한 것이다 — 넌스크롤 뷰포트 예산을
   늘리지 않기 위해 추가가 아니라 교체다(설계 D1). #}
{% import "components/kpi-card/macro.jinja" as kpi %}
{% set t = data.totals %}
<section id="dash-zone-hero" class="dash-hero">
  <div class="dash-hero__top">
    <div class="dash-hero__text">
      <h1 class="dash-hero__title">
        {% if t.modules == 0 %}점검 대상이 없습니다
        {% elif t.error > 0 %}점검실패 {{ t.error }}건 — 우선 확인이 필요합니다
        {% elif t.anomaly > 0 %}이상징후 {{ t.anomaly }}건이 감지되었습니다
        {% elif t.running > 0 %}{{ t.running }}개 모듈이 진행 중입니다
        {% elif t.not_inspected == t.modules %}오늘 아직 점검이 시작되지 않았습니다
        {% else %}오늘 점검은 정상입니다
        {% endif %}
      </h1>
      <p class="dash-hero__meta">
        {{ data.date_label }} · {{ t.passed }}/{{ t.modules }} 모듈 정상
        {% if t.anomaly > 0 %} · 이상징후 {{ t.anomaly }}건{% endif %}
        {% if t.error > 0 %} · 점검실패 {{ t.error }}건{% endif %}
        {% if data.generated_at %} · 갱신 {{ data.generated_at[11:16] }}{% endif %}
      </p>
    </div>
    <div class="dash-hero__aside">
      <div class="dash-hero__actions">
        <button id="dash-refresh" type="button" class="dash-refresh" aria-label="새로고침">
          <svg class="dash-refresh__icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          새로고침
        </button>
        <span id="dash-htmx-busy" class="dash-htmx-indicator">갱신…</span>
      </div>
    </div>
  </div>
</section>

{{ kpi.kpi_band(data.cards) }}

{% if data.attention %}
<section id="dash-zone-attention" class="dash-attention">
  <div class="dash-attention__item" data-tone="{{ data.attention[0].tone }}">
    <span class="dash-attention__dot" aria-hidden="true"></span>
    <span class="dash-attention__text">
      <strong>{{ data.attention[0].system_name }}</strong>
      {% if data.attention[0].module_name %} · {{ data.attention[0].module_name }}{% endif %}
      · {{ data.attention[0].status_label }}
    </span>
    {% if data.attention[0].run_id %}
    <a href="/runs/{{ data.attention[0].run_id }}" class="dash-attention__link">Run</a>
    {% endif %}
  </div>
  {% if data.attention|length > 1 %}
  <span class="dash-attention__more">+{{ data.attention|length - 1 }}건</span>
  {% endif %}
  <a href="/anomalies" class="dash-attention__inbox">전체 보기</a>
</section>
{% endif %}
```

밴드의 `id="dash-zone-stats"` 는 `kpi_band` 매크로가 유지하므로 `dashboard.js` 의 기존 셀렉터가 계속 동작한다.

- [ ] **Step 4: `dashboard.css` 에서 죽은 규칙을 제거한다**

삭제 대상:

- 98행 `#dash-host-kpi[data-kpi-compress="true"] .dash-stats__tile { ... }` — `kpi-card/styles.css` 로 이관됨
- 256~305행 `.dash-stats`, `.dash-stats__tile`, `.dash-stats__value`, `.dash-stats__label` 과 `data-tone` 4개 규칙, 미디어쿼리 안의 `.dash-stats__value`·`.dash-stats__label`
- 117행 `.dash-kpi__value` — 카드가 `.kpi-card__value` 를 쓰므로 히어로 전용 규칙이 남아 있으면 함께 정리한다. `dash-hero__rate` 관련 규칙도 삭제한다(D2 로 마크업이 사라짐).

Run: `grep -n "dash-stats\|dash-hero__rate\|dash-kpi__value" app/web/frontend/styles/dashboard.css`
Expected: 출력 없음

- [ ] **Step 5: `dashboard.js` 의 카운트업을 제거한다**

`app/web/static/dashboard.js` 에서 `animateCountUp`(207행)과 `runHeroCountUp`(230행), 그리고 그 호출부를 삭제한다. 카운트업은 이제 `kpi-card/index.ts` 가 담당한다.

`syncKpiCompress`(72행)는 **남긴다** — 셀렉터가 `#dash-host-kpi` 라 마크업 교체와 무관하게 계속 동작한다.

Run: `grep -n "animateCountUp\|runHeroCountUp\|dash-kpi__value" app/web/static/dashboard.js`
Expected: 출력 없음

- [ ] **Step 6: 패치 목록 앵커를 추가한다**

`app/web/templates/self_healing.html` 에서 승인 대기 패치 목록을 감싸는 섹션에 `id="patches"` 를 추가한다. 해당 섹션은 `grep -n "패치" app/web/templates/self_healing.html` 로 찾는다.

Run: `grep -n 'id="patches"' app/web/templates/self_healing.html`
Expected: 1건

- [ ] **Step 7: 통과를 확인한다**

Run: `python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py -v`
Expected: PASS

Run: `npm run build`
Expected: 성공

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과

- [ ] **Step 8: 화면을 육안 검증한다**

앱을 띄우고(`docs/INSTALL.md`) 비관리자 계정으로 로그인해 `/` 를 연다.

확인 항목:
- **스크롤바가 생기지 않는가** (넌스크롤 불변식) — 창 높이를 768px 까지 줄여서도 확인
- KPI 카드 4장이 한 줄에 보이는가
- "내 승인 대기" 카드만 색이 다른가
- "이번 달 절감" 카드에 `추정` 배지와 근거 줄이 있는가
- 절감 추정치가 미설정이면 "추정치 미설정" 과 링크가 보이는가
- 카드 숫자가 카운트업 애니메이션되는가
- 새로고침 버튼(htmx 재요청) 후에도 카운트업이 다시 도는가
- "내 승인 대기" 클릭 시 `/self-healing` 패치 목록으로 이동하는가
- 브라우저 콘솔 에러 0건

창을 줄였을 때 카드가 뭉개지면 `syncKpiCompress` 가 `data-kpi-compress="true"` 를 붙이는지 개발자도구로 확인한다. 붙는데도 넘치면 `kpi-card/styles.css` 의 압축 규칙에 `.kpi-card__label` 폰트 축소를 추가한다.

- [ ] **Step 9: 전체 게이트**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `npm run test && npm run typecheck && npm run lint`
Expected: 전부 통과

- [ ] **Step 10: 커밋**

```bash
git add app/web/templates/dashboard/partials/zone_a_kpi.html \
        app/web/frontend/styles/dashboard.css app/web/static/dashboard.js \
        app/web/templates/self_healing.html tests/test_dashboard_viewport.py
git commit -m "feat(dashboard): 상태 타일을 KPI 카드 4장으로 교체 — 절감·자동복구·승인대기 노출"
```

---

## 완료 기준 (P2 DoD)

- [ ] `grep -rn "build_daily_dashboard\b" app --include=*.py | grep -v _from_projection` → 출력 없음
- [ ] `python3 -m pytest tests/ -q` → 전부 통과
- [ ] `npm run build && npm run typecheck && npm run lint && npm run test` → 전부 통과
- [ ] `python3 scripts/ci/run_all_gates.py --profile full` → 전 게이트 통과
- [ ] **비관리자 계정**으로 `/` 에서 절감 시간이 보인다
- [ ] `/api/dashboard/daily/summary` 응답 본문에 `email`·`user_id`·`user_name`·`by_user` 문자열 0건
- [ ] `/api/admin/stats/usage` 는 비관리자에게 여전히 401/403
- [ ] KPI 4장 모두 기간 라벨 보유
- [ ] 추정 카드에 `추정` 배지 + 근거 줄 존재
- [ ] 창 높이 768px 에서 스크롤바 없음
- [ ] KST 아침 시간대(UTC 전날) 에도 healing "오늘" 이 일간 `date_label` 과 일치 (`tests/test_healing_day_boundary.py`)

---

## P2 이후

P3 가 이 계획의 산출물에 직접 의존한다:

- `kpi_band` / `kpi_card` 매크로 — 상황판은 대형 모드, 메일 리포트는 인라인으로 재사용
- `GET /api/dashboard/daily/summary` — 상황판·리포트가 같은 JSON 을 소비
- `build_daily_summary()` 카드 계약 (`key` 4종 고정)
- `day_label` 인자 — 상황판·리포트도 같은 날짜 기준을 써야 한다

**두 번 이월된 항목:** 자동 화면 스모크 테스트(콘솔 에러 0). P1·P2 모두 인증 불필요 렌더 경로가 없어 미뤘다. P3 에서 상황판 `/wall` 을 만들 때 토큰 기반 읽기 전용 경로가 생기므로, 그때 붙인다.
