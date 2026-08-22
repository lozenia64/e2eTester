# 프론트엔드 고도화 P3-3 (일간 리포트 메일) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 어제 점검 결과를 전사 수신자에게 하루 한 통 자동 발송하는 일간 리포트 메일을 만든다.

**Architecture:** 데이터는 P2 의 `get_daily_summary` 에 `date_label` 선택 인자를 더해 재사용하고(신규 쿼리 0건), 발송은 `RunRetentionScheduler` 의 cron 틱 패턴을, 하루 한 통 보장은 기존 범용 dedup claim 을 쓴다. 렌더는 `report_renderer.py` 의 비공개 헬퍼를 같은 모듈 안에서 재사용한다.

**Tech Stack:** Python 3.13 · pytest · smtplib(기존 `GmailEmailSender`) · tenacity(기존 재시도)

**Spec:** `docs/superpowers/specs/2026-08-21-frontend-elevation-p3-3-daily-report-design.md`

## Global Constraints

- UI·로그·README 문자열은 **한국어**. (`AGENTS.md`)
- **한국어 상태 라벨을 하드코딩하지 않는다.** `app/core/status_labels.py` 에서 가져온다 (P3-2 에서 같은 실수를 했다).
- **기능 스위치 기본 `false`.** 메일은 되돌릴 수 없는 부수효과다.
- **수신자가 비어 있으면 발송하지 않는다.**
- **하루 한 통** — 기존 `try_claim_sync("daily_report", date_label)` 로 보장한다. 신규 테이블을 만들지 않는다.
- **메일 색 값을 바꾸지 않는다.** 커버리지 누락(`PENDING`·`QUEUED`·`RUNNING`)만 메운다.
- **링크를 넣지 않는다.** 렌더 결과에 외부 URL 0건.
- **`date_label` 기본값은 현행 동작(오늘)** — 일간 현황·상황판이 영향받지 않아야 한다.
- **선행 의존: P3-2.** `summary["systems"]` 는 P3-2 가 추가한 패스스루다. P3-2 없이 병합하면 시스템별 표가 조용히 빈 채 발송된다 — 픽스처가 `systems` 를 주입하므로 테스트로는 잡히지 않는다.
- **SMTP 를 실제로 호출하는 테스트를 쓰지 않는다.** `docs/CI.md` 의 "AI/메일은 CI 밖" 방침과 일치시킨다.
- 새 CI 게이트를 등록하지 않는다.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full`.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `app/core/settings.py` (수정) | `daily_report_enabled` · `daily_report_cron` 필드 |
| `.env.example` · `docs/INSTALL.md` (수정) | env 3종 문서화 (`docs_consistency` 게이트 요구) |
| `app/contexts/scheduling/scheduler.py` (수정) | `schedule_day_start_utc(date_label)` 추가 |
| `app/orchestrator/queries/daily_queries.py` (수정) | `get_daily_dashboard(date_label=…)` |
| `app/orchestrator/queries/daily_summary_queries.py` (수정) | `get_daily_summary(date_label=…)` 전달 |
| `app/notifications/report_renderer.py` (수정) | `_STATUS_COLORS` 커버리지 + `render_daily_report_html()` + `_system_summary_table()` |
| `app/notifications/daily_report.py` (신규) | `build_daily_report()` — 순수 조립. I/O 없음 |
| `app/notifications/daily_report_email.py` (신규) | `DailyReportEmailService` — 수신자 해석·dedup·발송 |
| `app/contexts/scheduling/daily_report_scheduler.py` (신규) | cron 틱 루프. `run_retention.py` 와 동형 |
| `app/contexts/scheduling/composition.py` (수정) | 스케줄러 조립 |
| `app/composition/container.py` (수정) | 스케줄러 기동 배선 |
| `tests/test_daily_report_settings.py` (신규) | env 스위치 |
| `tests/test_daily_report_date_scope.py` (신규) | 날짜 파라미터화 |
| `tests/test_report_status_colors.py` (신규) | 색 커버리지 전수 |
| `tests/test_daily_report_build.py` (신규) | 제목 4경로 · SSOT 라벨 |
| `tests/test_daily_report_render.py` (신규) | 렌더 스모크 · 링크 없음 |
| `tests/test_daily_report_email.py` (신규) | 수신자·dedup·실패 처리 |
| `tests/test_daily_report_scheduler.py` (신규) | cron·비활성 |

---

## Task 1: 설정과 문서

**Files:**
- Modify: `app/core/settings.py`
- Modify: `.env.example`, `docs/INSTALL.md`
- Test: `tests/test_daily_report_settings.py`

**Interfaces:**
- Produces: `E2ESettings.daily_report_enabled: bool`(기본 `False`, alias `E2E_EMAIL_DAILY_REPORT_ENABLED`), `E2ESettings.daily_report_cron: str | None`(기본 `None`, alias `E2E_EMAIL_DAILY_REPORT_CRON`)

수신자(`E2E_EMAIL_DAILY_REPORT_RECIPIENTS`)는 `E2ESettings` 에 넣지 않는다 — 기존 메일 수신자들이 `dotenv_values` 로 읽히므로(`run_completion_email.py` 의 `_resolve_recipient_map`) 같은 경로를 Task 6 에서 쓴다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_daily_report_settings.py`:

```python
"""일간 리포트 발송 스위치.

메일은 사람 받은편지함으로 나가는 되돌릴 수 없는 부수효과다. 상황판(E2E_WALL_ENABLED)을
기본 true 로 둔 것과 반대로, 여기는 기본 false 다 — 안 켜면 "안 나가는" 것이고
켜면 "잘못 나가는" 것이라 실패 방향이 다르다(설계 D3).
"""

from app.core.settings import E2ESettings


def test_daily_report_is_disabled_by_default():
    assert E2ESettings().daily_report_enabled is False


def test_daily_report_can_be_enabled_by_env(monkeypatch):
    monkeypatch.setenv("E2E_EMAIL_DAILY_REPORT_ENABLED", "true")
    assert E2ESettings().daily_report_enabled is True


def test_daily_report_cron_defaults_to_none(monkeypatch):
    monkeypatch.delenv("E2E_EMAIL_DAILY_REPORT_CRON", raising=False)
    assert E2ESettings().daily_report_cron is None


def test_daily_report_cron_reads_env(monkeypatch):
    monkeypatch.setenv("E2E_EMAIL_DAILY_REPORT_CRON", "30 7 * * *")
    assert E2ESettings().daily_report_cron == "30 7 * * *"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_settings.py -q`
Expected: FAIL — `AttributeError: 'E2ESettings' object has no attribute 'daily_report_enabled'`

- [ ] **Step 3: 설정 필드를 추가한다**

`app/core/settings.py` 의 `run_retention_cron` 선언 근처에 추가한다:

```text
    # 일간 리포트 메일(P3-3). 메일은 되돌릴 수 없는 부수효과라 기본은 꺼 둔다 —
    # 상황판(E2E_WALL_ENABLED, 기본 true)과 반대 판단이다.
    daily_report_enabled: bool = Field(
        default=False, validation_alias="E2E_EMAIL_DAILY_REPORT_ENABLED"
    )
    # 발송 시각(스케줄 타임존 기준 5필드 cron). None 이면 기본값 08:00.
    daily_report_cron: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_DAILY_REPORT_CRON"
    )
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_settings.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: `.env.example` 에 문서화한다**

메일 설정 블록(`E2E_EMAIL_OPERATOR_RECIPIENTS` 근처) 아래에 추가한다:

```dotenv
# 일간 리포트 메일 — 어제 점검 결과를 전사 수신자에게 하루 한 통 보낸다.
# 메일은 되돌릴 수 없으므로 기본은 꺼져 있다. 운영 투입 전에는 RECIPIENTS 를
# 본인 주소로만 두고 하루 관찰할 것.
E2E_EMAIL_DAILY_REPORT_ENABLED=false
# 발송 시각(스케줄 타임존 기준 5필드 cron). 비우면 08:00.
E2E_EMAIL_DAILY_REPORT_CRON=0 8 * * *
# 파이프(|) 구분. 비어 있으면 발송하지 않는다.
E2E_EMAIL_DAILY_REPORT_RECIPIENTS=exec1@company.com|exec2@company.com
```

- [ ] **Step 6: `docs/INSTALL.md` env 표에 추가한다**

`| E2E_RUN_RETENTION_ENABLED / ... |` 행 근처에 추가:

```markdown
| `E2E_EMAIL_DAILY_REPORT_ENABLED` / `E2E_EMAIL_DAILY_REPORT_CRON` / `E2E_EMAIL_DAILY_REPORT_RECIPIENTS` | 일간 리포트 메일(어제 결과, 전사 단일). 기본 꺼짐 — 켜기 전 수신자를 본인 주소로 두고 하루 관찰 |
```

- [ ] **Step 7: 문서 정합성 게이트를 확인한다**

Run: `python3 scripts/ci/run_all_gates.py --gate docs_consistency`
Expected: `{"passed": true, ...}`

이 게이트는 코드가 읽는 환경변수가 `docs/INSTALL.md` 또는 `.env.example` 에 문서화되어 있는지 검사한다. `E2E_EMAIL_DAILY_REPORT_RECIPIENTS` 는 Task 6 에서 코드가 읽기 시작하므로, 지금 문서에 먼저 넣어 두면 그때 게이트가 바로 통과한다.

- [ ] **Step 8: 커밋**

```bash
git add app/core/settings.py .env.example docs/INSTALL.md tests/test_daily_report_settings.py
git commit -m "feat(config): 일간 리포트 메일 설정 3종 추가"
```

---

## Task 2: 날짜 파라미터화

**Files:**
- Modify: `app/contexts/scheduling/scheduler.py:63-77`
- Modify: `app/orchestrator/queries/daily_queries.py`
- Modify: `app/orchestrator/queries/daily_summary_queries.py`
- Test: `tests/test_daily_report_date_scope.py`

**Interfaces:**
- Produces:
  - `app.contexts.scheduling.scheduler.schedule_day_start_utc(date_label: str) -> datetime`
  - `DailyDashboardQueries.get_daily_dashboard(*, allowed_system_codes=None, date_label: str | None = None) -> dict`
  - `DailySummaryQueries.get_daily_summary(*, user_id, allowed_system_codes, is_admin=False, date_label: str | None = None) -> dict`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_daily_report_date_scope.py`:

```python
"""일간 집계의 날짜 파라미터화.

리포트는 어제를 보고해야 하는데(설계 D1) DailyDashboardQueries 가 오늘로
고정돼 있었다. 포트(list_for_date)는 이미 임의 날짜를 받으므로 이 한 곳만 연다.
기본값은 현행 동작이라 일간 현황·상황판은 영향받지 않아야 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.scheduling.scheduler import (
    schedule_day_start_utc,
    schedule_today_label,
    schedule_today_start_utc,
)


def test_day_start_matches_today_helper():
    """schedule_today_start_utc 는 오늘 라벨을 넣은 schedule_day_start_utc 와 같다."""
    assert schedule_day_start_utc(schedule_today_label()) == schedule_today_start_utc()


def test_day_start_is_utc_aware():
    result = schedule_day_start_utc("2026-08-20")
    assert result.tzinfo is not None
    assert result.utcoffset() == UTC.utcoffset(None)


def test_day_start_of_kst_date_is_previous_day_in_utc():
    """KST 2026-08-20 00:00 == UTC 2026-08-19 15:00 (E2E_SCHEDULE_TZ 기본 Asia/Seoul)."""
    result = schedule_day_start_utc("2026-08-20")
    assert result == datetime(2026, 8, 19, 15, 0, tzinfo=UTC)


def test_invalid_label_raises():
    with pytest.raises(ValueError):
        schedule_day_start_utc("2026/08/20")


class _RecordingStatusQuery:
    def __init__(self) -> None:
        self.dates: list[str] = []

    async def list_for_date(self, date_label, allowed_system_codes):
        self.dates.append(date_label)
        return []

    async def list_run_summaries_for_date(self, date_label, since_utc, allowed_system_codes):
        return []


class _EmptyRegistry:
    def list_systems(self):
        return []


@pytest.mark.asyncio
async def test_default_queries_today():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    query = _RecordingStatusQuery()
    await DailyDashboardQueries(_EmptyRegistry(), query).get_daily_dashboard()
    assert query.dates == [schedule_today_label()]


@pytest.mark.asyncio
async def test_explicit_date_label_is_used():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    query = _RecordingStatusQuery()
    await DailyDashboardQueries(_EmptyRegistry(), query).get_daily_dashboard(
        date_label="2026-08-20"
    )
    assert query.dates == ["2026-08-20"]


@pytest.mark.asyncio
async def test_dashboard_echoes_the_requested_date():
    from app.orchestrator.queries.daily_queries import DailyDashboardQueries

    data = await DailyDashboardQueries(
        _EmptyRegistry(), _RecordingStatusQuery()
    ).get_daily_dashboard(date_label="2026-08-20")
    assert data["date_label"] == "2026-08-20"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_date_scope.py -q`
Expected: FAIL — `ImportError: cannot import name 'schedule_day_start_utc'`

- [ ] **Step 3: `schedule_day_start_utc` 를 추가한다**

`app/contexts/scheduling/scheduler.py` 의 `schedule_today_start_utc` 아래에 추가한다:

```python
def schedule_day_start_utc(date_label: str) -> datetime:
    """스케줄 타임존 기준 ``date_label``(YYYY-MM-DD) 00:00:00 을 UTC 로 반환한다.

    일간 집계가 임의 날짜를 조회할 때 쓴다(P3-3 일간 리포트는 어제를 본다).
    """
    tz, _ = _resolve_timezone()
    day = datetime.strptime(date_label, "%Y-%m-%d")
    return day.replace(tzinfo=tz).astimezone(UTC)
```

그리고 기존 `schedule_today_start_utc` 를 새 함수로 표현해 중복을 없앤다:

```python
def schedule_today_start_utc() -> datetime:
    """스케줄 타임존 기준 '오늘' 00:00:00 을 UTC 로 반환한다."""
    return schedule_day_start_utc(schedule_today_label())
```

**정의 순서 주의:** `schedule_today_start_utc` 가 `schedule_day_start_utc` 와 `schedule_today_label` 을 호출하므로, 두 함수를 그 위에 두거나 모듈 로드 시점이 아닌 호출 시점에 해석되도록 그대로 둔다(파이썬 함수 본문은 호출 시 해석되므로 순서는 무관하지만, 읽는 순서를 위해 `schedule_day_start_utc` → `schedule_today_label` → `schedule_today_start_utc` 로 배치한다).

- [ ] **Step 4: `get_daily_dashboard` 를 파라미터화한다**

`app/orchestrator/queries/daily_queries.py`:

```text
    async def get_daily_dashboard(
        self,
        *,
        allowed_system_codes: list[str] | None = None,
        date_label: str | None = None,
    ) -> dict:
        """접근 가능한 시스템의 지정일(기본 오늘) 시스템·모듈별 점검 상태 집계(PII 없음)."""
        systems = self._registry.list_systems()
        if allowed_system_codes is not None:
            allowed = set(allowed_system_codes)
            systems = [s for s in systems if s.system_code in allowed]

        target_label = date_label or schedule_today_label()
        today_start_utc = schedule_day_start_utc(target_label)
        status_rows = await self._daily_status_query.list_for_date(
            target_label, allowed_system_codes
        )
        run_summaries = await self._daily_status_query.list_run_summaries_for_date(
            target_label, today_start_utc, allowed_system_codes
        )
```

이후 본문(`duration_by_module_run` 계산과 `build_daily_dashboard_from_projection` 호출)에서 `date_label=date_label` 을 `date_label=target_label` 로 바꾼다.

import 를 `schedule_day_start_utc` 로 교체한다 — `schedule_today_start_utc` 는 더 이상 이 파일에서 쓰지 않는다.

- [ ] **Step 5: `get_daily_summary` 가 그대로 전달하게 한다**

`app/orchestrator/queries/daily_summary_queries.py`:

```python
    async def get_daily_summary(
        self,
        *,
        user_id: str | None,
        allowed_system_codes: list[str] | None,
        is_admin: bool = False,
        date_label: str | None = None,
    ) -> dict[str, Any]:
        dashboard = await self._daily_queries.get_daily_dashboard(
            allowed_system_codes=allowed_system_codes,
            date_label=date_label,
        )
```

