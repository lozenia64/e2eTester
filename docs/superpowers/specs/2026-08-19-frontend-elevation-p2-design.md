# 프론트엔드 고도화 P2 (일간 현황) — Design

**작성일:** 2026-08-19
**상태:** 초안 (사용자 리뷰 대기)
**상위 설계:** `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§3.8~§3.10, Step 3)
**선행:** P1 기반 (`feat/frontend-elevation-p1`) — 토큰·컴포넌트 페어 규약·프론트 게이트 6종
**대상:** `app/contexts/insights/application/daily_dashboard.py`, `app/contexts/insights/application/daily_summary.py`(신규), `app/contexts/insights/application/stats_service.py`, `app/orchestrator/queries/`, `app/api/routes_daily.py`, `app/web/templates/dashboard/partials/zone_a_kpi.html`, `app/web/frontend/components/kpi-card/`(신규)

---

## 1. 문제

### 1.1 목표 재확인

상위 설계 §2.1 목표 4 — **이미 계산되는 자산(자동 복구·절감 시간·승인 대기)을 일간 현황 메인 화면에 올린다.** P2 는 이 목표 하나만 완수한다.

### 1.2 상위 설계의 사실오류 정정

상위 설계 §1.5 는 healing 지표가 `/self-healing` 하위에 묻혀 노출 작업이 필요하다고 적었다. **API 레벨에서는 이미 열려 있다.**

`app/api/routes_healing.py:50` `GET /api/healing/metrics` 는 `require_admin` 이 아니라 `get_current_user` + `_allowed(current_user)` 시스템 스코프로 동작한다. 따라서 healing 지표는 **권한 작업이 아니라 배치 작업**이며, P2 의 백엔드 작업량은 상위 설계 추정보다 작다.

반면 `manual_seconds_saved` 는 정정이 필요 없다. `app/api/routes_admin.py:329` `GET /api/admin/stats/usage` 는 `require_admin` 이며, 이것이 경영진이 절감 지표를 볼 수 없는 실제 원인이다.

### 1.3 이미 존재하는 계산 (신규 로직 0건)

| 자산 | 위치 | 반환 |
| --- | --- | --- |
| 자동 복구·무인 통과율·MTTR·승인 대기 | `app/contexts/healing/metrics.py:build_healing_metrics()` | `kpi.month_auto_recovered` · `kpi.unattended_rate` · `kpi.mttr_ms` · `kpi.pending_patches` · `trend[]`(일별 버킷) |
| 절감 시간 | `app/contexts/insights/application/stats_service.py:41` `get_usage_stats(from_dt, to_dt)` | `UsageStats.by_user[].manual_seconds_saved` · `by_system[].manual_seconds_saved` |
| 일간 집계 | `app/contexts/insights/application/daily_dashboard.py:411` | `totals.pass_rate` 외 |

### 1.4 근본 문제 1 — `totals` 빌더가 이중이고 한쪽은 죽어 있다

`daily_dashboard.py` 에 `totals` 를 만드는 함수가 둘이다.

| 함수 | 위치 | 프로덕션 사용 |
| --- | --- | --- |
| `build_daily_dashboard` (Run 객체 기반) | 231행 | **없음** |
| `build_daily_dashboard_from_projection` | 378행 | `app/orchestrator/queries/daily_queries.py:54` |

`build_daily_dashboard` 를 호출하는 곳은 테스트 4파일뿐이다 — `tests/test_daily_dashboard.py`(6곳), `tests/test_dashboard_fragments_http.py`(4곳), `tests/test_dashboard_viewport.py`(1곳).

**즉 프래그먼트 렌더 테스트가 프로덕션이 만들지 않는 데이터 모양을 검증하고 있다.** KPI 필드를 `totals` 에 추가할 때 레거시 빌더에만 추가하면 테스트는 전부 통과하면서 실제 화면은 비어 있게 된다.

### 1.5 근본 문제 2 — 일간 현황은 스크롤이 없는 화면이다

`app/web/frontend/styles/dashboard.css:5`

```css
body:has(.dash) {
  overflow: hidden;
  height: 100dvh;
  max-height: 100dvh;
}
```

전용 계획 문서 두 건(`docs/superpowers/plans/2026-08-15-viewport-fit-no-scroll.md`, `2026-08-15-dashboard-zone-c-fit-p1.md`)이 이 불변식을 만들었다.

그리고 `zone_a_kpi.html` 에는 **이미 4타일 밴드(`dash-stats`)가 있다** — 이상징후·점검실패·진행 중·미점검.

따라서 상위 설계 §3.8 의 "KPI 밴드 추가"는 **그대로 실행할 수 없다.** 밴드를 더하면 넌스크롤 불변식이 깨진다. 무엇을 내주고 무엇을 넣을지가 P2 의 핵심 결정이다.

---

## 2. 결정

| # | 결정 | 대안 대비 이유 |
| --- | --- | --- |
| D1 | **`dash-stats` 4타일을 KPI 카드 4장으로 교체** | 세로 공간 증가 0 으로 넌스크롤 불변식 유지. 좌우 분할(타일 7개)은 밀도 과다·모바일 붕괴, 히어로 압축은 "오늘 한 문장"을 약화시켜 §3.8 의도와 충돌 |
| D2 | **히어로의 큰 통과율 숫자를 제거하고 밴드 1번 칸으로 이동** | D1 적용 시 통과율이 히어로와 밴드에 중복된다. 상위 설계 §3.8 의 원래 형태 |
| D3 | **절감 지표는 전사 합계 + 본인 기여분까지만 개방** | `UserUsageStat` 은 이름·이메일을 포함한다. 사용자별 분해를 열면 "누가 얼마나 돌렸나"가 전직원에게 노출된다 |
| D4 | **레거시 빌더 `build_daily_dashboard` 제거 + 테스트 4파일 이관** | 공통 함수 추출은 `totals` 만 통일하고 `_module_view` 등 다른 경로의 이중성은 남긴다. 제거해야 테스트가 비로소 프로덕션을 검증한다 |
| D5 | **기간을 KPI마다 명시하고 섞지 않는다** | 라벨 없는 숫자는 회의실에서 즉시 혼란을 만든다 |

---

## 3. 설계

### 3.1 KPI 조립 전용 읽기 서비스

KPI 카드 4장은 세 컨텍스트에 걸쳐 있다 — 일간(`insights`) · 치유(`healing`) · 사용량(`stats`). 기존 `DailyDashboardQueries` 에 이를 물리면 일간 쿼리가 3방향 fan-out 을 하게 된다.

```text
app/contexts/insights/application/daily_summary.py
  build_daily_summary(totals, healing_metrics, savings, *, today) -> dict   # 순수, I/O 없음
