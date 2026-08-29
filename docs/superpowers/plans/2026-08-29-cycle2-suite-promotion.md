# Cycle 2: 수트 상세 승격 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수트 상세를 넌스크롤 수직 파이프라인으로 승격하고, `app.js` 의 수트 몫 약 568줄을 `entries/suite.ts` 로 이관한다.

**Architecture:** 서버가 먼저 두 가지를 준비한다 — 시스템별 평균 소요시간(ETA baseline)과 "어느 스텝을 펼칠지"(`expanded_step_order`). 둘 다 기존 확장점에 얹는다: baseline 은 `RunSummaryQueryPort` 의 형제 집계 메서드, 펼침은 `SuiteView` 의 파생 필드다. 도메인 모델과 이벤트 wire 는 한 줄도 바뀌지 않는다. 그다음 프런트에서 순수 로직(진행률·ETA) → DOM 모듈 → **전환(템플릿 재작성 + 배선 + `app.js` 절단)** 순으로 간다. 전환은 원자적이어야 하므로 한 태스크에 묶는다.

**Tech Stack:** FastAPI · Pydantic · SQLite(`run_history_index` 프로젝션) · Jinja2 · TypeScript 5.6 · Vite 6 다중 엔트리 · Vitest 3 + jsdom · Tailwind v4 · pytest + Playwright

**Spec:** `docs/superpowers/specs/2026-08-29-suite-promotion-design.md`

## Global Constraints

- **도메인 모델과 이벤트 wire 를 한 줄도 바꾸지 않는다**(D9). `app/core/suite_models.py` · `app/contexts/suite/domain/events.py` 는 이 계획에서 **수정 대상이 아니다.** `snapshot_validate` · `projection_validate` 게이트가 diff 0 이어야 한다.
- **색 SSOT 는 `app/core/status_colors.py` 의 `PALETTE`.** 새 hex 를 적지 않는다. FG-002 가 `templates/` 와 `static/*.js` 까지 스캔한다.
- **상태 라벨·톤은 서버 주입만**(FG-003 · FG-006). 배지는 `components/status-badge` 를 쓴다.
- **`/static/` 직접 참조 금지**(FG-005). 자산은 `_assets.html` 매크로 경유.
- **파일 400줄 상한**(FG-004). 넘치면 책임 단위로 쪼갠다.
- **넌스크롤 예산:** `body` 세로 스크롤 0. 내부 스크롤은 **스텝 목록 하나뿐.** 최악 조건(1366×768 · 시스템 6개 · OTP 대기)에서 여유가 ~109px 뿐이다.
- **`is_visible()` 로 가시성을 단언하지 않는다.** 뷰포트 밖 요소를 통과시킨다. `bounding_box()` 좌표로 단언한다.
- **UI 문자열은 한국어**(AGENTS.md).
- **PR 전 필수:** `python3 scripts/ci/run_all_gates.py --profile full`

## File Structure

| 파일 | 책임 | 상태 |
| --- | --- | --- |
| `app/contexts/run/contracts/ports.py` | `avg_duration_ms_by_system` 시그니처 추가 | 수정 |
| `app/contexts/run/infrastructure/sqlite_run_summary_query.py` | 위 메서드 SQL 구현 | 수정 |
| `app/contexts/run/infrastructure/in_memory_run_summary_query.py` | 위 메서드 메모리 구현 | 수정 |
| `app/contexts/suite/views/view.py` | `expanded_step_order` 파생 필드 + 계산 함수 | 수정 |
| `app/api/routes_dashboard.py:152` | `step_baselines` 주입 | 수정 |
| `app/web/frontend/styles/shell.css` | `.dash`·`.exec`·`.suite` 공통 넌스크롤 셸 | **신규** |
| `app/web/frontend/lib/otp-countdown.ts` | OTP 카운트다운(런·수트 공용) | **신규** |
| `app/web/frontend/suite/progress.ts` | 모듈 진행 계산(순수) | **신규** |
| `app/web/frontend/suite/eta.ts` | 남은 시간 계산(순수) | **신규** |
| `app/web/frontend/suite/steps.ts` | 스텝 행·모듈 칩 DOM | **신규** |
| `app/web/frontend/suite/render.ts` | 스냅샷 렌더·진도 블록 | **신규** |
| `app/web/frontend/suite/socket.ts` | 수트 소켓 + 하위 Run 진행 소켓 | **신규** |
| `app/web/frontend/suite/actions.ts` | 취소·OTP 제출·OTP 패널 | **신규** |
| `app/web/frontend/suite/styles.css` | 수트 화면 컴포넌트 CSS | **신규** |
| `app/web/frontend/entries/suite.ts` | 배선만 | **신규** |
| `app/web/templates/suite.html` | 마크업 전면 재작성 | 수정 |
| `app/web/static/app.js` | 수트 몫 ~568줄 삭제 | 수정 |
| `vite.config.ts` · `base.css` | 엔트리·임포트 등록 | 수정 |

---

### Task 1: 시스템별 평균 소요시간 쿼리

ETA 의 baseline. 서버 단독이라 UI 없이 완결된다.

**Files:**
- Modify: `app/contexts/run/contracts/ports.py:36-58`
- Modify: `app/contexts/run/infrastructure/sqlite_run_summary_query.py`
- Modify: `app/contexts/run/infrastructure/in_memory_run_summary_query.py`
- Test: `tests/test_suite_eta_baseline.py`