그리고 `build_daily_summary(...)` 호출의 `today_label=schedule_today_label()` 을 `today_label=dashboard["date_label"]` 로 바꾼다 — **지정일 리포트에서 "오늘 자동 복구"가 엉뚱한 날을 가리키지 않게 하기 위해서다.**

- [ ] **Step 6: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_date_scope.py -q`
Expected: PASS (7 passed)

- [ ] **Step 7: 기존 경로가 안 깨졌는지 확인한다**

Run: `python3 -m pytest tests/test_daily_dashboard.py tests/test_daily_summary.py tests/test_daily_summary_http.py tests/test_dashboard_fragments_http.py -q`
Expected: PASS — 기본값이 현행 동작이므로 전부 통과해야 한다

- [ ] **Step 8: 커밋**

```bash
git add app/contexts/scheduling/scheduler.py app/orchestrator/queries/ \
        tests/test_daily_report_date_scope.py
git commit -m "feat(insights): 일간 집계에 date_label 선택 인자 추가 — 임의 날짜 조회"
```

---

## Task 3: 메일 상태 색 커버리지

**Files:**
- Modify: `app/notifications/report_renderer.py:68-88`
- Test: `tests/test_report_status_colors.py`

**Interfaces:**
- Produces: `_STATUS_COLORS` 가 `ModuleStatus`·`RunStatus`·`SuiteStatus` 의 모든 값을 명시적으로 담는다

- [ ] **Step 1: 전수 검사 테스트를 작성한다**

`tests/test_report_status_colors.py`:

```python
"""메일 상태 색의 전수 커버리지.

_STATUS_COLORS 는 손으로 유지하는 매핑인데 전수 검사가 없어 RUNNING·PENDING·QUEUED 가
빠져 중립 회색으로 떨어지고 있었다. run.html:6 의 status_pill 이 anomaly·error 키를
빠뜨렸던 것과 같은 병이다.

맵은 enum 이 아니라 **문자열 값**으로 키가 잡히므로 값 하나가 세 enum 을 모두 덮는다.
"""

import pytest

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.notifications.report_renderer import (
    INFO_COLOR,
    NEUTRAL_COLOR,
    _STATUS_COLORS,
    _status_color,
)

ALL_STATUS_VALUES = sorted(
    {s.value for s in ModuleStatus} | {s.value for s in RunStatus} | {s.value for s in SuiteStatus}
)


@pytest.mark.parametrize("value", ALL_STATUS_VALUES)
def test_every_status_value_is_explicitly_mapped(value: str) -> None:
    """기본값으로 흘러내리는 상태가 없어야 한다.

    PENDING 처럼 중립색이 맞는 상태도 '명시'를 요구한다 — 기본값으로 우연히 맞는 것과
    의도적으로 중립인 것을 구분하기 위해서다.
    """
    assert value in _STATUS_COLORS, f"{value} 가 _STATUS_COLORS 에 없습니다."


def test_running_is_not_neutral() -> None:
    """진행 중은 중립이 아니다 — 웹 토큰도 파랑(--st-running-text)이다."""
    assert _status_color(ModuleStatus.RUNNING.value) == INFO_COLOR
    assert _status_color(RunStatus.RUNNING.value) == INFO_COLOR
    assert _status_color(SuiteStatus.RUNNING.value) == INFO_COLOR


def test_pending_and_queued_are_deliberately_neutral() -> None:
    assert _status_color(ModuleStatus.PENDING.value) == NEUTRAL_COLOR
    assert _status_color(ModuleStatus.QUEUED.value) == NEUTRAL_COLOR


def test_existing_values_are_unchanged() -> None:
    """설계 D5 — 커버리지만 메우고 값은 바꾸지 않는다."""
    assert _status_color(ModuleStatus.PASSED.value) == "#2f8f4e"
    assert _status_color(ModuleStatus.ERROR.value) == "#c0392b"
    assert _status_color(ModuleStatus.ANOMALY.value) == "#b7791f"
    assert _status_color(ModuleStatus.WAITING_INPUT.value) == "#b7791f"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_report_status_colors.py -q`
Expected: FAIL — `PENDING`·`QUEUED`·`RUNNING` 3건이 `_STATUS_COLORS` 에 없음

- [ ] **Step 3: 누락 3개를 추가한다**

`app/notifications/report_renderer.py` 의 `_STATUS_COLORS` 딕셔너리 끝(닫는 `}` 직전)에 추가한다. **기존 항목은 건드리지 않는다.**

```python
    # 아래 3개는 이전까지 맵에 없어 기본값(NEUTRAL_COLOR)으로 흘러내렸다.
    # RUNNING 은 진행 중이므로 중립이 아니어야 한다 — 웹 토큰도 파랑이다.
    # PENDING/QUEUED 는 중립이 맞지만, 우연이 아니라 의도임을 명시한다.
    ModuleStatus.RUNNING.value: INFO_COLOR,
    ModuleStatus.PENDING.value: NEUTRAL_COLOR,
    ModuleStatus.QUEUED.value: NEUTRAL_COLOR,
```

`RunStatus.RUNNING.value` 와 `SuiteStatus.RUNNING.value` 는 문자열이 같으므로 따로 넣지 않는다(넣으면 중복 키가 되어 ruff `F601` 계열은 아니지만 무의미하다).

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_report_status_colors.py -q`
Expected: PASS

- [ ] **Step 5: 기존 메일 테스트가 안 깨졌는지 확인한다**

Run: `python3 -m pytest tests/test_email_inline_images.py tests/test_email_attachment_selection.py tests/test_email_retry.py -q`
Expected: PASS — 기존 색 값을 바꾸지 않았으므로 영향이 없어야 한다

- [ ] **Step 6: 커밋**

```bash
git add app/notifications/report_renderer.py tests/test_report_status_colors.py
git commit -m "fix(notifications): 메일 상태 색 커버리지 누락 3건 수정 + 전수 가드"
```

---

## Task 4: `build_daily_report` 순수 조립

**Files:**
- Create: `app/notifications/daily_report.py`
- Test: `tests/test_daily_report_build.py`