app/orchestrator/queries/daily_summary_queries.py
  DailySummaryQueries.get_daily_summary(*, user, allowed_system_codes) -> dict
```

순수 조립 함수를 분리하는 것은 `build_healing_metrics` 와 동일한 패턴이다(스토어에서 읽은 것을 넘겨받아 계산, I/O 무지). 단위 테스트가 붙는다.

### 3.2 노출 경로

| 경로 | 용도 | 권한 |
| --- | --- | --- |
| `GET /api/dashboard/daily/summary` | JSON. P3 의 상황판·메일 리포트가 재사용 | `get_current_user` |
| `GET /api/dashboard/daily/fragments/kpi` (기존) | htmx 프래그먼트. `zone_a_kpi.html` 이 소비 | `get_current_user` |

`kpi` 프래그먼트 라우트는 `_load_dashboard` 대신 `DailySummaryQueries` 를 쓴다. `matrix` 프래그먼트와 `system/{code}/panel` 은 변경하지 않는다.

### 3.3 절감 지표 — 전사 합계 + 내 기여분 (D3)

`StatsService` 에 비관리자용 메서드를 추가한다.

```python
async def get_savings_summary(
    self, *, from_dt: datetime, to_dt: datetime, user_id: str | None
) -> SavingsSummary
```

`SavingsSummary` (신규 모델, `app/core/stats_models.py`):

| 필드 | 성격 | 의미 |
| --- | --- | --- |
| `total_seconds: int` | 파생(추정) | 전사 합계 |
| `my_seconds: int` | 파생(추정) | 로그인 사용자 본인 기여분 |
| `run_count: int` | **실측** | 산출 근거 |
| `module_count: int` | **실측** | 산출 근거 |
| `basis_updated_at: datetime \| None` | 메타 | `ModuleSettings` 추정치 최종 갱신일 |
| `estimated: bool` | 메타 | 항상 `True` (현 산출 방식이 추정이므로) |
| `note: str` | 메타 | 근거 문자열. 예 `"1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)"` |

**계약: 이 응답에는 `user_id` · `email` · `user_name` 을 담은 리스트가 포함되지 않는다.** 사용자별 분해는 `require_admin` 인 `/api/admin/stats/usage` 에만 남는다. 이를 회귀 테스트로 강제한다(§5).

### 3.4 기간 프레이밍 (D5)

| KPI | 기간 | 출처 |
| --- | --- | --- |
| 통과율 | **오늘** | `totals.pass_rate` |
| 스스로 복구 | **오늘** (부연: 이번 달 누적) | `build_healing_metrics()["trend"]` 에서 오늘 날짜 버킷 |
| 승인 대기 | **현재 시점** (기간 없음) | `kpi.pending_patches` |
| 절감 시간 | **이번 달** | `get_savings_summary(from_dt=월초, to_dt=now)` |

각 카드는 기간 라벨을 본문에 표시한다. 라벨 없는 숫자를 두지 않는다.

### 3.4.1 날짜 경계 — 타임존이 어긋나 있다 (수정 필요)

일간 대시보드는 `app/orchestrator/queries/daily_queries.py:44` 에서 `schedule_today_label()` 로 오늘을 정한다. 이는 `app/core/schedule_time.py` 의 `resolve_schedule_timezone()` 기준이며 기본값은 **Asia/Seoul** 이다.

반면 `build_healing_metrics` 는 UTC 로 버킷을 만든다.

- `metrics.py` 의 월 경계: `now.replace(day=1, ...)` 를 `_as_utc(now)` 위에서 계산
- 일별 추이 키: `_as_utc(event.created_at).date().isoformat()` — **UTC 날짜**

따라서 KST `00:00~09:00` 구간에는 healing 의 "오늘"이 아직 전날 UTC 날짜다. **사람들이 실제로 대시보드를 보는 아침 시간대에 자동 복구 건수가 어긋난다.**

**해결:** `build_healing_metrics` 에 날짜 라벨 함수를 선택 인자로 추가한다(가산적 변경, 기본값은 현행 UTC 동작 유지).

```python
def build_healing_metrics(
    events, patches, *, now, trend_days=30,
    day_label: Callable[[datetime], str] = _utc_day_label,   # 신규
) -> dict[str, Any]:
```

`DailySummaryQueries` 와 `HealingService.metrics()` 가 `day_label=schedule_day_label` 을 넘긴다 — 자가 치유 화면이 UTC 날짜를, 일간 현황이 KST 날짜를 보여주는 상태 자체가 버그이므로 **서비스 계층은 의도적으로 동작이 바뀐다**(순수 함수의 기본 인자만 UTC 로 유지). 월 경계도 같은 타임존으로 계산한다. 절감 시간의 "이번 달" 역시 동일 타임존 기준 월초를 `from_dt` 로 쓴다.

이렇게 하면 버킷팅 구현이 하나로 유지되고, 기존 `/api/healing/metrics` 호출자는 기본 인자로 동작이 바뀌지 않는다.

**앞선 초안에서 "healing 컨텍스트를 수정하지 않는다"고 적었으나 이는 틀렸다.** 타임존 일치 없이는 KPI 가 아침마다 틀린 숫자를 보여준다.

### 3.5 레거시 빌더 제거 (D4)

`build_daily_dashboard` 와 그 전용 헬퍼 `_module_view`(168행) · `_system_view`(188행) · `_pick_module_status`(150행)를 삭제한다. 약 150줄이 줄어든다.

테스트 이관: 픽스처가 `Run` 객체 대신 `DailyStatusRow` 를 만들도록 바꾼다.

| 파일 | 호출 지점 |
| --- | --- |
| `tests/test_daily_dashboard.py` | 64·89·124·133·148·171행 |
| `tests/test_dashboard_fragments_http.py` | 54·90·226·247행 |
| `tests/test_dashboard_viewport.py` | 211행 |

**이 작업을 먼저 하고 독립 커밋으로 분리한다.** KPI 작업과 섞으면 실패 원인이 뒤엉킨다.

### 3.6 화면 — `zone_a_kpi.html` 재구성

```text
히어로   "오늘 점검은 정상입니다"                          [새로고침]
         8월 19일 · 34/36 모듈 정상 · 이상징후 2건 · 갱신 09:14