**Interfaces:**
- Consumes: `run_history_index` 테이블(`app/platform/eventing/support.py:183`) — `system_code` · `status` · `requested_at` · `started_at` · `ended_at` 컬럼과 `idx_run_history_system` 인덱스
- Produces: `RunSummaryQueryPort.avg_duration_ms_by_system(*, days: int = 30) -> dict[str, int]` — 시스템 코드 → 평균 소요 밀리초(반올림 정수). **이력이 없는 시스템은 키 자체가 없다**(0 이 아니다). Task 4 의 라우트 주입이 소비한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_suite_eta_baseline.py` 를 만든다. 픽스처 방식은 `tests/test_summary_queries.py` 를 따른다 — `SqliteDatabase` + `ensure_schema` + 프로젝션 핸들러로 이벤트를 흘려 인덱스를 채운다. 그 파일의 `_run(...)` 헬퍼와 `run_events_as_envelopes` 사용법을 그대로 읽고 맞춘다.

```python
"""ETA baseline — 시스템별 평균 Run 소요시간.

'정상 실행이 얼마나 걸리는가' 를 재는 것이므로 PASSED 만 센다. 중간에 끊긴
Run 을 섞으면 평균이 짧아져 ETA 가 낙관적으로 빗나간다(설계 D3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.run.infrastructure.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.core.enums import RunStatus


def _row(system_code: str, status: RunStatus, *, started_min: int, duration_min: int | None):
    """테스트용 run_history_index 행 한 줄."""
    base = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    started = base + timedelta(minutes=started_min)
    ended = started + timedelta(minutes=duration_min) if duration_min is not None else None
    return {
        "system_code": system_code,
        "status": status,
        "requested_at": started,
        "started_at": started,
        "ended_at": ended,
    }


async def test_averages_only_passed_runs(memory_query) -> None:
    """실패 Run 이 평균을 끌어내리면 안 된다."""
    await memory_query.seed(
        [
            _row("hom", RunStatus.PASSED, started_min=0, duration_min=4),
            _row("hom", RunStatus.PASSED, started_min=60, duration_min=6),
            _row("hom", RunStatus.ERROR, started_min=120, duration_min=1),
        ]
    )
    result = await memory_query.avg_duration_ms_by_system()
    assert result["hom"] == 5 * 60 * 1000


async def test_unfinished_runs_are_excluded(memory_query) -> None:
    """진행 중인 Run 은 ended_at 이 없어 표본이 아니다."""
    await memory_query.seed(
        [
            _row("mhm", RunStatus.PASSED, started_min=0, duration_min=2),
            _row("mhm", RunStatus.RUNNING, started_min=10, duration_min=None),
        ]
    )
    assert (await memory_query.avg_duration_ms_by_system())["mhm"] == 2 * 60 * 1000


async def test_system_without_history_has_no_key(memory_query) -> None:
    """0 을 돌려주면 화면이 '평균 0초' 를 표시한다. 키가 없어야 '평균 —' 로 갈린다."""
    await memory_query.seed([_row("hom", RunStatus.PASSED, started_min=0, duration_min=3)])
    result = await memory_query.avg_duration_ms_by_system()
    assert "chbot" not in result


async def test_days_window_excludes_older_runs(memory_query) -> None:
    old = _row("fp", RunStatus.PASSED, started_min=0, duration_min=10)
    old["requested_at"] = datetime(2026, 1, 1, tzinfo=UTC)
    await memory_query.seed([old, _row("fp", RunStatus.PASSED, started_min=0, duration_min=2)])
    assert (await memory_query.avg_duration_ms_by_system(days=30))["fp"] == 2 * 60 * 1000


async def test_sqlite_and_memory_agree(sqlite_query, memory_query) -> None:
    """두 어댑터가 갈라지면 테스트가 프로덕션을 대변하지 못한다."""
    rows = [
        _row("hom", RunStatus.PASSED, started_min=0, duration_min=4),
        _row("hom", RunStatus.PASSED, started_min=60, duration_min=6),
        _row("hom", RunStatus.ERROR, started_min=120, duration_min=1),
        _row("mhm", RunStatus.PASSED, started_min=0, duration_min=2),
    ]
    await memory_query.seed(rows)
    await sqlite_query.seed(rows)
    assert await sqlite_query.avg_duration_ms_by_system() == await memory_query.avg_duration_ms_by_system()
```

`memory_query` · `sqlite_query` 픽스처와 `seed(...)` 헬퍼는 이 파일 안에 만든다. sqlite 쪽은 `run_history_index` 에 직접 INSERT 하는 것이 가장 짧다 — 이 테스트가 검증하는 것은 프로젝션이 아니라 집계 SQL 이다. `ensure_schema` 로 스키마를 만든 뒤 `INSERT INTO run_history_index (run_id, system_code, status, requested_at, started_at, ended_at) VALUES (...)` 로 채우고, 나머지 NOT NULL 컬럼(`status`·`requested_at`)만 맞춘다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_suite_eta_baseline.py -v`
Expected: FAIL — `AttributeError: 'InMemoryRunSummaryQuery' object has no attribute 'avg_duration_ms_by_system'`

- [ ] **Step 3: 포트에 시그니처를 추가한다**

`app/contexts/run/contracts/ports.py` 의 `RunSummaryQueryPort` 에 `last_finished_at_by_system` 옆으로 넣는다.

```python
    async def avg_duration_ms_by_system(self, *, days: int = 30) -> dict[str, int]: ...
```

- [ ] **Step 4: sqlite 어댑터를 구현한다**

`app/contexts/run/infrastructure/sqlite_run_summary_query.py` 의 `last_finished_at_by_system`(`:231`) 아래에 추가한다.

```python
    async def avg_duration_ms_by_system(self, *, days: int = 30) -> dict[str, int]:
        """시스템별 평균 Run 소요시간(ms) — ETA baseline(설계 §3.3).

        PASSED 만 센다. 중간에 끊긴 Run 의 소요시간은 '정상 실행이 얼마나 걸리는가'
        의 표본이 아니며, 섞으면 평균이 짧아져 ETA 가 낙관적으로 빗나간다.
        run_history_index 에 duration 컬럼이 없어 시각 차로 계산한다.
        """
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        rows = await self._db.fetchall(
            """
            SELECT system_code,
                   AVG((julianday(ended_at) - julianday(started_at)) * 86400000.0) AS avg_ms
            FROM run_history_index
            WHERE ended_at IS NOT NULL
              AND started_at IS NOT NULL
              AND status = ?
              AND requested_at >= ?
            GROUP BY system_code
            """,
            (RunStatus.PASSED.value, since),
        )
        result: dict[str, int] = {}
        for row in rows:
            value = row["avg_ms"]
            if value is None:
                continue
            result[row["system_code"]] = round(value)
        return result
```

`datetime` · `timedelta` · `UTC` · `RunStatus` 임포트가 파일 상단에 있는지 확인하고 없으면 추가한다. `status` 컬럼에 저장되는 값의 형태(`"PASSED"` 인지 `"RunStatus.PASSED"` 인지)를 **실제 인덱스에서 확인하고 맞춘다** — 같은 파일의 다른 쿼리가 status 를 어떻게 비교하는지 보면 된다.

- [ ] **Step 5: in-memory 어댑터를 구현한다**

`app/contexts/run/infrastructure/in_memory_run_summary_query.py` 의 `last_finished_at_by_system`(`:159`) 아래에 추가한다.

```python
    async def avg_duration_ms_by_system(self, *, days: int = 30) -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        buckets: dict[str, list[float]] = {}
        for row in await self._all_rows():
            if row.status != RunStatus.PASSED:
                continue
            if row.started_at is None or row.ended_at is None:
                continue
            if row.requested_at < cutoff:
                continue
            buckets.setdefault(row.system_code, []).append(
                (row.ended_at - row.started_at).total_seconds() * 1000.0
            )
        return {code: round(sum(v) / len(v)) for code, v in buckets.items() if v}
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_suite_eta_baseline.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: 아키텍처 게이트 확인**

Run: `python3 scripts/check_architecture_gates.py && python3 -m pytest tests/test_ci_config_valid.py -q`
Expected: 통과. import-linter 계약을 건드리지 않았으므로 변화가 없어야 한다.

- [ ] **Step 8: 커밋**

```bash
git add app/contexts/run tests/test_suite_eta_baseline.py
git commit -m "feat(suite): 시스템별 평균 소요시간 쿼리 — ETA baseline"
```

---

### Task 2: `expanded_step_order` 파생 필드

"어느 스텝을 펼칠지" 를 서버가 정한다(설계 D8).

**Files:**
- Modify: `app/contexts/suite/views/view.py`
- Test: `tests/test_suite_expanded_step.py`

**Interfaces:**
- Consumes: `SuiteRun`(`app/core/suite_models.py:21`) — `status` · `steps` · `current_step_index` · `awaiting_input_run_id`
- Produces:
  - `compute_expanded_step_order(status: SuiteStatus, steps: list[SuiteStep], current_step_index: int, awaiting_input_run_id: str | None) -> int | None` — 모듈 수준 순수 함수
  - `SuiteView.expanded_step_order: int | None` — 필드
  - Task 7 의 `suite/render.ts` 가 WS 페이로드에서 이 키를 읽는다

- [ ] **Step 1: 두 직렬화 경로를 먼저 읽는다**

`app/contexts/suite/views/view.py` 에는 구성 경로가 **둘** 있다.

| 경로 | 용도 |
| --- | --- |
| `from_suite(suite)` → `dump(suite)`(`:75`) | 페이지 렌더 · REST · WS 스냅샷 |
| `dump_from_summary(suite_id, summary)`(`:80`) | 실시간 프로젝터가 fat event 요약으로 blob 재수화 없이 만든다 |

**둘 다 고쳐야 한다.** `from_suite` 만 고치면 최초 렌더에는 필드가 있고 WS 갱신에는 없어서, 소켓 이벤트가 올 때마다 펼침이 사라진다. 계산 함수를 모듈 수준에 두고 양쪽이 호출하게 한다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_suite_expanded_step.py`:

```python
"""자동 펼침 규칙 — 어느 스텝을 펼칠지는 수트 상태의 순수 함수다(설계 D4·D8).