**Interfaces:**
- Consumes: Task 2 의 `get_daily_summary(date_label=…)` 반환 dict — `cards` · `totals` · `attention` · `date_label`, 그리고 **P3-2 가 넣는** `systems`
- Produces:
  ```python
  def build_daily_report(summary: dict[str, Any], *, date_label: str) -> dict[str, Any]
  # → {
  #     "date_label": str,
  #     "headline": str,          # 예 "점검실패 2건"
  #     "status_value": str,      # ModuleStatus 값 — 메일 배지·강조색에 쓴다
  #     "kpis": [(label, value, unit), ...],
  #     "systems": [{"code","name","passed","total","status_value","status_label"}, ...],
  #     "issues": [{"system","module","status_label"}, ...],
  #   }
  ```

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_daily_report_build.py`:

```python
"""일간 리포트 내용 조립.

제목 규칙은 상황판과 다르다 — 발송 시각(다음 날 아침)에는 어제의 OTP 대기가 이미
끝났거나 무의미하므로 하루가 닫힌 뒤의 결론만 담는다(설계 §3.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.enums import ModuleStatus
from app.core.status_labels import module_status_label
from app.notifications.daily_report import build_daily_report

CARDS = [
    {
        "key": "pass_rate",
        "label": "통과율",
        "value": 94,
        "unit": "%",
        "period": "오늘",
        "note": "34/36",
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
        "note": "누적 21건",
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


def _system(code: str, name: str, *, passed: int, total: int, **counts: int) -> dict[str, Any]:
    base = {
        "passed": passed,
        "anomaly": 0,
        "error": 0,
        "running": 0,
        "other": 0,
        "not_inspected": 0,
    }
    base.update(counts)
    return {
        "system_code": code,
        "system_name": name,
        "module_total": total,
        "pass_rate": round(passed / total * 100) if total else 0,
        "counts": base,
        "modules": [],
    }


def _summary(
    *,
    error: int = 0,
    anomaly: int = 0,
    not_inspected: int = 0,
    modules: int = 36,
    systems: list[dict] | None = None,
    attention: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "cards": CARDS,
        "systems": systems
        if systems is not None
        else [
            _system("HOM", "대표홈", passed=6, total=6),
            _system("FP", "위촉서류", passed=4, total=6, anomaly=2),
        ],
        "totals": {
            "modules": modules,
            "passed": modules - error - anomaly - not_inspected,
            "pass_rate": 94,
            "error": error,
            "anomaly": anomaly,
            "running": 0,
            "not_inspected": not_inspected,
        },
        "attention": attention or [],
        "date_label": "2026-08-20",
        "generated_at": "2026-08-21T08:00:00+00:00",
    }


def _attention(system: str, module: str, label: str) -> dict[str, Any]:
    return {
        "kind": "module",
        "system_code": system,
        "system_name": system,
        "module_id": "m",
        "module_name": module,
        "status_label": label,
        "tone": "error",
        "run_id": "r",
        "rank": 50,
    }


def test_error_headline_wins():
    report = build_daily_report(_summary(error=2), date_label="2026-08-20")
    assert report["headline"] == f"{module_status_label(ModuleStatus.ERROR)} 2건"
    assert report["status_value"] == ModuleStatus.ERROR.value


def test_anomaly_headline_when_no_error():
    report = build_daily_report(_summary(anomaly=3), date_label="2026-08-20")
    assert report["headline"] == f"{module_status_label(ModuleStatus.ANOMALY)} 3건"
    assert report["status_value"] == ModuleStatus.ANOMALY.value


def test_error_beats_anomaly():
    report = build_daily_report(_summary(error=1, anomaly=5), date_label="2026-08-20")
    assert report["status_value"] == ModuleStatus.ERROR.value


def test_not_inspected_day():
    report = build_daily_report(_summary(not_inspected=36, modules=36), date_label="2026-08-20")
    assert report["headline"] == "점검 미실행"
    assert report["status_value"] == ModuleStatus.PENDING.value


def test_all_clear_headline():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    assert report["headline"] == module_status_label(ModuleStatus.PASSED)
    assert report["status_value"] == ModuleStatus.PASSED.value


def test_kpis_come_from_cards_in_order():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    assert [label for label, _v, _u in report["kpis"]] == [
        "통과율",
        "스스로 복구",
        "내 승인 대기",
        "이번 달 절감",
    ]


def test_systems_carry_worst_status():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    by_code = {s["code"]: s for s in report["systems"]}
    assert by_code["HOM"]["status_value"] == ModuleStatus.PASSED.value
    assert by_code["FP"]["status_value"] == ModuleStatus.ANOMALY.value
    assert by_code["FP"]["passed"] == 4
    assert by_code["FP"]["total"] == 6


def test_system_error_beats_anomaly():
    systems = [_system("X", "X", passed=1, total=4, anomaly=1, error=1)]
    report = build_daily_report(_summary(systems=systems), date_label="2026-08-20")
    assert report["systems"][0]["status_value"] == ModuleStatus.ERROR.value


def test_uninspected_system_is_pending():
    systems = [_system("Y", "Y", passed=0, total=3, not_inspected=3)]
    report = build_daily_report(_summary(systems=systems), date_label="2026-08-20")
    assert report["systems"][0]["status_value"] == ModuleStatus.PENDING.value


def test_issues_come_from_attention():
    attention = [_attention("FP", "첨부", "점검실패"), _attention("HOM", "로그인", "이상징후")]
    report = build_daily_report(_summary(error=1, attention=attention), date_label="2026-08-20")
    assert [(i["system"], i["module"]) for i in report["issues"]] == [
        ("FP", "첨부"),
        ("HOM", "로그인"),
    ]


def test_date_label_is_echoed():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    assert report["date_label"] == "2026-08-20"


def test_source_has_no_hardcoded_status_labels():
    """P3-2 에서 파이썬에 한국어 라벨을 하드코딩했다가 지적받았다. 반복하지 않는다."""
    source = Path("app/notifications/daily_report.py").read_text(encoding="utf-8")
    for label in ("정상", "이상징후", "점검실패", "입력 대기", "실행 중"):
        assert f'"{label}"' not in source, label
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications.daily_report'`

- [ ] **Step 3: 구현한다**

`app/notifications/daily_report.py`:

```python
"""일간 리포트 내용 조립 — 요약 dict → 메일에 넣을 구조.

I/O 없음. ``DailyReportEmailService`` 가 ``get_daily_summary(date_label=어제)`` 결과를
넘겨 호출한다(``build_daily_summary``·``build_wall_view`` 와 같은 순수 빌더 패턴).

제목 규칙이 상황판(P3-2)과 다른 이유: 발송 시각(다음 날 아침)에는 어제의 OTP 대기가
이미 끝났거나 무의미하다. 하루가 닫힌 뒤의 결론만 담는다.

한국어 상태 라벨을 하드코딩하지 않는다 — status_labels.py 가 유일한 출처다.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ModuleStatus
from app.core.status_labels import module_status_label

# 점검이 하루 종일 한 번도 돌지 않은 상태. 어느 enum 에도 대응하지 않는
# 리포트 전용 문구라 여기서 정의한다(상태 라벨 복제가 아니다).
NOT_INSPECTED_HEADLINE = "점검 미실행"

# 시스템 블록의 최악 버킷 우선순위. daily_dashboard 의 버킷 이름을 쓴다.
_WORST_BUCKETS: tuple[tuple[str, ModuleStatus], ...] = (
    ("error", ModuleStatus.ERROR),
    ("anomaly", ModuleStatus.ANOMALY),
    ("running", ModuleStatus.RUNNING),
    ("other", ModuleStatus.BLOCKED),
    ("not_inspected", ModuleStatus.PENDING),
)


def _count(totals: dict[str, Any], key: str) -> int:
    return int(totals.get(key, 0) or 0)


def _headline(totals: dict[str, Any]) -> tuple[str, str]:
    """(제목, 상태값). 라벨은 status_labels.py 에서 가져온다."""
    error = _count(totals, "error")
    if error > 0:
        return f"{module_status_label(ModuleStatus.ERROR)} {error}건", ModuleStatus.ERROR.value
    anomaly = _count(totals, "anomaly")
    if anomaly > 0:
        return (
            f"{module_status_label(ModuleStatus.ANOMALY)} {anomaly}건",
            ModuleStatus.ANOMALY.value,
        )
    modules = _count(totals, "modules")
    if modules > 0 and _count(totals, "not_inspected") == modules:
        return NOT_INSPECTED_HEADLINE, ModuleStatus.PENDING.value
    return module_status_label(ModuleStatus.PASSED), ModuleStatus.PASSED.value


def _system_status(counts: dict[str, Any]) -> ModuleStatus:
    for bucket, status in _WORST_BUCKETS:
        if int(counts.get(bucket, 0) or 0) > 0:
            return status
    return ModuleStatus.PASSED


def build_daily_report(summary: dict[str, Any], *, date_label: str) -> dict[str, Any]:
    """일간 요약 → 리포트 메일 컨텍스트."""
    totals = summary.get("totals", {})
    headline, status_value = _headline(totals)

    systems: list[dict[str, Any]] = []
    for system in summary.get("systems", []):
        counts = system.get("counts", {})
        status = _system_status(counts)
        systems.append(
            {
                "code": system["system_code"],
                "name": system["system_name"],
                "passed": int(counts.get("passed", 0) or 0),
                "total": int(system.get("module_total", 0) or 0),
                "status_value": status.value,
                "status_label": module_status_label(status),
            }
        )

    issues = [
        {
            "system": item.get("system_name") or item.get("system_code") or "",
            "module": item.get("module_name") or "",
            "status_label": item.get("status_label") or "",
        }
        for item in summary.get("attention", [])
    ]

    return {
        "date_label": date_label,
        "headline": headline,
        "status_value": status_value,
        "kpis": [
            (card["label"], str(card["value"]), card.get("unit", ""))
            for card in summary.get("cards", [])
        ],
        "systems": systems,
        "issues": issues,
    }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_build.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/notifications/daily_report.py tests/test_daily_report_build.py