─────────────────────────────────────────────────────────
밴드     ┌────────┬──────────┬──────────┬──────────────┐
         │ 통과율 │ 스스로   │ 승인 대기 │ 이번 달 절감 │
         │  94%   │ 복구 7   │    2     │    310h [추정]│
         │ 오늘   │ 오늘     │ 패치     │ 1,240회 × …  │
         └────────┴──────────┴──────────┴──────────────┘
주의선   ● HOM · 로그인 · 이상징후          +2건   전체 보기
─────────────────────────────────────────────────────────
매트릭스 시스템 6개
```

변경:

- `dash-hero__title` 고정 문자열 "오늘의 점검 현황" → **상태에 따라 바뀌는 결론 문장.** 기존 `dash-hero__summary` 의 분기 로직을 제목으로 승격한다.
- `dash-hero__rate-block`(큰 통과율) 제거 → 밴드 1번 칸 (D2)
- `dash-stats` 4타일 → `KpiCard` 4장 (D1)
- `dash-hero__meta` 에 이상징후·점검실패 건수를 병기 — 타일에서 사라진 숫자를 문장이 흡수한다
- 주의선(`dash-attention`)·매트릭스는 변경하지 않는다

### 3.7 `KpiCard` 컴포넌트

P1 이 `status-badge` 로 확립한 페어 규약을 따른다. `TEMPLATE_SEARCH_DIRS`(`app/web/asset_manifest.py:68`)에 `app/web/frontend` 가 이미 포함되어 매크로 임포트가 가능하다.

```text
app/web/frontend/components/kpi-card/
  macro.jinja
  index.ts        # 숫자 카운트업 (dashboard.js 의 .dash-kpi__value 동작 이관)
  styles.css      # 토큰만 참조 (FG-002)
  index.test.ts   # Vitest