클라이언트가 같은 규칙을 다시 구현하면 서버 렌더와 WS 갱신이 두 벌이 되어
어긋난다. 규칙은 여기 하나뿐이다.
"""

from __future__ import annotations

from app.contexts.suite.views.view import compute_expanded_step_order
from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteStep


def _steps(*specs: tuple[str, SuiteStatus, str | None]) -> list[SuiteStep]:
    return [
        SuiteStep(
            system_code=code,
            system_name=code.upper(),
            order=index,
            run_id=run_id,
            status=status,
            module_total=3,
        )
        for index, (code, status, run_id) in enumerate(specs)
    ]


def test_running_expands_current_step() -> None:
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.RUNNING, "r2"),
        ("fp", SuiteStatus.PENDING, None),
    )
    assert compute_expanded_step_order(SuiteStatus.RUNNING, steps, 1, None) == 1


def test_waiting_input_wins_over_current_index() -> None:
    """입력 대기가 현재 인덱스와 어긋나도 사람이 볼 곳은 대기 중인 스텝이다."""
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.WAITING_INPUT, "r2"),
        ("fp", SuiteStatus.PENDING, None),
    )
    assert compute_expanded_step_order(SuiteStatus.WAITING_INPUT, steps, 2, "r2") == 1


def test_terminal_expands_first_error() -> None:
    steps = _steps(
        ("hom", SuiteStatus.ANOMALY, "r1"),
        ("mhm", SuiteStatus.ERROR, "r2"),
        ("fp", SuiteStatus.ERROR, "r3"),
    )
    assert compute_expanded_step_order(SuiteStatus.ERROR, steps, 2, None) == 1


def test_terminal_falls_back_to_first_anomaly() -> None:
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.ANOMALY, "r2"),
        ("fp", SuiteStatus.PASSED, "r3"),
    )
    assert compute_expanded_step_order(SuiteStatus.ANOMALY, steps, 2, None) == 1


def test_all_passed_expands_nothing() -> None:
    """전부 정상이면 6줄이 그대로 결과 목록이 된다."""
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.PASSED, "r2"),
    )
    assert compute_expanded_step_order(SuiteStatus.PASSED, steps, 1, None) is None


def test_empty_steps_returns_none() -> None:
    assert compute_expanded_step_order(SuiteStatus.PENDING, [], 0, None) is None


def test_current_index_out_of_range_returns_none() -> None:
    """인덱스가 스텝 수를 넘어도 예외를 던지지 않는다."""
    steps = _steps(("hom", SuiteStatus.PASSED, "r1"))
    assert compute_expanded_step_order(SuiteStatus.RUNNING, steps, 9, None) is None
```

그리고 **두 직렬화 경로가 모두** 필드를 싣는지 단언한다. Step 1 이 설명한 결함(한쪽만 고쳐 WS 갱신마다 펼침이 사라짐)은 정확히 이 두 단언으로만 잡힌다.

```python
from datetime import UTC, datetime

from app.contexts.suite.views.view import SuiteView
from app.core.suite_models import SuiteRun


def _suite() -> SuiteRun:
    return SuiteRun(
        suite_id="suite_test",
        status=SuiteStatus.RUNNING,
        steps=_steps(
            ("hom", SuiteStatus.PASSED, "r1"),
            ("mhm", SuiteStatus.RUNNING, "r2"),
        ),
        current_step_index=1,
        requested_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        selected_system_codes=["hom", "mhm"],
    )


def test_dump_carries_the_field() -> None:
    payload = SuiteView.dump(_suite())
    assert payload["expanded_step_order"] == 1


def test_dump_from_summary_carries_the_field() -> None:
    """실시간 프로젝터 경로. 여기가 빠지면 소켓 이벤트마다 펼침이 사라진다."""
    suite = _suite()
    summary = SuiteView.dump(suite)
    payload = SuiteView.dump_from_summary(suite.suite_id, summary)
    assert payload["expanded_step_order"] == 1
```

`dump_from_summary` 가 기대하는 `summary` 의 정확한 형태는 `app/domain/summary_fields.py` 의 `suite_summary_fields` 가 만든다. 위처럼 `dump(suite)` 결과를 그대로 넘겨서 키가 맞지 않으면, `suite_summary_fields(suite)` 를 호출해 진짜 요약을 만들어 넘긴다 — **어느 쪽이든 프로덕션이 실제로 넘기는 것과 같은 형태여야 한다.**

- [ ] **Step 3: 실패를 확인한다**

Run: `python3 -m pytest tests/test_suite_expanded_step.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_expanded_step_order'`

- [ ] **Step 4: 계산 함수를 구현한다**

`app/contexts/suite/views/view.py` 의 `SuiteView` 클래스 **위**에 모듈 수준 함수로 둔다.

```python
_TERMINAL_EXPAND_ORDER = (SuiteStatus.ERROR, SuiteStatus.ANOMALY)


def compute_expanded_step_order(
    status: SuiteStatus,
    steps: list[SuiteStep],
    current_step_index: int,
    awaiting_input_run_id: str | None,
) -> int | None:
    """자동으로 펼칠 스텝의 order — 수트 상태의 순수 함수(설계 D4·D8).

    진행 중: 입력 대기 스텝이 있으면 그것, 없으면 현재 스텝.
    종료됨: 첫 error → 없으면 첫 anomaly → 없으면 없음(전부 접힘).

    클라이언트가 같은 규칙을 다시 구현하면 서버 렌더와 WS 갱신이 어긋난다.
    """
    if not steps:
        return None

    if awaiting_input_run_id:
        for step in steps:
            if step.run_id == awaiting_input_run_id:
                return step.order

    for step in steps:
        if step.status == SuiteStatus.WAITING_INPUT:
            return step.order

    if status in _SUITE_ACTIVE_VIEW_STATUSES:
        for step in steps:
            if step.order == current_step_index:
                return step.order
        return None

    for wanted in _TERMINAL_EXPAND_ORDER:
        for step in steps:
            if step.status == wanted:
                return step.order
    return None
```

`_SUITE_ACTIVE_VIEW_STATUSES` 는 `{SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}` 로 같은 파일 상단에 정의한다. `app/contexts/suite/domain/aggregate.py` 에 `_SUITE_ACTIVE` 라는 같은 집합이 있으나 **도메인에서 import 하지 않는다** — 뷰가 도메인 내부 상수에 묶이면 D9(도메인 불변)의 취지가 흐려진다.

- [ ] **Step 5: 두 직렬화 경로에 필드를 싣는다**

`SuiteView` 에 필드를 추가한다.

```python
    expanded_step_order: int | None = None
```

`from_suite` 의 `cls(...)` 호출에 추가한다.

```python
            expanded_step_order=compute_expanded_step_order(
                suite.status, suite.steps, suite.current_step_index, suite.awaiting_input_run_id
            ),
```

`dump_from_summary` 에서도 같은 값을 계산해 넣는다. 이 경로는 `summary` dict 로 `SuiteStep` 리스트를 재구성하므로, 재구성이 끝난 뒤 같은 함수를 부른다.

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_suite_expanded_step.py -v`
Expected: PASS

- [ ] **Step 7: 도메인 불변을 확인한다**

Run: `python3 -m pytest tests/test_suite_event_codec.py tests/test_snapshot_rebuild.py tests/test_projection_handlers.py -v`
Expected: PASS. 도메인·wire 를 건드리지 않았으므로 한 건도 바뀌면 안 된다.

- [ ] **Step 8: 커밋**

```bash
git add app/contexts/suite/views/view.py tests/test_suite_expanded_step.py
git commit -m "feat(suite): 자동 펼침 스텝을 뷰 파생 필드로 계산"
```

---

### Task 3: 넌스크롤 공통 셸 추출

`.dash`·`.exec` 에 이어 `.suite` 가 세 번째 소비자다(설계 D7).

**Files:**
- Create: `app/web/frontend/styles/shell.css`
- Modify: `app/web/frontend/styles/dashboard.css` (셸 블록 제거)
- Modify: `app/web/frontend/styles/execute.css` (셸 블록 제거)
- Modify: `app/web/frontend/styles/base.css` (임포트)
- Test: `tests/frontend/test_shell_css_ownership.py`

**Interfaces:**
- Consumes: 없음
- Produces: `body:has(.dash)` · `body:has(.exec)` · `body:has(.suite)` 세 셀렉터에 같은 넌스크롤 규칙. Task 6 의 `suite.html` 이 `.suite` 를 붙여 소비한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

Cycle 1b 가 만든 `tests/frontend/test_execute_preset_css_migration.py` 의 소유권 단언 방식을 따른다.

```python
"""넌스크롤 셸의 소유권 — 세 화면이 같은 규칙을 각자 복제하지 않는다.