git commit -m "feat(notifications): 일간 리포트 내용 조립기 추가 — 제목 규칙 + SSOT 라벨"
```

---

## Task 5: 리포트 HTML 렌더

**Files:**
- Modify: `app/notifications/report_renderer.py` (끝에 추가)
- Test: `tests/test_daily_report_render.py`

**Interfaces:**
- Consumes: Task 4 의 `build_daily_report()` 반환 dict
- Produces: `render_daily_report_html(context: dict) -> str`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_daily_report_render.py`:

```python
"""일간 리포트 메일 HTML.

기존 Run 완료 메일과 같은 셸·헬퍼를 쓴다. 링크는 넣지 않는다 — 기존 메일에도 링크가
없고 공개 URL env 자체가 없다(설계 D6).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.core.enums import ModuleStatus
from app.notifications.daily_report import build_daily_report
from app.notifications.report_renderer import render_daily_report_html

CARDS = [
    {
        "key": "pass_rate",
        "label": "통과율",
        "value": 94,
        "unit": "%",
        "period": "오늘",
        "note": "34/36",
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
        "note": "누적 21건",
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


def _summary(*, error: int = 0, anomaly: int = 0) -> dict[str, Any]:
    return {
        "cards": CARDS,
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
        ],
        "totals": {
            "modules": 36,
            "passed": 34,
            "pass_rate": 94,
            "error": error,
            "anomaly": anomaly,
            "running": 0,
            "not_inspected": 0,
        },
        "attention": [
            {
                "kind": "module",
                "system_code": "FP",
                "system_name": "위촉서류",
                "module_id": "m",
                "module_name": "첨부",
                "status_label": "이상징후",
                "tone": "anomaly",
                "run_id": "r",
                "rank": 40,
            }
        ],
        "date_label": "2026-08-20",
        "generated_at": "2026-08-21T08:00:00+00:00",
    }


def _html(**kwargs) -> str:
    context = build_daily_report(_summary(**kwargs), date_label="2026-08-20")
    return render_daily_report_html(context)


@pytest.mark.parametrize(
    "kwargs", [{}, {"error": 2}, {"anomaly": 3}], ids=["clear", "error", "anomaly"]
)
def test_renders_without_error(kwargs) -> None:
    assert _html(**kwargs).strip()


def test_headline_is_in_the_html() -> None:
    assert "점검실패 2건" in _html(error=2)


def test_systems_table_lists_every_system() -> None:
    html = _html()
    assert "HOM" in html
    assert "대표홈" in html
    assert "위촉서류" in html


def test_system_row_shows_passed_over_total() -> None:
    assert "4/6" in _html()


def test_kpi_labels_are_rendered() -> None:
    html = _html()
    for label in ("통과율", "스스로 복구", "내 승인 대기", "이번 달 절감"):
        assert label in html


def test_issue_list_names_system_and_module() -> None:
    html = _html(anomaly=2)
    assert "위촉서류" in html
    assert "첨부" in html


def test_no_external_links() -> None:
    """설계 D6 — 자족적 메일. cid: 인라인 이미지는 이 리포트에 없다."""
    html = _html(error=1)
    assert not re.search(r"https?://", html)
    assert "<a " not in html


def test_date_is_in_the_html() -> None:
    assert "2026-08-20" in _html()


def test_running_status_is_not_neutral_gray() -> None:
    """Task 3 의 커버리지 수정이 렌더까지 이어지는지."""
    from app.notifications.report_renderer import INFO_COLOR, _status_color

    assert _status_color(ModuleStatus.RUNNING.value) == INFO_COLOR
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_render.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_daily_report_html'`

- [ ] **Step 3: 시스템 표 헬퍼를 추가한다**

`app/notifications/report_renderer.py` 의 `_module_table` 아래에 추가한다:

```python
def _system_summary_table(systems: list[dict]) -> str:
    """일간 리포트의 시스템별 요약 표 — 코드/이름/통과비/상태."""
    head = (
        f'<thead><tr style="background:{SOFT_BG};">'
        + "".join(
            f'<th style="padding:10px 12px;border:1px solid {BORDER};font-size:13px;'
            f'font-weight:700;color:{MUTED};text-align:left;">{escape(title)}</th>'
            for title in ("시스템", "이름", "통과", "상태")
        )
        + "</tr></thead>"
    )
    rows = "".join(
        (
            "<tr>"
            f'<td style="padding:10px 12px;border:1px solid {BORDER};font-size:13px;'
            f'font-weight:700;color:{INK};">{escape(system["code"])}</td>'
            f'<td style="padding:10px 12px;border:1px solid {BORDER};font-size:13px;'
            f'color:{INK};">{escape(system["name"])}</td>'
            f'<td style="padding:10px 12px;border:1px solid {BORDER};font-size:13px;'
            f'color:{MUTED};">{system["passed"]}/{system["total"]}</td>'
            f'<td style="padding:10px 12px;border:1px solid {BORDER};font-size:13px;'
            f'font-weight:700;color:{_status_color(system["status_value"])};">'
            f"{escape(system['status_label'])}</td>"
            "</tr>"
        )
        for system in systems
    )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:collapse;">{head}<tbody>{rows}</tbody></table>'
    )
```

- [ ] **Step 4: 렌더 함수를 추가한다**

`report_renderer.py` **맨 끝**에 추가한다:

```python
# --- 일간 리포트 (P3-3) -------------------------------------------------------------
def render_daily_report_html(context: dict) -> str:
    """일간 리포트 메일 본문.

    Run/Suite 보고서와 같은 셸·헬퍼를 쓴다. 링크는 넣지 않는다 — 기존 메일에도 링크가
    없고 공개 URL 설정 자체가 없다(설계 D6).
    """
    status_value = context["status_value"]
    accent = _status_color(status_value)

    title = _title_block(
        f"[E2E] {context['date_label']} 점검 결과",
        status_value,
        context["headline"],
        context["date_label"],
    )

    kpi = _kpi_cards([(label, f"{value}{unit}", INK) for label, value, unit in context["kpis"]])

    body = _section(1, "요약", kpi, accent)
    body += _section(2, "시스템별 결과", _system_summary_table(context["systems"]), accent)

    issues = context["issues"]
    if issues:
        items = "".join(
            f'<li style="margin-bottom:6px;">{escape(issue["system"])}'
            f" · {escape(issue['module'])} — "
            f"<b>{escape(issue['status_label'])}</b></li>"
            for issue in issues
        )
        issue_html = f'<ul style="margin:0;padding-left:20px;font-size:14px;">{items}</ul>'
    else:
        issue_html = _callout("확인이 필요한 건이 없습니다.", PASS_COLOR, PASS_SOFT_BG)
    body += _section(3, "확인 필요", issue_html, accent)
    body += _footer()

    return _shell(title, body)
```

**KPI 값 색을 `INK`(기본 먹색)로 두는 이유:** 카드의 `tone` 은 웹 토큰 이름이라 메일 팔레트로 옮기려면 매핑을 새로 발명해야 한다. 상태 강조는 제목 배지와 시스템 표가 이미 하므로 KPI 숫자는 중립으로 둔다.

- [ ] **Step 5: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_render.py -q`
Expected: PASS (11 passed)

`test_no_external_links` 가 실패하면 `_footer()` 나 헬퍼가 URL 을 넣은 것이다. 현재 `_footer` 는 텍스트뿐이므로 통과해야 한다.

- [ ] **Step 6: 커밋**

```bash
git add app/notifications/report_renderer.py tests/test_daily_report_render.py
git commit -m "feat(notifications): 일간 리포트 HTML 렌더러 추가"
```

---

## Task 6: 발송 서비스

**Files:**
- Create: `app/notifications/daily_report_email.py`
- Test: `tests/test_daily_report_email.py`

**Interfaces:**
- Consumes: Task 4 의 `build_daily_report()`, Task 5 의 `render_daily_report_html()`, Task 2 의 `get_daily_summary(date_label=…)`
- Produces:
  ```python
  class DailyReportEmailService:
      def __init__(self, summary_queries, dedup_store, config, recipients, sender_factory=GmailEmailSender)
      async def send_for(self, date_label: str) -> bool   # 발송했으면 True
  RECIPIENTS_ENV = "E2E_EMAIL_DAILY_REPORT_RECIPIENTS"
  def resolve_daily_report_recipients(values: dict[str, str | None]) -> tuple[str, ...]
  ```

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_daily_report_email.py`:

```python
"""일간 리포트 발송 — 수신자·중복 방어·실패 처리.

SMTP 는 스텁한다. 실제 발송은 테스트하지 않는다(docs/CI.md 의 "메일은 CI 밖").
"""

from __future__ import annotations

import smtplib
from typing import Any

import pytest

from app.notifications.daily_report_email import (
    DailyReportEmailService,
    resolve_daily_report_recipients,
)

SUMMARY: dict[str, Any] = {
    "cards": [
        {
            "key": "pass_rate",
            "label": "통과율",
            "value": 94,
            "unit": "%",
            "period": "오늘",
            "note": "34/36",
            "tone": "passed",
            "href": "",
            "estimated": False,
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
        "modules": 6,
        "passed": 6,
        "pass_rate": 100,
        "error": 0,
        "anomaly": 0,
        "running": 0,
        "not_inspected": 0,
    },
    "attention": [],
    "date_label": "2026-08-20",
    "generated_at": "2026-08-21T08:00:00+00:00",
}


class _Queries:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_daily_summary(
        self, *, user_id, allowed_system_codes, is_admin=False, date_label=None
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "allowed": allowed_system_codes,
                "is_admin": is_admin,
                "date_label": date_label,
            }
        )
        return SUMMARY


class _Dedup:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.claims: list[tuple[str, str]] = []
        self.releases: list[tuple[str, str]] = []

    def try_claim_sync(self, scope: str, entity_id: str) -> bool:
        self.claims.append((scope, entity_id))
        return self.allow

    def release_sync(self, scope: str, entity_id: str) -> None:
        self.releases.append((scope, entity_id))


class _Sender:
    def __init__(self, config) -> None:
        self.config = config
        self.sent: list[list[str]] = []

    def send(self, message, recipients: list[str]) -> None:
        self.sent.append(list(recipients))


class _FailingSender(_Sender):
    def __init__(self, config, exc: Exception) -> None:
        super().__init__(config)
        self.exc = exc

    def send(self, message, recipients):
        raise self.exc


class _Config:
    gmail_account = "sender@test.local"
    gmail_app_password = "pw"
    smtp_host = "smtp.test"
    smtp_port = 465
    timeout_seconds = 5


def _service(*, dedup=None, sender_cls=_Sender, recipients=("a@test.local",), queries=None):
    holder: dict[str, Any] = {}

    def factory(config):
        holder["sender"] = sender_cls(config)
        return holder["sender"]

    service = DailyReportEmailService(
        summary_queries=queries or _Queries(),
        dedup_store=dedup or _Dedup(),
        config=_Config(),
        recipients=tuple(recipients),
        sender_factory=factory,
    )
    return service, holder


def test_recipients_parse_pipe_separated():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": " a@x.com | b@x.com "}
    assert resolve_daily_report_recipients(values) == ("a@x.com", "b@x.com")


def test_recipients_empty_when_unset():
    assert resolve_daily_report_recipients({}) == ()


def test_recipients_drop_blank_entries():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "a@x.com||b@x.com|"}
    assert resolve_daily_report_recipients(values) == ("a@x.com", "b@x.com")


@pytest.mark.asyncio
async def test_sends_once_to_all_recipients():
    service, holder = _service(recipients=("a@x.com", "b@x.com"))
    assert await service.send_for("2026-08-20") is True
    assert holder["sender"].sent == [["a@x.com", "b@x.com"]]


@pytest.mark.asyncio
async def test_queries_the_requested_date_company_wide():
    queries = _Queries()
    service, _ = _service(queries=queries)
    await service.send_for("2026-08-20")
    assert queries.calls == [
        {"user_id": None, "allowed": None, "is_admin": False, "date_label": "2026-08-20"}
    ]


@pytest.mark.asyncio
async def test_no_recipients_means_no_send():
    service, holder = _service(recipients=())
    assert await service.send_for("2026-08-20") is False
    assert "sender" not in holder


@pytest.mark.asyncio
async def test_claim_is_scoped_to_the_date():
    dedup = _Dedup()
    service, _ = _service(dedup=dedup)
    await service.send_for("2026-08-20")
    assert dedup.claims == [("daily_report", "2026-08-20")]


@pytest.mark.asyncio
async def test_second_call_for_same_date_does_not_send():
    dedup = _Dedup(allow=False)
    service, holder = _service(dedup=dedup)
    assert await service.send_for("2026-08-20") is False
    assert "sender" not in holder


@pytest.mark.asyncio
async def test_permanent_failure_keeps_the_claim():
    """인증 실패로 하루를 건너뛴다 — 같은 날 실패 메일을 반복 시도하지 않는다(설계 §3.7)."""
    dedup = _Dedup()

    def failing(config):
        return _FailingSender(config, smtplib.SMTPAuthenticationError(535, b"bad"))

    service = DailyReportEmailService(
        summary_queries=_Queries(),
        dedup_store=dedup,
        config=_Config(),
        recipients=("a@x.com",),
        sender_factory=failing,
    )
    assert await service.send_for("2026-08-20") is False
    assert dedup.releases == []


@pytest.mark.asyncio
async def test_permanent_failure_does_not_raise():
    """스케줄러 루프를 죽이지 않는다."""

    def failing(config):
        return _FailingSender(config, smtplib.SMTPAuthenticationError(535, b"bad"))

    service = DailyReportEmailService(
        summary_queries=_Queries(),
        dedup_store=_Dedup(),
        config=_Config(),
        recipients=("a@x.com",),
        sender_factory=failing,
    )
    await service.send_for("2026-08-20")  # 예외가 전파되면 테스트 실패
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_email.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications.daily_report_email'`

- [ ] **Step 3: 구현한다**

`app/notifications/daily_report_email.py`:

```python
"""일간 리포트 메일 발송 — 수신자 해석 · 하루 한 통 보장 · 실패 처리.

발송 자체는 기존 ``GmailEmailSender``(tenacity 재시도 포함)를 그대로 쓴다.
첨부·인라인 이미지가 없으므로 메시지는 여기서 간단히 만든다 —
``run_completion_email`` 의 비공개 ``_build_email_message`` 를 임포트하지 않는다.
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any, Protocol

from app.core.logging import get_logger
from app.notifications.daily_report import build_daily_report
from app.notifications.report_renderer import render_daily_report_html
from app.notifications.run_completion_email import GmailEmailSender

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

RECIPIENTS_ENV = "E2E_EMAIL_DAILY_REPORT_RECIPIENTS"
DEDUP_SCOPE = "daily_report"


class _DedupStore(Protocol):
    def try_claim_sync(self, scope: str, entity_id: str) -> bool: ...


def resolve_daily_report_recipients(values: dict[str, str | None]) -> tuple[str, ...]:
    """파이프 구분 수신자 문자열 → 튜플. 기존 메일 수신자 형식과 같다."""
    raw = (values.get(RECIPIENTS_ENV) or "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split("|") if part.strip())


def _build_message(*, subject: str, from_addr: str, html_body: str, plain_body: str):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_addr
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message


class DailyReportEmailService:
    def __init__(
        self,
        *,
        summary_queries: Any,
        dedup_store: _DedupStore,
        config: Any,
        recipients: tuple[str, ...],
        sender_factory: Callable[[Any], Any] = GmailEmailSender,
    ) -> None:
        self._summary_queries = summary_queries
        self._dedup_store = dedup_store
        self._config = config
        self._recipients = recipients
        self._sender_factory = sender_factory

    async def send_for(self, date_label: str) -> bool:
        """지정일 리포트를 보낸다. 실제로 보냈으면 True."""
        if not self._recipients:
            logger.info(
                "일간 리포트 수신자가 없어 발송하지 않음",
                log_event="daily_report.no_recipients",
                date_label=date_label,
            )
            return False

        if not self._dedup_store.try_claim_sync(DEDUP_SCOPE, date_label):
            logger.info(
                "일간 리포트가 이미 발송됨",
                log_event="daily_report.already_sent",
                date_label=date_label,
            )
            return False

        summary = await self._summary_queries.get_daily_summary(
            user_id=None,  # 리포트에 개인 기여분은 의미가 없다
            allowed_system_codes=None,  # 전사 리포트
            is_admin=False,
            date_label=date_label,
        )
        report = build_daily_report(summary, date_label=date_label)
        html = render_daily_report_html(report)
        subject = f"[E2E] {date_label} 점검 결과 — {report['headline']}"
        plain = f"{date_label} 점검 결과: {report['headline']}"

        message = _build_message(
            subject=subject,
            from_addr=self._config.gmail_account,
            html_body=html,
            plain_body=plain,
        )
        try:
            self._sender_factory(self._config).send(message, list(self._recipients))
        except Exception as exc:
            # claim 을 해제하지 않는다 — 같은 날 실패 메일을 반복 시도하는 것보다
            # 하루를 건너뛰고 다음 날 다시 시도하는 편이 낫다(설계 §3.7).
            logger.exception(
                "일간 리포트 발송 실패 — 오늘은 건너뛴다",
                log_event="daily_report.send_failed",
                date_label=date_label,
                error=str(exc),
            )
            return False

        logger.info(
            "일간 리포트 발송",
            log_event="daily_report.sent",
            date_label=date_label,
            recipient_count=len(self._recipients),
        )
        return True
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_email.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/notifications/daily_report_email.py tests/test_daily_report_email.py
git commit -m "feat(notifications): 일간 리포트 발송 서비스 추가 — 하루 한 통 보장"
```