```

매크로 시그니처:

```jinja
{% macro kpi_card(label, value, unit="", period="", note="", tone="", href="", estimated=false) %}
```

- `tone` 은 P1 의 9개 톤 축을 재사용한다. **"승인 대기" 카드만 `anomaly` 톤**을 받아 색이 분리된다 — 나머지 셋은 보고하는 숫자지만 이것은 행동을 요구하는 숫자다(상위 설계 §3.8).
- `estimated=true` 면 `[추정]` 배지가 붙고 `note` 가 근거 줄이 된다.
- `href` 가 있으면 카드 전체가 링크가 된다.

카운트업 로직을 `dashboard.js` 에서 옮기므로 그 파일(327줄)이 P3 이관 전에 미리 줄어든다.

### 3.8 정직성을 컴포넌트가 강제한다

상위 설계 §3.9 규율을 문서가 아니라 **불변식**으로 만든다.

- `build_daily_summary()` 가 `estimated=True` 인 항목에 대해 `note` 를 반드시 생성한다.
- `estimated and not note` 인 요약은 만들어질 수 없음을 테스트로 강제한다(§5).
- 실측(통과율·복구 건수·승인 대기)과 추정(절감 시간)을 시각적으로 구분한다 — 추정만 `[추정]` 배지를 갖는다.

**추정치 미설정 상태:** `ModuleSettings.estimated_manual_seconds` 가 설정되지 않아 `total_seconds == 0` 이면 카드는 `0h` 를 성과처럼 표시하지 않고 **"추정치 미설정"** 안내와 설정 화면 링크를 보여준다.

### 3.9 "승인 대기" 이동 경로

카드 클릭 → `/self-healing` 의 패치 목록으로 이동한다. `self_healing.html` 에 앵커(`id="patches"`)를 추가해 딥링크를 만든다.

이것이 상위 설계 §3.3 "자가 치유를 1급 시민으로"의 실질이다 — 경영진 데모에서 숫자를 누르면 곧바로 자동 생성된 diff 와 사람 승인 버튼이 나온다.

### 3.10 잃는 것 (정직한 비용)

| 사라지는 숫자 | 대체 |
| --- | --- |
| 이상징후 건수 | 히어로 메타 줄 + 주의선 + 매트릭스 색 |
| 점검실패 건수 | 히어로 제목 문장 |
| **진행 중 건수** | 매트릭스의 `running` 톤만 — **숫자로는 사라진다** |
| **미점검 건수** | 매트릭스의 `not_inspected` 톤만 — **숫자로는 사라진다** |

6시스템 규모라 매트릭스에서 세어지지만, 이것은 D1 이 치르는 실제 비용이다. 운영팀 피드백으로 되돌릴 수 있도록 기존 타일 마크업은 git 이력에 남긴다.

---

## 4. 목표 / 비목표

### 4.1 성공 기준

| 기준 | 측정 |
| --- | --- |
| 절감 시간 가시성 | **비관리자 계정**으로 `/` 에서 확인 가능 |
| 프라이버시 | `/api/dashboard/daily/summary` 응답에 사용자 식별자 0건 |
| 넌스크롤 불변식 | `test_dashboard_viewport.py` 통과 |
| 정직성 | 추정 항목에 `[추정]` 배지 + 근거 줄이 항상 존재 |
| 죽은 코드 | `build_daily_dashboard` 참조 0건 |
| 기간 명시 | KPI 4장 모두 기간 라벨 보유 |
| 날짜 경계 | healing '오늘'과 일간 `date_label` 이 동일 타임존 기준 |

### 4.2 비목표 (P3 이월)

- 상황판 `/wall`
- 메일 리포트 인라인 KPI
- Run 상세 라이브 (모듈 점등 · `recovered` 배지 강조)
- WS 실시간 KPI 갱신 — **P2 는 기존 htmx `dash-refresh` 갱신을 그대로 쓴다**
- 잔여 화면 이관 (`app.js` 소멸)
- **자동 화면 스모크 테스트** — P1 에서 한 번 이월된 항목. 인증 불필요 렌더 경로가 P2 에도 생기지 않아 다시 P3 으로 미룬다. 두 번 미뤘음을 기록해 둔다.

---

## 5. 검증

| 대상 | 방법 |
| --- | --- |
| `build_daily_summary()` 순수 조립 | pytest — totals·healing·savings 3입력 조합 |
| **응답에 사용자 식별자 부재** | pytest — 직렬화 결과에 `email`·`user_id`·`user_name` 키 없음 |
| `estimated ⇒ note` 불변식 | pytest |
| 비관리자 접근 | pytest — 일반 사용자 200, 사용자별 분해는 여전히 `require_admin` |
| 기간 라벨 | pytest — KPI 4장 모두 period 라벨 동봉 |
| 추정치 미설정 상태 | pytest — `total_seconds == 0` 이면 "추정치 미설정" 경로 |
| **날짜 경계** | pytest — KST 08:00(=UTC 전날 23:00) 시각을 고정해 healing '오늘' 버킷이 일간 `date_label` 과 같은 날인지 |
| 순수 함수 하위호환 | pytest — `day_label` 미전달 시 `build_healing_metrics` 가 기존 UTC 버킷을 그대로 반환 |
| 뷰포트 예산 | `test_dashboard_viewport.py` (프로젝션 빌더로 이관 + KPI 밴드 케이스 추가) |
| `KpiCard` 렌더 | Vitest — `estimated` 배지 · `tone` · 카운트업 |

P1 이 배선한 게이트 6종(`frontend_gates` · `frontend_tokens` · `typecheck_web` · `eslint_web` · `build_web` · `vitest_web`)이 신규 컴포넌트에 자동 적용된다. **P2 는 새 게이트를 추가하지 않는다.**

---

## 6. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| 레거시 빌더 제거 비중 | 테스트 4파일 이관이 P2 작업량의 절반을 차지할 수 있다 | 먼저 수행하고 독립 커밋. KPI 작업과 분리 |
| 카드 높이 초과 | `note` 줄 때문에 기존 타일보다 높아져 뷰포트 예산을 넘길 수 있다 | 카드 높이 상한을 토큰으로 고정, `note` 1줄 말줄임. 뷰포트 테스트가 게이트 |
| 진행 중·미점검 숫자 상실 | §3.10 — 실제 비용 | 수용. 운영팀 피드백 시 되돌릴 수 있도록 이력 보존 |
| 절감 시간은 끝까지 추정치 | 정직 표기가 임팩트를 깎는다 | 의도된 절충. 신뢰가 임팩트보다 오래간다 |
| 타임존 인자 추가 | `build_healing_metrics` 시그니처가 넓어진다 | 기본값이 현행 동작이라 기존 호출자 무영향. 대안(요약 쪽에서 재버킷팅)은 버킷팅 구현을 이중화한다 |
| `my_seconds` 의 부작용 | 본인 기여분 노출이 은근한 실적 경쟁을 만들 수 있다 | 순위·비교를 표시하지 않는다. 본인 수치만, 등수 없이 |

---

## 7. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md`
- P1 계획: `docs/superpowers/plans/2026-08-19-frontend-elevation-p1.md`
- 넌스크롤 불변식: `docs/superpowers/plans/2026-08-15-viewport-fit-no-scroll.md`, `2026-08-15-dashboard-zone-c-fit-p1.md`
- CI 게이트 SSOT: `scripts/ci/gates.py`, `docs/CI.md`