dashboard.css 와 execute.css 가 같은 body:has(...) 블록을 한 벌씩 갖고 있었다.
세 번째 소비자(.suite)가 생기는 시점에 공통으로 뽑는다(설계 D7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "app/web/frontend/styles"
SHELL = STYLES / "shell.css"


def _text(name: str) -> str:
    return (STYLES / name).read_text(encoding="utf-8")


def test_shell_file_exists() -> None:
    assert SHELL.exists()


@pytest.mark.parametrize("selector", ["body:has(.dash)", "body:has(.exec)", "body:has(.suite)"])
def test_shell_owns_all_three_screens(selector: str) -> None:
    assert selector in _text("shell.css")


@pytest.mark.parametrize("name", ["dashboard.css", "execute.css"])
def test_screen_stylesheets_no_longer_own_the_shell(name: str) -> None:
    """복제가 남아 있으면 한쪽만 고쳤을 때 조용히 갈라진다."""
    assert "body:has(" not in _text(name)


def test_base_css_imports_shell_before_screen_sheets() -> None:
    """셸이 화면 시트보다 먼저 와야 화면 시트가 덮어쓸 수 있다."""
    base = _text("base.css")
    assert '@import "./shell.css";' in base
    assert base.index('@import "./shell.css";') < base.index('@import "./dashboard.css";')


def test_shell_has_no_hex() -> None:
    import re

    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", _text("shell.css"))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_shell_css_ownership.py -v`
Expected: FAIL — `shell.css` 없음

- [ ] **Step 3: 셸을 뽑는다**

`dashboard.css` 의 `/* ── Viewport-fit shell ── */` 블록(`body:has(.dash)` 계열, 미디어쿼리 포함)과 `execute.css` 의 같은 블록을 잘라 `shell.css` 로 옮긴다. 셀렉터 목록만 합치고 **선언은 한 줄도 바꾸지 않는다.**

```css
/* 넌스크롤 셸 — 관제탑 화면 공통(설계 D7).

   .dash(일간 대시보드) · .exec(점검 실행) · .suite(수트 상세)가 같은 규칙을
   쓴다. 세 번째 소비자가 생긴 시점에 dashboard.css·execute.css 의 복제를
   여기로 합쳤다. 네 번째(런 상세, Cycle 3)도 셀렉터만 추가하면 된다. */

body:has(.dash),
body:has(.exec),
body:has(.suite) {
  overflow: hidden;
  height: 100dvh;
  max-height: 100dvh;
  min-height: 0;
}
```

나머지 블록(`main`·`main > div`·미디어쿼리 두 개)도 같은 방식으로 세 셀렉터를 나열해 옮긴다. `.dash` 만 갖고 있던 `container-type: inline-size` 같은 화면 고유 규칙은 **옮기지 말고** `dashboard.css` 에 남긴다 — 셸이 아니라 그 화면의 것이다.

- [ ] **Step 4: base.css 에 임포트를 넣는다**

`@import "./tokens.generated.css";` 와 `@import "./legacy-aliases.css";` 다음, `@import "./app.css";` **앞**에 넣는다.

```css
@import "./shell.css";
```

- [ ] **Step 5: 테스트와 빌드를 확인한다**

Run: `python3 -m pytest tests/frontend/test_shell_css_ownership.py -v && npm run build`
Expected: PASS · 빌드 성공

- [ ] **Step 6: 기존 두 화면이 안 깨졌는지 확인한다**

Run: `python3 -m pytest tests/test_dashboard_viewport.py tests/test_execute_viewport.py -v`
Expected: PASS. 셸을 옮기기만 했으므로 한 건도 바뀌면 안 된다.

- [ ] **Step 7: 커밋**

```bash
git add app/web/frontend/styles tests/frontend/test_shell_css_ownership.py
git commit -m "refactor(styles): 넌스크롤 셸을 세 화면 공통으로 추출"
```

---

### Task 4: OTP 카운트다운을 `lib/` 로 승격

실제 공유분은 이것 하나뿐이다(설계 C1·C2·D6).

**Files:**
- Create: `app/web/frontend/lib/otp-countdown.ts`
- Create: `app/web/frontend/lib/otp-countdown.test.ts`
- Modify: `app/web/static/app.js:1132-1192`
- Modify: `app/web/frontend/execute/legacy-bridge.ts`
- Modify: `app/web/frontend/entries/execute.ts` 또는 카운트다운을 쓰는 `execute/` 모듈

**Interfaces:**
- Consumes: 없음
- Produces:
  - `startOtpCountdown(startedAtIso: string, target: HTMLElement): void`
  - `stopOtpCountdown(): void`
  - `moduleStartedAtFromRun(runPayload: unknown, moduleId: string): string | null`
  - Task 7 의 `suite/actions.ts` 와 기존 `execute/` 가 함께 소비한다

- [ ] **Step 1: 원본과 소비처를 읽는다**

`app/web/static/app.js:1132~1192` 의 `otpCountdownTimer` · `clearOtpCountdownTimer` · `stopOtpCountdown` · `startOtpCountdown` · `moduleStartedAtFromRun` 을 읽는다. 그리고 TS 쪽 소비처를 찾는다.

Run: `grep -rn "__executeLegacy" app/web/frontend --include=*.ts`

현재 `startOtpCountdown` 이 어느 DOM 노드에 쓰는지 확인한다. 원본이 특정 id 를 하드코딩하고 있으면 **대상 요소를 인자로 받도록 바꾼다** — 수트는 `#suite-otp-countdown`, 런은 기존 노드를 쓰므로 공용이 되려면 대상이 주입돼야 한다. 이것이 이 태스크에서 유일하게 동작이 바뀌는 지점이며, 위 `Produces` 시그니처가 그것을 반영한다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`app/web/frontend/lib/otp-countdown.test.ts`:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { moduleStartedAtFromRun, startOtpCountdown, stopOtpCountdown } from "./otp-countdown";

describe("startOtpCountdown", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    stopOtpCountdown();
    vi.useRealTimers();
  });

  it("대상 요소에 남은 시간을 쓴다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", el);
    expect(el.textContent).not.toBe("");
  });

  it("1초마다 갱신한다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", el);
    const first = el.textContent;
    vi.advanceTimersByTime(2000);
    expect(el.textContent).not.toBe(first);
  });

  it("두 번 시작해도 타이머가 하나만 남는다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const a = document.createElement("p");
    const b = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", a);
    const frozen = a.textContent;
    startOtpCountdown("2026-08-29T09:00:00Z", b);
    vi.advanceTimersByTime(3000);
    expect(a.textContent).toBe(frozen);
    expect(b.textContent).not.toBe(frozen);
  });

  it("stop 후에는 갱신이 멈춘다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", el);
    stopOtpCountdown();
    const frozen = el.textContent;
    vi.advanceTimersByTime(5000);
    expect(el.textContent).toBe(frozen);
  });
});