---

## Task 7: 스케줄러와 배선

**Files:**
- Create: `app/contexts/scheduling/daily_report_scheduler.py`
- Modify: `app/contexts/scheduling/composition.py`
- Modify: `app/composition/container.py`
- Test: `tests/test_daily_report_scheduler.py`

**Interfaces:**
- Consumes: Task 1 의 설정, Task 6 의 `DailyReportEmailService.send_for(date_label)`
- Produces: `DailyReportScheduler.from_env(service) -> DailyReportScheduler | None`, `run_forever()`

- [ ] **Step 1: 테스트를 작성한다**

`tests/test_daily_report_scheduler.py`:

```python
"""일간 리포트 스케줄러 — cron·비활성·대상일 계산.

run_retention.py 와 동형이다. 기본은 꺼져 있어야 한다(설계 D3).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.scheduling.daily_report_scheduler import (
    DEFAULT_DAILY_REPORT_CRON,
    DailyReportScheduler,
)


class _Service:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_for(self, date_label: str) -> bool:
        self.sent.append(date_label)
        return True


def test_from_env_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("E2E_EMAIL_DAILY_REPORT_ENABLED", raising=False)
    from app.core.settings import get_settings

    get_settings.cache_clear()
    assert DailyReportScheduler.from_env(_Service()) is None


def test_from_env_builds_when_enabled(monkeypatch):
    monkeypatch.setenv("E2E_EMAIL_DAILY_REPORT_ENABLED", "true")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    scheduler = DailyReportScheduler.from_env(_Service())
    assert scheduler is not None


def test_default_cron_is_eight_am():
    assert DEFAULT_DAILY_REPORT_CRON == "0 8 * * *"


def test_target_date_is_the_previous_day():
    """리포트는 어제를 보고한다(설계 D1)."""
    scheduler = DailyReportScheduler(report_service=_Service(), cron=DEFAULT_DAILY_REPORT_CRON)
    # KST 2026-08-21 08:00 == UTC 2026-08-20 23:00
    label = scheduler.target_date_label(datetime(2026, 8, 20, 23, 0, tzinfo=UTC))
    assert label == "2026-08-20"


@pytest.mark.asyncio
async def test_tick_sends_for_yesterday_when_cron_matches():
    service = _Service()
    scheduler = DailyReportScheduler(report_service=service, cron="0 8 * * *")
    # KST 2026-08-21 08:00 정각
    await scheduler.tick_at(datetime(2026, 8, 20, 23, 0, tzinfo=UTC))
    assert service.sent == ["2026-08-20"]


@pytest.mark.asyncio
async def test_tick_does_nothing_when_cron_does_not_match():
    service = _Service()
    scheduler = DailyReportScheduler(report_service=service, cron="0 8 * * *")
    # KST 2026-08-21 09:00 — cron 불일치
    await scheduler.tick_at(datetime(2026, 8, 21, 0, 0, tzinfo=UTC))
    assert service.sent == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_scheduler.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.contexts.scheduling.daily_report_scheduler'`

- [ ] **Step 3: 구현한다**

`app/contexts/scheduling/daily_report_scheduler.py`:

```python
"""일간 리포트 메일 스케줄러 — cron 시각에 어제 리포트를 보낸다.

``run_retention.py`` 의 RunRetentionScheduler 와 동형이다: parse_cron + 틱 루프 +
from_env(설정이 꺼져 있으면 None).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.contexts.scheduling.cron import parse_cron
from app.contexts.scheduling.scheduler import _resolve_timezone
from app.core.logging import get_logger
from app.core.schedule_time import schedule_day_label
from app.core.settings import get_settings

if TYPE_CHECKING:
    from app.notifications.daily_report_email import DailyReportEmailService

logger = get_logger(__name__)

DEFAULT_DAILY_REPORT_CRON = "0 8 * * *"
TICK_SECONDS = 30


class DailyReportScheduler:
    def __init__(
        self,
        *,
        report_service: DailyReportEmailService,
        cron: str = DEFAULT_DAILY_REPORT_CRON,
        tick_seconds: int = TICK_SECONDS,
    ) -> None:
        self._service = report_service
        self._cron_expr = cron
        self._cron = parse_cron(cron)
        self._tick_seconds = tick_seconds
        self._running = False
        _tz, self._timezone_name = _resolve_timezone()

    @classmethod
    def from_env(cls, report_service: DailyReportEmailService) -> DailyReportScheduler | None:
        settings = get_settings()
        if not settings.daily_report_enabled:
            return None
        cron = (settings.daily_report_cron or "").strip() or DEFAULT_DAILY_REPORT_CRON
        parse_cron(cron)
        return cls(report_service=report_service, cron=cron)

    def target_date_label(self, now_utc: datetime) -> str:
        """리포트가 보고할 날짜 — 스케줄 타임존 기준 전날(설계 D1)."""
        return schedule_day_label(now_utc - timedelta(days=1))

    async def tick_at(self, now_utc: datetime) -> None:
        tz, _name = _resolve_timezone()
        now_local = now_utc.astimezone(tz)
        if not self._cron.matches(now_local):
            return
        await self._service.send_for(self.target_date_label(now_utc))

    async def run_forever(self) -> None:
        self._running = True
        logger.info(
            "일간 리포트 스케줄러 시작",
            log_event="daily_report.started",
            timezone=self._timezone_name,
            cron=self._cron_expr,
            tick_seconds=self._tick_seconds,
        )
        while self._running:
            try:
                await self.tick_at(datetime.now(UTC))
            except Exception as exc:
                logger.exception(
                    "일간 리포트 tick 오류",
                    log_event="daily_report.tick_error",
                    error=str(exc),
                )
            try:
                await asyncio.sleep(self._tick_seconds)
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
```

**`_resolve_timezone` 임포트:** `scheduler.py` 의 비공개 함수지만 `app/contexts/scheduling/run_retention.py:9` 가 이미 같은 방식으로 직접 임포트한다(`from app.contexts.scheduling.scheduler import _resolve_timezone`). 같은 컨텍스트 안이므로 확립된 패턴을 그대로 따른다.

**중복 방지 주의:** cron 이 분 단위로 맞으면 `tick_seconds=30` 이라 같은 분에 두 번 발화할 수 있다. **그 방어는 Task 6 의 dedup claim 이 담당한다** — 두 번째 호출은 claim 실패로 조용히 넘어간다. 스케줄러에 별도 상태를 두지 않는다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_scheduler.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: composition 에 배선한다**

`app/contexts/scheduling/composition.py`:

```python
@dataclass
class SchedulingContainer:
    schedule_repository: SqliteScheduleRepository
    scheduler: SchedulerService | None = None
    retention_scheduler: RunRetentionScheduler | None = None
    daily_report_scheduler: DailyReportScheduler | None = None


def compose_daily_report_scheduler(
    report_service: DailyReportEmailService,
) -> DailyReportScheduler | None:
    return DailyReportScheduler.from_env(report_service)
```

import 를 추가한다:

```python
from app.contexts.scheduling.daily_report_scheduler import DailyReportScheduler
from app.notifications.daily_report_email import DailyReportEmailService
```

- [ ] **Step 6: 컨테이너에서 서비스와 스케줄러를 만든다**

**배선 위치는 `wire_read_models()` 의 끝**이다 — `container.py:272-277` 에서 `self.insights.daily_summary_queries` 가 만들어진 **직후**. `retention_scheduler` 를 만드는 `container.py:252` 는 `wire_orchestration()` 안이고 `daily_summary_queries` 보다 앞이라, 거기 두면 아직 없는 객체를 참조한다.

`self.insights.daily_summary_queries = DailySummaryQueries(...)` 블록 바로 아래에 추가한다:

```text
        email_config = EmailNotificationConfig.from_env(self.execution.system_codes)
        if email_config is not None:
            # 컨테이너에 dedup 스토어 필드가 없다. 같은 DB(self.es_db)로 새로 만들면
            # claim 테이블이 Run 완료 메일과 공유되고, scope 가 "daily_report" 로
            # 달라 충돌하지 않는다.
            daily_report_service = DailyReportEmailService(
                summary_queries=self.insights.daily_summary_queries,
                dedup_store=SqliteEmailNotificationDedupStore(self.es_db),
                config=email_config,
                recipients=resolve_daily_report_recipients(
                    load_dotenv_file(DEFAULT_ENV_FILE_PATH)
                ),
            )
            self.scheduling.daily_report_scheduler = compose_daily_report_scheduler(
                daily_report_service
            )
```

**파일 상단에 추가할 임포트 4줄** — `container.py:59` 는 지금 `RunCompletionEmailNotifier` 만 임포트한다:

```text
from app.contexts.scheduling.composition import compose_daily_report_scheduler
from app.core.env_utils import DEFAULT_ENV_FILE_PATH, load_dotenv_file
from app.notifications.daily_report_email import (
    DailyReportEmailService,
    resolve_daily_report_recipients,
)
from app.notifications.infrastructure.sqlite_email_notification_dedup import (
    SqliteEmailNotificationDedupStore,
)
from app.notifications.run_completion_email import EmailNotificationConfig
```

`compose_daily_report_scheduler` 는 기존 `compose_retention_scheduler` 임포트(`container.py:40`) 옆에 합쳐 넣는다.

**확정된 이름들** (실측):

| 필요한 것 | 실제 위치 |
| --- | --- |
| 요약 쿼리 | `self.insights.daily_summary_queries` (`container.py:274` 에서 생성) |
| dedup 스토어 | 컨테이너에 없다. `app/platform/eventing/composition.py:28` 이 `SqliteEmailNotificationDedupStore(es_db)` 로 만든다. **여기서도 `SqliteEmailNotificationDedupStore(self.es_db)` 로 새로 만든다** — 같은 DB(`container.py:131` 의 `self.es_db`)를 쓰므로 claim 테이블이 공유되고, scope 가 `"daily_report"` 로 달라 Run 완료 메일과 충돌하지 않는다 |
| env 값 읽기 | `dotenv_values` 는 임포트가 아니라 `load_dotenv_file(DEFAULT_ENV_FILE_PATH)` 의 결과 지역 변수다(`run_completion_email.py:114`). 두 이름 모두 `app.core.env_utils` 에 있다 |
| 스케줄러 조립 지점 | **`wire_read_models()` 끝** (`container.py:272-277` 의 `daily_summary_queries` 생성 직후). `container.py:252` 는 `wire_orchestration()` 안이라 너무 이르다 |

`EmailNotificationConfig.from_env` 는 `container.py:367` 근처에서 `inspect_env_status` 용으로 이미 호출된다. 그 호출은 상태 점검용이므로 별개다 — 여기서 `from_env` 를 다시 부르되, `None` 이면(메일 설정 없음) 스케줄러를 만들지 않는다.

- [ ] **Step 7: 스케줄러를 기동한다**

`container.py:400-404` 의 기동 블록에 같은 형태로 추가한다:

```python
        if self.scheduling.daily_report_scheduler is not None:
            self._daily_report_task = asyncio.create_task(
                self.scheduling.daily_report_scheduler.run_forever()
            )
```

그리고 `container.py:417-418` 의 정지 블록에 추가한다:

```python
        if self.scheduling.daily_report_scheduler is not None:
            self.scheduling.daily_report_scheduler.stop()
```

`None` 이면 띄우지도 멈추지도 않는다 — `retention_scheduler` 와 같은 규율이다.

- [ ] **Step 8: 전체 검증**

Run: `python3 -m pytest tests/ -q`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `python3 scripts/check_architecture_gates.py && python3 -m importlinter.cli lint`
Expected: 통과. 위반이 뜨면 `app/contexts/scheduling` → `app/notifications` 방향 의존이 계약에 없는 것이다. 그 경우 `DailyReportScheduler` 가 `DailyReportEmailService` 를 타입으로만 참조하도록(`TYPE_CHECKING` 하위 임포트, 이미 그렇게 되어 있음) 유지하고, 런타임 임포트가 남아 있는지 확인한다.

- [ ] **Step 9: 육안 검증 (선택 — env 가 있을 때만)**

SMTP 자격증명이 있는 환경에서만 한다. **수신자를 본인 주소로만 두고** 확인한다:

```bash
E2E_EMAIL_ENABLED=true \
E2E_EMAIL_DAILY_REPORT_ENABLED=true \
E2E_EMAIL_DAILY_REPORT_CRON="* * * * *" \
E2E_EMAIL_DAILY_REPORT_RECIPIENTS="본인@주소" \
python3 scripts/run_local.py
```

확인 항목:
- 1분 안에 메일이 **한 통만** 온다 (cron 이 매분이어도 dedup claim 이 하루 한 통으로 막는다)
- 제목이 `[E2E] {어제} 점검 결과 — {결론}` 형태다
- 본문에 시스템별 표와 KPI 가 보인다
- 링크가 하나도 없다
- Outlook/Gmail 양쪽에서 레이아웃이 깨지지 않는다

- [ ] **Step 10: 커밋**

```bash
git add app/contexts/scheduling/ app/composition/container.py \
        tests/test_daily_report_scheduler.py
git commit -m "feat(scheduling): 일간 리포트 스케줄러 추가 + 컨테이너 배선"
```

---

## 완료 기준 (P3-3 DoD)

- [ ] `E2E_EMAIL_DAILY_REPORT_ENABLED` 미설정 시 `from_env` 가 `None`
- [ ] 수신자가 비어 있으면 발송하지 않는다
- [ ] 같은 날짜로 두 번 호출해도 SMTP 는 한 번
- [ ] 재시도 불가 오류에서 claim 유지 + 예외 미전파
- [ ] 제목 4경로(실패/이상/미실행/정상) 각각 올바른 제목·상태값
- [ ] `daily_report.py` 에 한국어 상태 라벨 리터럴 0건
- [ ] `_STATUS_COLORS` 가 3개 enum 의 모든 값을 명시 포함
- [ ] 렌더 결과에 `http://`·`https://`·`<a ` 0건
- [ ] `date_label` 미전달 시 일간 현황·상황판 동작 불변
- [ ] `python3 -m pytest tests/ -q` 전부 통과
- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 전 게이트 통과
- [ ] `docs/INSTALL.md` + `.env.example` 에 env 3종 문서화

---

## P3-3 이후

남은 조각은 **Step 7 — 잔여 화면 이관**이다(13파일 8,909줄). 이 계획이 남기는 것:

- `schedule_day_start_utc(date_label)` — 임의 날짜 집계가 필요한 모든 곳이 쓴다
- `build_daily_report` 의 제목 규칙 — 주간 리포트가 같은 형태를 쓴다
- `_STATUS_COLORS` 전수 가드 — Step 7 이 메일 팔레트를 SSOT 로 통일할 때 안전망이 된다

**Step 7 이 이어받을 항목**(이 계획이 의도적으로 남긴 것):
- 메일 팔레트 값 통일 — 지금은 커버리지만 메웠고 값은 웹과 다르다
- `report_renderer.py` 분할 — 약 1,050줄이 된다
- 리포트에 `/wall` 딥링크 — P3-2 병합 후 비인증 경로가 생기면 자연스럽다