describe("moduleStartedAtFromRun", () => {
  it("해당 모듈의 started_at 을 찾는다", () => {
    const run = { modules: [{ module_id: "a", started_at: "2026-08-29T09:00:00Z" }] };
    expect(moduleStartedAtFromRun(run, "a")).toBe("2026-08-29T09:00:00Z");
  });

  it("없는 모듈이면 null", () => {
    expect(moduleStartedAtFromRun({ modules: [] }, "a")).toBeNull();
  });

  it("run 이 null 이어도 던지지 않는다", () => {
    expect(moduleStartedAtFromRun(null, "a")).toBeNull();
  });
});
```

세 번째 테스트("두 번 시작해도 타이머가 하나")가 이 모듈에서 가장 중요하다 — 수트와 런이 같은 타이머 슬롯을 공유하므로, 정리가 빠지면 두 화면을 오갈 때 타이머가 누적된다.

- [ ] **Step 3: 실패를 확인한다**

Run: `npm run test -- otp-countdown`
Expected: FAIL — 모듈 없음

- [ ] **Step 4: 모듈을 만들고 app.js 에서 지운다**

`app/web/frontend/lib/otp-countdown.ts` 를 만든다. `app.js:1132~1192` 의 로직을 옮기고 타입만 얹되, Step 1 에서 정한 대로 대상 요소를 인자로 받는다.

그다음 **같은 커밋에서** `app.js` 에서 지운다:
- `otpCountdownTimer` 변수와 함수 4개(`:1132~1192`)
- `window.__executeLegacy` 객체(`:1183~1192`)에서 `startOtpCountdown` · `stopOtpCountdown` · `moduleStartedAtFromRun` 세 키

남는 키는 `setInlineFeedback` · `readErrorMessage` · `bindScheduleBuilder` · `buildScheduleCron` · `refreshScheduleList` **5개**다.

`app/web/frontend/execute/legacy-bridge.ts` 의 타입 선언에서도 세 키를 지우고, 소비처가 `../lib/otp-countdown` 을 직접 import 하도록 바꾼다.

- [ ] **Step 5: 확인한다**

Run: `npm run test && npm run typecheck && npm run lint && npm run build`
Expected: 전부 PASS

Run: `grep -c "startOtpCountdown\|stopOtpCountdown\|moduleStartedAtFromRun" app/web/static/app.js`
Expected: `0`

- [ ] **Step 6: 런 상세 OTP 를 실물로 확인한다**

앱을 띄워 Run 하나를 OTP 구간까지 진행시키고 카운트다운이 도는지 본다. 이 태스크는 런 상세의 동작을 바꾸므로 **여기서 확인하지 않으면 Task 7 에서 원인이 섞인다.**

- [ ] **Step 7: 커밋**

```bash
git add app/web/frontend/lib app/web/frontend/execute app/web/frontend/entries app/web/static/app.js
git commit -m "refactor(otp): 카운트다운을 lib 로 승격 — 다리 8→5"
```

---

### Task 5: 수트 순수 로직 — 진행률과 ETA

DOM 을 모르는 계산. 가장 테스트하기 좋고 가장 조용히 깨지는 부분이다.

**Files:**
- Create: `app/web/frontend/suite/progress.ts`
- Create: `app/web/frontend/suite/progress.test.ts`
- Create: `app/web/frontend/suite/eta.ts`
- Create: `app/web/frontend/suite/eta.test.ts`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `type ModuleProgress = { current: number; total: number; label: string; moduleName: string; tone: string }`
  - `computeRunModuleProgress(run: unknown): ModuleProgress`
  - `orderedSelectedRunModules(run: unknown): unknown[]`
  - `type EtaInput = { steps: Array<{ order: number; system_code: string; status: string }>; baselines: Record<string, number>; currentStepOrder: number | null; currentStepElapsedMs: number; suiteStatus: string }`
  - `type EtaResult = { remainingMs: number | null; partial: boolean; held: boolean }`
  - `computeSuiteEta(input: EtaInput): EtaResult`
  - Task 6 의 `steps.ts`·`render.ts` 가 소비한다

- [ ] **Step 1: `progress.ts` 를 이관한다**

`app.js:1310~1385` 의 `orderedSelectedRunModules` · `computeRunModuleProgress` 를 로직 변경 없이 옮기고 타입을 얹는다. `SUITE_ACTIVE_MODULE_STATUSES` · `ACTIVE_RUN_STATUSES` · `isModuleIssueStatus` · `normalizeOutcomeStatus` 상수/헬퍼가 필요하면 함께 옮긴다(`app.js:3~14`).

`moduleProgressClassName`(`:1386`)은 **옮기지 않는다.** 하드코딩 Tailwind 색을 반환하는 함수이고 Task 6 이 `data-tone` 속성으로 대체한다(설계 §3.5).

- [ ] **Step 2: `progress.test.ts` 를 쓴다**

```typescript
import { describe, expect, it } from "vitest";
import { computeRunModuleProgress } from "./progress";

const mods = (...specs: Array<[string, string]>) =>
  specs.map(([module_id, status], order) => ({ module_id, name: module_id, order, status }));

describe("computeRunModuleProgress", () => {
  it("진행 중 모듈을 현재 위치로 잡는다", () => {
    const p = computeRunModuleProgress({
      status: "RUNNING",
      modules: mods(["a", "passed"], ["b", "running"], ["c", "pending"]),
    });
    expect(p.current).toBe(2);
    expect(p.total).toBe(3);
    expect(p.tone).toBe("active");
  });

  it("입력 대기 모듈은 waiting 톤이다", () => {
    const p = computeRunModuleProgress({
      status: "WAITING_INPUT",
      modules: mods(["a", "passed"], ["b", "waiting_input"]),
    });
    expect(p.tone).toBe("waiting");
  });

  it("완료되면 total/total", () => {
    const p = computeRunModuleProgress({
      status: "PASSED",
      modules: mods(["a", "passed"], ["b", "passed"]),
    });
    expect(p.label).toBe("2/2");
    expect(p.tone).toBe("passed");
  });

  it("모듈이 없으면 빈 결과를 돌려주고 던지지 않는다", () => {
    expect(computeRunModuleProgress({ status: "PENDING", modules: [] }).total).toBe(0);
    expect(computeRunModuleProgress(null).total).toBe(0);
  });

  it("skipped 모듈은 분모에서 빠진다", () => {
    const p = computeRunModuleProgress({
      status: "RUNNING",
      modules: mods(["a", "passed"], ["b", "skipped"], ["c", "running"]),
    });
    expect(p.total).toBe(2);
  });
});
```

기대값이 원본과 어긋나면 **테스트가 아니라 기대값을 고친다** — 이 태스크는 동작을 바꾸지 않는 이관이다.

- [ ] **Step 3: `eta.ts` 를 쓴다(신규 로직)**

```typescript
// 수트 남은 시간 — baseline(과거 PASSED 평균) + 라이브 상태로 계산한다(설계 §3.3).
// 서버는 baseline 만 주고 산술은 여기서 한다. 소켓 이벤트마다 다시 부른다.

const WAITING = "waiting_input";
const DONE = new Set(["passed", "anomaly", "error", "failed", "cancelled", "skipped"]);

export type EtaInput = {
  steps: Array<{ order: number; system_code: string; status: string }>;
  baselines: Record<string, number>;
  currentStepOrder: number | null;
  currentStepElapsedMs: number;
  suiteStatus: string;
};

export type EtaResult = {
  /** 남은 밀리초. 계산 불가면 null. */
  remainingMs: number | null;
  /** baseline 이 없는 스텝을 제외하고 계산했다. */
  partial: boolean;
  /** 입력 대기 중이라 계산을 보류했다. */
  held: boolean;
};

export function computeSuiteEta(input: EtaInput): EtaResult {
  if (input.suiteStatus.toLowerCase() === WAITING) {
    return { remainingMs: null, partial: false, held: true };
  }

  let total = 0;
  let known = 0;
  let missing = 0;

  for (const step of input.steps) {
    if (DONE.has(step.status.toLowerCase())) continue;
    const base = input.baselines[step.system_code];
    if (base === undefined) {
      missing += 1;
      continue;
    }
    known += 1;
    if (step.order === input.currentStepOrder) {
      total += Math.max(0, base - input.currentStepElapsedMs);
    } else {
      total += base;
    }
  }

  if (known === 0) return { remainingMs: null, partial: missing > 0, held: false };
  return { remainingMs: total, partial: missing > 0, held: false };
}
```

- [ ] **Step 4: `eta.test.ts` 를 쓴다**

```typescript
import { describe, expect, it } from "vitest";
import { computeSuiteEta } from "./eta";

const MIN = 60_000;
const step = (order: number, code: string, status: string) => ({ order, system_code: code, status });

const base: Parameters<typeof computeSuiteEta>[0] = {
  steps: [step(0, "hom", "passed"), step(1, "fp", "running"), step(2, "hrp", "pending")],
  baselines: { hom: 3 * MIN, fp: 2 * MIN, hrp: 4 * MIN },
  currentStepOrder: 1,
  currentStepElapsedMs: 30_000,
  suiteStatus: "running",
};

describe("computeSuiteEta", () => {
  it("끝난 스텝은 빼고, 현재 스텝은 경과를 뺀다", () => {
    // fp 남은 90초 + hrp 4분 = 5분 30초
    expect(computeSuiteEta(base).remainingMs).toBe(90_000 + 4 * MIN);
  });

  it("현재 스텝이 baseline 을 넘겨도 음수로 가지 않는다", () => {
    const r = computeSuiteEta({ ...base, currentStepElapsedMs: 10 * MIN });
    expect(r.remainingMs).toBe(4 * MIN);
  });

  it("입력 대기 중에는 계산을 보류한다", () => {
    const r = computeSuiteEta({ ...base, suiteStatus: "waiting_input" });
    expect(r.held).toBe(true);
    expect(r.remainingMs).toBeNull();
  });

  it("baseline 이 없는 스텝은 제외하고 partial 을 세운다", () => {
    const r = computeSuiteEta({ ...base, baselines: { hom: 3 * MIN, fp: 2 * MIN } });
    expect(r.remainingMs).toBe(90_000);
    expect(r.partial).toBe(true);
  });

  it("남은 스텝의 baseline 이 전부 없으면 계산하지 않는다", () => {
    const r = computeSuiteEta({ ...base, baselines: {} });
    expect(r.remainingMs).toBeNull();
    expect(r.partial).toBe(true);
  });

  it("남은 스텝이 없으면 0 이다", () => {
    const r = computeSuiteEta({
      ...base,
      steps: [step(0, "hom", "passed"), step(1, "fp", "passed")],
      currentStepOrder: null,
    });
    expect(r.remainingMs).toBe(0);
  });
});
```

- [ ] **Step 5: 확인한다**

Run: `npm run test -- suite && npm run typecheck && npm run lint`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/web/frontend/suite
git commit -m "feat(suite): 진행률·ETA 순수 로직과 테스트"
```

---

### Task 6: 수트 DOM 모듈

Task 5 위에 DOM 계층을 얹는다. **아직 배선하지 않는다** — Task 7 이 원자적으로 전환한다.

**Files:**
- Create: `app/web/frontend/suite/steps.ts`
- Create: `app/web/frontend/suite/render.ts`
- Create: `app/web/frontend/suite/socket.ts`
- Create: `app/web/frontend/suite/actions.ts`

**Interfaces:**
- Consumes: Task 5 의 `computeRunModuleProgress` · `computeSuiteEta`, Task 4 의 `startOtpCountdown` · `stopOtpCountdown` · `moduleStartedAtFromRun`, 기존 `components/status-badge`
- Produces:
  - `renderSuiteSnapshot(suite: unknown): void` (`render.ts`)
  - `bindSuiteSocket(): void` · `closeSuiteRunProgressSocket(): void` (`socket.ts`)
  - `bindSuiteActions(): void` · `bindSuiteOtpForm(): void` (`actions.ts`)
  - Task 7 의 `entries/suite.ts` 가 이 넷을 부른다

- [ ] **Step 1: 원본을 덩어리별로 옮긴다**

`app.js:1405~1812` 를 네 파일로 나눈다. **로직은 바꾸지 않는다.**

| 파일 | 옮길 함수 (`app.js` 줄) |
| --- | --- |
| `steps.ts` | `formatStepModuleProgressText`(1405) · `findSuiteStepCardByRunId`(1428) · `updateSuiteStepModuleProgress`(1435) · `updateSuiteStepCard`(1628) · `refreshFinishedSuiteStepProgress`(1561) |
| `render.ts` | `currentSuiteId`(1573) · `updateSuiteActions`(1577) · `updateSuiteProgress`(1590) · `updateSuiteProgressDetailWithModule`(1456) · `renderSuiteSnapshot`(1682) |
| `socket.ts` | `refreshSuiteRunProgress`(1474) · `closeSuiteRunProgressSocket`(1490) · `resolveActiveSuiteRunId`(1498) · `syncSuiteRunProgressSocket`(1524) · `bindSuiteSocket`(1779) |
| `actions.ts` | `updateSuiteOtpPanel`(1667) · `cancelSuite`(1701) · `bindSuiteActions`(1720) · `submitSuiteOtp`(1728) · `bindSuiteOtpForm`(1760) |

`app.js` 의 공용 함수(`readErrorMessage` · `setInlineFeedback` · `showToast`)를 쓰는 자리는 `window.__executeLegacy` 를 통해 부르지 말고, **필요한 최소한을 `suite/` 안에 지역 함수로 둔다.** 수트는 `app.js` 와 아무것도 주고받지 않아야 한다(설계 §3.4 "신규 다리 0개"). 세 함수 모두 10~20줄짜리라 복제 비용이 다리 비용보다 싸고, Cycle 4 가 `app.js` 를 지울 때 원본만 사라진다.

- [ ] **Step 2: 세 가지를 새로 넣는다**

**(가) 진도 블록과 ETA.** `render.ts` 의 `updateSuiteProgress` 가 스텝 진행 바에 더해 경과·ETA 를 갱신한다. baseline 은 `#suite-root` 의 `data-step-baselines` 속성(Task 7 이 서버에서 주입)을 JSON 으로 한 번 읽어 모듈 지역 변수에 담는다.

**(나) 자동 펼침.** `renderSuiteSnapshot` 이 `suite.expanded_step_order` 를 읽어 해당 행에만 `data-expanded="true"` 를 세우고 나머지는 지운다. **클라이언트가 규칙을 재구현하지 않는다** — 서버 값을 그대로 반영만 한다(설계 D8).

**(다) 수트 OTP 카운트다운.** `actions.ts` 의 `updateSuiteOtpPanel` 이 대기 상태로 진입하면 `startOtpCountdown(startedAt, document.getElementById("suite-otp-countdown"))` 을 부르고, 벗어나면 `stopOtpCountdown()` 을 부른다. `startedAt` 은 `moduleStartedAtFromRun(runPayload, moduleId)` 로 얻는다 — 진행 소켓이 이미 그 Run 페이로드를 받고 있다.

- [ ] **Step 3: 톤 클래스를 CSS 로 넘긴다**

`moduleProgressClassName` 을 되살리지 않는다. 진행 텍스트 노드에 `dataset.tone = progress.tone` 만 세우고 색은 Task 7 의 `suite/styles.css` 가 `[data-tone="error"]` 등으로 준다(설계 §3.5).

- [ ] **Step 4: 확인한다**

Run: `npm run typecheck && npm run lint && npm run test`
Expected: PASS. 아직 어떤 화면도 이 모듈을 부르지 않으므로 동작 변화는 없다.

FG-004 로 400줄을 넘는 파일이 나오면 책임 단위로 더 쪼갠다.

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/suite
git commit -m "feat(suite): 스텝·렌더·소켓·액션 DOM 모듈"
```

---

### Task 7: 전환 — 템플릿·스타일·배선·`app.js` 절단

한 커밋에 묶는다. 마크업만 바꾸면 옛 JS 가 못 찾고, JS 만 바꾸면 옛 마크업이 안 맞는다.

**Files:**
- Create: `app/web/frontend/suite/styles.css`
- Create: `app/web/frontend/entries/suite.ts`
- Modify: `app/web/templates/suite.html` (전면 재작성)
- Modify: `app/api/routes_dashboard.py:152-173`
- Modify: `vite.config.ts`
- Modify: `app/web/frontend/styles/base.css`
- Modify: `app/web/static/app.js` (삭제)
- Test: `tests/test_suite_layout.py`

**Interfaces:**
- Consumes: Task 1 의 `avg_duration_ms_by_system`, Task 2 의 `expanded_step_order`, Task 3 의 `.suite` 셸, Task 6 의 네 bind/render 함수
- Produces: 완성된 화면

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_suite_layout.py`. 픽스처는 `tests/test_execute_layout.py`(Cycle 1a) 방식을 따른다.

```python
"""수트 상세 레이아웃 계약.

JS 는 data-* 로 노드를 찾는다. 마크업을 바꾸면서 훅을 잃으면 화면은 멀쩡해
보이는데 소켓이 아무것도 갱신하지 못한다.
"""


def test_root_carries_the_suite_shell_class(client) -> None:
    assert 'class="suite' in _html(client)


def test_step_rows_are_a_vertical_list(client) -> None:
    """2열 그리드가 남아 있으면 파이프라인이 아니다."""
    html = _html(client)
    assert "md:grid-cols-2" not in html
    assert 'data-step-order="0"' in html


def test_expanded_step_comes_from_the_server(client) -> None:
    """클라이언트가 규칙을 재구현하지 않는다 — 서버 값이 마크업에 찍혀 있어야 한다."""
    assert 'data-expanded="true"' in _html(client)


def test_baselines_are_injected_once(client) -> None:
    html = _html(client)
    assert "data-step-baselines=" in html


def test_js_hooks_survive(client) -> None:
    html = _html(client)
    for hook in (
        'id="suite-cancel"',
        'id="suite-status"',
        'id="suite-otp-panel"',
        'id="suite-otp-form"',
        'id="suite-otp-countdown"',
        'id="suite-step-list"',
        'data-role="step-run-link"',
        'data-role="step-module-progress"',
    ):
        assert hook in html, hook


def test_no_tailwind_color_utilities(client) -> None:
    """외형은 컴포넌트 CSS 가 갖는다(설계 §1.3)."""
    import re

    html = _html(client)
    assert not re.findall(r'class="[^"]*\b(?:bg|text|border)-(?:gray|amber|red|emerald|indigo)-\d{2,3}', html)


def test_dead_hook_classes_are_gone(client) -> None:
    """정의가 없는 채로 붙어 있던 클래스들(설계 §3.5). 컴포넌트 CSS 가 자리를 대신한다."""
    html = _html(client)
    assert "suite-step-card" not in html
    assert "otp-panel" not in html
```

`client` 픽스처와 `_html` 헬퍼는 `tests/test_execute_layout.py` 의 것을 읽고 suite 라우트(`GET /suites/{id}`)에 맞춰 옮긴다. `SuiteService` 는 가짜로 주입한다 — `tests/test_suite_browser_mode.py` 나 `tests/test_wall_http.py` 의 서비스 오버라이드 방식을 참고한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_suite_layout.py -v`
Expected: FAIL — `.suite` 클래스 · `data-step-order` · `data-expanded` · `data-step-baselines` 없음

- [ ] **Step 3: 라우트에 baseline 을 주입한다**

`app/api/routes_dashboard.py:152` 의 `suite_dashboard` 에 쿼리 의존성을 추가하고 컨텍스트에 넣는다.

```python
    baselines = await run_summary_query.avg_duration_ms_by_system()
    return templates.TemplateResponse(
        request,
        "suite.html",
        {
            "suite": suite,
            "current_user": current_user,
            "step_baselines": baselines,
        },
    )
```

`run_summary_query` 는 같은 파일이 이미 쓰는 의존성 주입 방식(`Depends(...)`)을 따른다 — `app/api/dependencies.py` 에서 `RunSummaryQueryPort` 를 내주는 provider 를 찾아 쓰고, 없으면 기존 provider 들과 같은 모양으로 추가한다.

**실패 처리:** baseline 조회가 실패해도 화면은 떠야 한다. 예외를 삼키고 `{}` 를 넘긴다 — ETA 만 사라지고 실행 관찰은 살아 있다.

- [ ] **Step 4: 템플릿을 재작성한다**

`app/web/templates/suite.html` 을 설계 §3.1 구조로 다시 쓴다. 뼈대:

```jinja
{% extends "base.html" %}
{% block title %}전체 점검{% endblock %}

{% block content %}
{% import "components/status-badge/macro.jinja" as sb %}
<div class="suite" id="suite-root"
     data-suite-id="{{ suite.suite_id }}"
     data-step-baselines='{{ step_baselines | tojson }}'>

  <header class="suite-head"> … 빵부스러기 · 제목 · 상태 배지 · #suite-cancel … </header>

  <section class="suite-otp" id="suite-otp-panel"
           data-run-id="{{ suite.awaiting_input_run_id or '' }}"
           {% if not suite.awaiting_input_run_id %}hidden{% endif %}>
    … #suite-otp-prompt · #suite-otp-countdown · #suite-otp-form …
  </section>

  <section class="suite-sum"> … 진행 바 · 경과 · ETA … </section>

  <ol class="suite-steps" id="suite-step-list">
    {% for step in suite.steps|sort(attribute='order') %}
    <li class="suite-step" data-step-order="{{ step.order }}"
        data-system-code="{{ step.system_code }}"
        {% if suite.expanded_step_order == step.order %}data-expanded="true"{% endif %}>
      … 인덱스 · 이름 · 소요시간/평균 · 배지 · (전개 시) 모듈 칩 · Run 상세 링크 …
    </li>
    {% endfor %}
  </ol>
</div>
{% endblock %}

{% block scripts %}
{% import "_assets.html" as suite_assets %}
{{ suite_assets.asset_script("entries/suite.ts") }}
{% endblock %}
```

`is-hidden` 클래스 대신 네이티브 `hidden` 속성을 쓴다 — `base.css` 가 이미 `[x-cloak]` 를 다루듯 브라우저 기본 동작으로 충분하다. 상태 배지는 `sb.status_badge(...)` 매크로를 그대로 쓴다(FG-003·FG-006).

대기 스텝의 「평균 N분」은 서버가 `step_baselines` 를 갖고 있으므로 **템플릿에서 바로 렌더한다** — 초기 화면에 이미 값이 있어야 깜빡임이 없다.

- [ ] **Step 5: `suite/styles.css` 를 만든다**

설계 §3.1 의 세로 구성을 CSS 로 옮긴다. 색은 전부 토큰(FG-002). 톤 규칙을 포함한다.

```css
/* 수트 상세 — 진행 관찰용 수직 파이프라인(설계 §3.1).
   넌스크롤 셸은 shell.css 가 담당한다. */

.suite {
  display: flex;
  flex-direction: column;
  gap: 0.6875rem;
  height: 100%;
  padding: 1rem;
  overflow: hidden;
}

.suite-head, .suite-otp, .suite-sum { flex-shrink: 0; }

.suite-steps {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;      /* 넌스크롤 예산: 내부 스크롤은 여기 하나뿐 */
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.suite-step[data-expanded="true"] {
  border-color: var(--st-running-border);
  box-shadow: 0 0 0 3px var(--st-running-surface), var(--pl-shadow-sm);
}

[data-role="step-module-progress"][data-tone="active"] { color: var(--st-running-text); }
[data-role="step-module-progress"][data-tone="waiting"] { color: var(--st-waiting_input-text); }
[data-role="step-module-progress"][data-tone="anomaly"] { color: var(--st-anomaly-text); }
[data-role="step-module-progress"][data-tone="error"]   { color: var(--st-error-text); }
[data-role="step-module-progress"][data-tone="passed"]  { color: var(--st-passed-text); }
[data-role="step-module-progress"][data-tone="muted"]   { color: var(--pl-text-subtle); }
```

나머지(헤더·OTP·진도 블록·스텝 행·모듈 칩)도 같은 방식으로 채운다. 400줄을 넘으면 쪼갠다.

- [ ] **Step 6: 엔트리를 만들고 등록한다**

`app/web/frontend/entries/suite.ts`:

```typescript
// 수트 상세 화면 엔트리. 배선만 한다 — 로직은 suite/ 아래 모듈에 있다.
import "../suite/styles.css";
import { bindSuiteActions, bindSuiteOtpForm } from "../suite/actions";
import { renderSuiteSnapshot } from "../suite/render";
import { bindSuiteSocket } from "../suite/socket";

document.addEventListener("DOMContentLoaded", () => {
  bindSuiteActions();
  bindSuiteOtpForm();
  bindSuiteSocket();
});
```

`renderSuiteSnapshot` 을 import 만 하고 안 쓰면 lint 가 잡는다 — 최초 렌더가 서버 마크업으로 끝나면 import 를 지우고, 초기 1회 렌더가 필요하면 여기서 부른다. Task 6 Step 2 에서 정한 구조에 맞춘다.

`vite.config.ts` 의 `rollupOptions.input` 에 추가한다.

```typescript
        suite: resolve(__dirname, "app/web/frontend/entries/suite.ts"),
```

- [ ] **Step 7: `app.js` 에서 수트 몫을 지운다**

- 수트 함수 20개(`:1405~1812`)
- `orderedSelectedRunModules` · `computeRunModuleProgress` · `moduleProgressClassName`(`:1310~1404`)
- `DOMContentLoaded` 의 `bindSuiteActions();` · `bindSuiteOtpForm();` · `bindSuiteSocket();` 세 줄

지운 뒤 남은 참조가 있는지 확인한다.

Run: `grep -n "Suite\|suite" app/web/static/app.js | grep -v "suite_id\|suiteId" | head -20`

`buildExecutionGroups`(`:188`) 등 **Run 이력**이 쓰는 suite 관련 코드는 남는다 — Cycle 4 의 몫이다.

- [ ] **Step 8: 테스트와 빌드**

Run: `python3 -m pytest tests/test_suite_layout.py -v && npm run build && npm run typecheck && npm run lint && npm run test`
Expected: 전부 PASS

Run: `wc -l app/web/static/app.js`
Expected: 약 1,381줄

- [ ] **Step 9: 실물로 확인한다**

수트를 하나 실행해 끝까지 본다.

- 진행 중 스텝만 펼쳐지고, 스텝이 넘어가면 펼침이 따라 이동한다
- 모듈 칩이 소켓 이벤트로 갱신된다
- 경과가 1초마다 오르고 ETA 가 줄어든다
- OTP 구간에서 패널이 뜨고 **카운트다운이 돈다**
- 취소 버튼이 동작한다
- 종료 후 첫 error(없으면 anomaly) 스텝이 펼쳐지고, 전부 정상이면 모두 접힌다
- 콘솔에 `ReferenceError` 가 없다

- [ ] **Step 10: 커밋**

```bash
git add app/web/templates/suite.html app/web/frontend app/web/static/app.js vite.config.ts app/api/routes_dashboard.py tests/test_suite_layout.py
git commit -m "feat(suite): 넌스크롤 수직 파이프라인으로 전환 — app.js 절단"
```

---

### Task 8: 회귀 테스트와 문서

**Files:**
- Create: `tests/test_suite_viewport.py`
- Modify: `docs/specs/dashboard/03-run-suite-views.md`
- Modify: `docs/superpowers/specs/2026-08-29-suite-promotion-design.md` (§7 실측 반영)

**Interfaces:**
- Consumes: Task 7 의 완성된 화면
- Produces: 없음

- [ ] **Step 1: Playwright 회귀를 쓴다**

`tests/test_dashboard_viewport.py` 의 서버 기동 픽스처를 복사해 쓴다(세 번째 사용처가 되면 공통으로 뽑는다 — 지금은 두 번째다).

```python
VIEWPORTS = [(1366, 768), (1920, 1080), (2560, 1440)]


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_page_scroll(page_factory, width, height):
    page = page_factory(width, height)
    page.goto(f"{BASE_URL}/suites/{SUITE_ID}")
    page.wait_for_selector(".suite")
    overflow = page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )
    assert overflow <= 1, f"{width}x{height} 에서 세로 스크롤 {overflow}px"


def test_expanded_step_is_inside_the_viewport(page_factory):
    """is_visible() 은 뷰포트 밖 요소를 통과시킨다 — 좌표로 단언한다(설계 §5)."""
    page = page_factory(1366, 768)
    page.goto(f"{BASE_URL}/suites/{SUITE_ID}")
    page.wait_for_selector('[data-expanded="true"]')
    box = page.locator('[data-expanded="true"] [data-role="step-module-progress"]').bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= 768


def test_exactly_one_internal_scroller(page_factory):
    page = page_factory(1920, 1080)
    page.goto(f"{BASE_URL}/suites/{SUITE_ID}")
    page.wait_for_selector(".suite")
    scrollers = page.evaluate(
        """() => Array.from(document.querySelectorAll('.suite *'))
              .filter((el) => {
                  const style = getComputedStyle(el);
                  return /auto|scroll/.test(style.overflowY)
                      && el.scrollHeight > el.clientHeight + 1;
              })
              .map((el) => el.className)"""
    )
    assert len(scrollers) <= 1, f"내부 스크롤러가 여럿: {scrollers}"


def test_worst_case_six_steps_with_otp_fits(page_factory):
    """설계 §3.1 예산의 최악 조건. 여유가 109px 뿐이라 이 케이스가 경계다."""
    page = page_factory(1366, 768)
    page.goto(f"{BASE_URL}/suites/{SUITE_ID_SIX_STEPS_WAITING}")
    page.wait_for_selector("#suite-otp-panel:not([hidden])")
    overflow = page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )
    assert overflow <= 1
```

`SUITE_ID` 는 3~4 스텝 진행 중 픽스처, `SUITE_ID_SIX_STEPS_WAITING` 은 **시스템 6개 + OTP 대기** 픽스처다. 후자가 예산의 경계이므로 반드시 별도로 만든다.

- [ ] **Step 2: 실행한다**

Run: `python3 -m pytest tests/test_suite_viewport.py -v`
Expected: PASS. 넘치면 어느 뷰포트에서 몇 px 인지 메시지가 알려준다 — `.suite` 의 `gap`·`padding` 을 줄인다.

Chromium 이 없으면 `python3 -m playwright install chromium` 후 재실행.

- [ ] **Step 3: AC Spec 을 갱신한다**

`docs/specs/dashboard/03-run-suite-views.md` §1 에 수트 상세의 새 구조를 적고 수용 기준을 추가한다. `AC-001`(OTP 패널)은 **기존 규칙이 유지되므로 건드리지 않는다.**

```markdown
### AC-003: 수트 상세 자동 펼침

```gherkin
Given 실행 중인 suite
When 진행 중 스텝이 바뀐다
Then 펼쳐진 스텝이 서버의 expanded_step_order 와 일치한다
And 수동 펼침 경로는 존재하지 않는다
```

### AC-004: 수트 상세 넌스크롤

```gherkin
Given 시스템 6개 suite 가 OTP 입력 대기
When 1366x768 에서 렌더한다
Then body 세로 스크롤이 0 이다
And 펼쳐진 스텝의 모듈 진행이 뷰포트 안에 있다
```
```

- [ ] **Step 4: 설계 문서 §7 에 실측을 반영한다**

`app.js` 최종 줄 수, `frontend/suite/` 각 파일 줄 수, `__executeLegacy` 잔여 키 수를 실측값으로 적는다. **추정으로 적지 않는다.**

- [ ] **Step 5: 전체 게이트**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `python3 scripts/check_docs_consistency.py`
Expected: 통과

- [ ] **Step 6: 커밋**

```bash
git add tests/test_suite_viewport.py docs/
git commit -m "test(suite): 넌스크롤 좌표 계약 회귀 + AC Spec 갱신"
```

---

## 완료 확인

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [ ] `npm run test && npm run typecheck && npm run lint && npm run build` 통과
- [ ] `app.js` 약 1,381줄, 수트 함수 0개
- [ ] `__executeLegacy` 키 5개 (`setInlineFeedback` · `readErrorMessage` · `bindScheduleBuilder` · `buildScheduleCron` · `refreshScheduleList`)
- [ ] 신규 다리 0개 — `suite/` 가 `window.__execute*` 를 참조하지 않는다
- [ ] `frontend/suite/` · `entries/suite.ts` 전 파일 400줄 미만
- [ ] 1366 · 1920 · 2560 px 넌스크롤, 최악 조건(6 스텝 + OTP) 포함
- [ ] `suite.html` 에 Tailwind 색 유틸리티 0개
- [ ] `snapshot_validate` · `projection_validate` diff 0
- [ ] 실물에서 수트 1회 완주 — 펼침 이동 · ETA 감소 · OTP 카운트다운 · 종료 후 전개

## 이 계획이 남기는 것

| 항목 | 다음 단계 |
| --- | --- |
| `app.js` 잔여 약 1,381줄 | Cycle 3(런 상세) → 4(Run 이력, 소멸) |
| `__executeOtpPanel` 다리 | Cycle 3 |
| `__executeLegacy` 잔여 5키 | Cycle 4 |
| `FG004_ALLOWLIST` 의 `app.css` | Cycle 3~6 |
| Playwright 서버 기동 픽스처 중복 2벌 | 세 번째 사용처가 생기면 공통 추출 |
| `suite/` 안의 `readErrorMessage` 등 지역 복제 | Cycle 4 가 `app.js` 원본을 지울 때 정리 판단 |
