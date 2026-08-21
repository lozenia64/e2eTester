# 프론트엔드 고도화 P3-3 (일간 리포트 메일) — Design

**작성일:** 2026-08-21
**상태:** 초안 (사용자 리뷰 대기)
**상위 설계:** `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§4 Step 6)
**선행:** P1 기반 · P2 일간 현황 (둘 다 `main` 병합 완료). **P3-2 에 의존하지 않는다** — 이 브랜치는 `origin/main` 기준이다
**대상:** `app/notifications/report_renderer.py`, `app/notifications/daily_report.py`(신규), `app/contexts/scheduling/daily_report_scheduler.py`(신규), `app/contexts/scheduling/composition.py`, `app/orchestrator/queries/daily_queries.py`, `app/orchestrator/queries/daily_summary_queries.py`, `app/core/settings.py`, `docs/INSTALL.md`, `.env.example`

---

## 1. 문제

### 1.1 상위 설계의 사실오류 정정 (두 번째)

상위 설계 §4 는 Step 6 을 *"메일 리포트 — 같은 KPI 를 메일 인라인으로"* 라고 적었다. **실제와 다르다.**

`app/notifications/` 에는 개별 Run/Suite **완료 메일**만 있다. `report_renderer.py` 의 공개 함수는 `render_run_report_html`(599행)과 `render_suite_report_html`(738행) 둘뿐이며, **일간·주간 리포트가 존재하지 않는다.** 따라서 Step 6 은 "재스타일링"이 아니라 **생성기와 예약 발송을 새로 만드는 신규 기능**이다.

이 오류는 P3-1 스펙 §0 에서 이미 지적했고 여기서 확정한다.

### 1.2 있는 것 — 재사용 가능한 인프라

| 자산 | 위치 | 재사용 |
| --- | --- | --- |
| SMTP 발송 (Gmail · 재시도 분류 · 중복 방어) | `run_completion_email.py` (1,759줄) | 발송 경로 |
| 메일 HTML 렌더러 (Outlook 대응 인라인 스타일) | `report_renderer.py` (930줄) — `_shell`(125) · `_title_block`(153) · `_section`(167) · `_kpi_cards`(175) · `_status_badge`(141) · `_footer`(590) | 렌더 헬퍼 |
| **일일 배치 선례** | `app/contexts/scheduling/run_retention.py` — `parse_cron` + 틱 루프 + `from_env`(63) + `composition.py:40` 배선 | 스케줄 구조 |
| **범용 중복 방어** | `sqlite_email_notification_dedup.py:34` `try_claim_sync(scope, entity_id)` | 하루 한 통 보장 |
| 일간 집계 | P2 의 `DailySummaryQueries.get_daily_summary()` | 리포트 데이터 전량 |

**신규 인프라가 거의 필요 없다.** 조립과 배선이 대부분이다.

### 1.3 근본 제약 — 일간 쿼리가 "오늘"에 고정되어 있다

`DailyStatusQueryPort.list_for_date(date_label, ...)`(`app/contexts/insights/infrastructure/ports.py:46`)는 **이미 임의 날짜를 받는다.** 오늘로 고정하는 것은 `DailyDashboardQueries.get_daily_dashboard()` 하나뿐이며, 내부에서 `schedule_today_label()` 을 호출한다.

리포트는 어제를 보고해야 하므로(§2 D1) 이 한 곳을 파라미터화해야 한다.

### 1.4 메일 상태 색의 커버리지 누락

`report_renderer.py:68` `_STATUS_COLORS` 는 손으로 유지하는 19줄 매핑이다. 라벨(`_STATUS_LABELS`, 62행)은 `status_labels.py` 에서 파생되지만 **색은 독립 팔레트**다.

실측한 결과, 색 **값**의 차이는 대체로 같은 의도의 다른 명도였다(메일 `_status_color` 는 텍스트 강조색이므로 웹의 `--st-*-text` 와 짝이 맞는다):

| 상태 | 메일 | 웹 `-text` | 판정 |
| --- | --- | --- | --- |
| `PASSED` | `#2f8f4e` | `#047857` | 같은 계열, 값 차이 |
| `ANOMALY` | `#b7791f` | `#b45309` | 거의 같음 |
| `ERROR` | `#c0392b` | `#b91c1c` | 거의 같음 |
| `RUNNING` | **`#6b7280`(중립 회색)** | `#1d4ed8`(파랑) | **커버리지 누락** |

`RUNNING` 은 `_STATUS_COLORS` 에 **아예 없어서** 기본값인 `NEUTRAL_COLOR` 로 떨어진다.

전수 검사한 결과 누락은 정확히 **`PENDING` · `QUEUED` · `RUNNING` 3개**다. `_STATUS_COLORS` 는 enum 이 아니라 **문자열 값**으로 키가 잡혀 있어(`ModuleStatus.WAITING_INPUT.value == "WAITING_INPUT"`), 한 번 등록된 값은 세 enum 을 모두 덮는다 — 키 8개로 전체를 커버하는 구조다.

**이것은 `run.html:6` 의 `status_pill` 이 `anomaly`·`error` 키를 빠뜨렸던 것과 같은 병이다** — 맵을 손으로 유지하는데 전수 검사가 없다.

---

## 2. 결정

| # | 결정 | 이유 |
| --- | --- | --- |
| D1 | **보고 기준일은 어제** (스케줄 타임존 전날 00:00~24:00) | 상위 설계 §3.2 의 리포트 장면이 "어제 어디가 문제였나"다. "오늘"을 보고하면 발송 시각에 점검이 안 끝나 빈 리포트가 나간다 |
| D2 | **전사 단일 리포트.** 신규 env `E2E_EMAIL_DAILY_REPORT_RECIPIENTS` | 기존 `E2E_EMAIL_RECIPIENTS_{코드}` 는 시스템별 담당 부서용 Run 완료 메일 경로다. 리포트 장면은 경영진·전사용이라 성격이 다르고, 전사 그림을 보는 사람이 있어야 목적을 달성한다 |
| D3 | **기능 스위치 기본 `false`** | 메일은 사람 받은편지함으로 나가는 되돌릴 수 없는 부수효과다. `E2E_WALL_ENABLED` 를 `true` 로 둔 것과 반대 판단인데, 상황판은 안 켜면 "안 보이는" 것이고 메일은 켜면 "잘못 나가는" 것이라 실패 방향이 다르다 |
| D4 | **렌더러를 `report_renderer.py` 같은 모듈에 추가** | `_shell`·`_title_block`·`_section`·`_kpi_cards`·`_footer` 를 새 모듈에서 임포트하면 비공개 경계를 깬다. 파일이 930 → 약 1,050줄이 되지만 FG-004(400줄)는 프론트엔드 전용이고 파이썬엔 크기 게이트가 없다 |
| D5 | **메일 색은 커버리지 누락만 메우고 값은 바꾸지 않는다** | 값 차이는 같은 의도의 다른 명도이고(§1.4), 통일하면 사람들이 익숙한 메일 색이 바뀐다. 팔레트 통일은 Step 7 로 |
| D6 | **링크를 넣지 않는다 — 자족적 메일** | 기존 Run 완료 메일에 링크가 하나도 없고 공개 URL env 자체가 없다. 링크를 넣으려면 새 base URL env + "대시보드는 로그인이 필요하다"는 문제를 함께 풀어야 한다 |

---

## 3. 설계

### 3.1 날짜 파라미터화 — 가산적 변경

```python
# app/orchestrator/queries/daily_queries.py
async def get_daily_dashboard(
    self, *, allowed_system_codes=None,
    date_label: str | None = None,   # 신규. None 이면 오늘(기존 동작)
) -> dict

# app/orchestrator/queries/daily_summary_queries.py
async def get_daily_summary(
    self, *, user_id, allowed_system_codes, is_admin=False,
    date_label: str | None = None,   # 신규. 그대로 전달
) -> dict
```

**기본값이 현행 동작이므로 일간 현황·상황판은 영향받지 않는다.**

어제 라벨은 `app/core/schedule_time.py:30` `schedule_day_label(now - 1일)` 로 만든다 — 이미 있는 순수 유틸이다.

**주의:** `get_daily_dashboard` 는 `schedule_today_start_utc()` 로 당일 Run 요약도 조회한다. `date_label` 을 넘길 때는 그 날의 00:00(스케줄 타임존)을 UTC 로 환산한 값을 함께 써야 한다. 이 계산을 `schedule_day_start_utc(date_label)` 로 `scheduler.py` 에 추가한다(`schedule_today_start_utc` 와 동형).

### 3.2 리포트 내용 조립 — 순수 함수

`app/notifications/daily_report.py`(신규):

```python
def build_daily_report(summary: dict[str, Any], *, date_label: str) -> dict[str, Any]
# → {"headline": str, "tone": str, "kpis": [...], "systems": [...], "issues": [...],
#    "date_label": str}
```

I/O 없음. `build_daily_summary`·`build_wall_view` 와 같은 순수 빌더 패턴이다.

데이터는 **P2 의 `get_daily_summary(date_label=어제)` 하나로 전량 나온다** — `cards`·`totals`·`systems`·`attention` 이 그대로 대응한다. **신규 쿼리 0건.**

### 3.3 제목 규칙 — 상황판과 다르다

상황판(P3-2)은 `waiting_input` 을 최우선으로 두었으나 **리포트는 아니다.** 발송 시각(다음 날 아침)에는 어제의 OTP 대기가 이미 끝났거나 무의미하다. 하루가 닫힌 뒤의 결론만 담는다.

| 순위 | 조건 | 제목 | 톤 |
| --- | --- | --- | --- |
| 1 | `totals.error > 0` | 점검실패 N건 | `error` |
| 2 | `totals.anomaly > 0` | 이상징후 N건 | `anomaly` |
| 3 | `totals.not_inspected == totals.modules` | 점검 미실행 | `pending` |
| 4 | 그 외 | 정상 | `passed` |

**라벨은 `app/core/status_labels.py` 에서 가져온다.** P3-2 구현에서 파이썬에 한국어 라벨을 하드코딩했다가 지적받은 것과 같은 실수를 반복하지 않는다 — `module_status_label(ModuleStatus.ERROR)` 로 "점검실패"를 받는다.

### 3.4 렌더 — 기존 헬퍼 재사용

`report_renderer.py` 에 `render_daily_report_html(context: dict) -> str` 을 추가한다.

| 구역 | 수단 |
| --- | --- |
| 셸(Outlook 대응) | `_shell` 재사용 |
| 제목 | `_title_block` 재사용 |
| KPI 4개 | `_kpi_cards` 재사용 |
| 시스템별 표 | **신규** `_system_summary_table` |
| 이상 건 목록 | `_section` + 기존 목록 스타일 |
| 푸터 | `_footer` 재사용 |

```text
제목      [E2E] 8월 20일 점검 결과 — 점검실패 2건
KPI       통과율 94%  ·  스스로 복구 7건  ·  승인 대기 2건  ·  이번 달 절감 310h
시스템표   HOM  6/6 정상    MHM  5/5 정상    FP  4/6 이상징후 2
          HRP  7/7 정상    HWTC 6/6 정상    CHBOT 6/6 정상
이상 목록  · FP · 위촉서류 첨부 — 점검실패 · 09:08
          · HOM · 로그인 — 이상징후 · 08:51
```

### 3.5 발송 — `RunRetentionScheduler` 패턴 재사용

`app/contexts/scheduling/daily_report_scheduler.py`(신규)는 `run_retention.py` 와 동형이다: `parse_cron` + 틱 루프 + `from_env`(설정이 꺼져 있으면 `None` 반환) + `composition.py` 배선.

| env | 기본값 | 용도 |
| --- | --- | --- |
| `E2E_EMAIL_DAILY_REPORT_ENABLED` | **`false`** | 기능 스위치 (D3) |
| `E2E_EMAIL_DAILY_REPORT_CRON` | `0 8 * * *` | 발송 시각 (스케줄 타임존) |
| `E2E_EMAIL_DAILY_REPORT_RECIPIENTS` | (없음) | 파이프 구분 수신자. 비어 있으면 발송하지 않는다 |

`E2E_EMAIL_ENABLED` 와 SMTP 자격증명은 기존 것을 그대로 쓴다.

### 3.6 하루 한 통 보장

`SqliteEmailNotificationDedupStore.try_claim_sync(scope, entity_id)`(34행)가 범용이다. `try_claim("daily_report", "2026-08-20")` 으로 claim 한다 — **신규 테이블·인프라 0건.**

프로세스가 여럿이어도(API + 워커) SQLite claim 이 최종 관문이다. 재기동으로 cron 이 같은 분에 두 번 맞아도 두 번째는 claim 실패로 조용히 넘어간다.

### 3.7 실패 시 — 하루를 건너뛴다

SMTP 실패는 기존 `_is_retryable` 분류(`run_completion_email.py:294`)를 재사용한다.

- **일시적 오류**(연결·타임아웃): 기존 재시도 정책을 따른다
- **재시도 불가 오류**(인증 실패·수신자 거부): **claim 을 해제하지 않는다.** 같은 날 계속 실패 메일을 시도하는 것보다 하루를 건너뛰고 구조적 로그를 남기는 편이 낫다. 다음 날 다시 시도된다

### 3.8 커버리지 누락 수정 (D5)

`_STATUS_COLORS` 에 빠진 항목을 추가한다. **기존 값은 바꾸지 않는다.**

맵은 문자열 값으로 키가 잡히므로 값 하나를 등록하면 세 enum 이 모두 덮인다. 전수 검사로 확인한 누락은 **3개뿐**이다.

| 값 | 현재 | 수정 후 | 근거 |
| --- | --- | --- | --- |
| `RUNNING` | 없음 → `NEUTRAL_COLOR`(회색) | **`INFO_COLOR`** (`#2563eb`) | 진행 중은 중립이 아니다. 웹 토큰도 파랑(`--st-running-text: #1d4ed8`)이다 |
| `PENDING` | 없음 → `NEUTRAL_COLOR` | `NEUTRAL_COLOR` (**명시**) | 중립이 맞지만 우연이 아니라 의도로 남긴다 |
| `QUEUED` | 없음 → `NEUTRAL_COLOR` | `NEUTRAL_COLOR` (**명시**) | 동일 |

`WAITING_INPUT`·`BLOCKED`·`SKIPPED`·`CANCELLED`·`FAILED` 는 **이미 등록돼 있다** — 브레인스토밍 중 내가 "Module 항목만 있고 Run/Suite 것이 없다"고 말했으나 문자열 키 구조를 오해한 것이었다. 값은 그대로 둔다.

**재발 방지 테스트**: `ModuleStatus`·`RunStatus`·`SuiteStatus` 의 **모든** 값이 `_STATUS_COLORS` 에 명시적으로 존재하는지 전수 검사한다. 지금 `run.html` 과 `_STATUS_COLORS` 가 같은 병을 반복한 이유가 "손으로 유지하는 맵에 전수 검사가 없어서"다.

이 검사는 `PENDING` 처럼 중립색이 맞는 상태도 **명시**를 요구한다 — 기본값으로 흘러내려 우연히 맞는 것과 의도적으로 중립인 것을 구분하기 위해서다.

---

## 4. 목표 / 비목표

### 4.1 성공 기준

| 기준 | 측정 |
| --- | --- |
| 어제 데이터 | 리포트가 발송일 전날의 집계를 담는다 |
| 기존 경로 무영향 | `date_label` 미전달 시 일간 현황·상황판 동작 불변 |
| 기본 비활성 | `E2E_EMAIL_DAILY_REPORT_ENABLED` 미설정 시 스케줄러가 `None` |
| 수신자 없음 | `RECIPIENTS` 비어 있으면 발송하지 않는다 |
| 하루 한 통 | 같은 날짜로 두 번 호출해도 SMTP 는 한 번 |
| 제목 규칙 | 4경로(실패/이상/미실행/정상) 각각 올바른 제목·톤 |
| 라벨 SSOT | `daily_report.py` 에 한국어 상태 라벨 리터럴 0건 |
| 색 커버리지 | 3개 enum 의 모든 값이 `_STATUS_COLORS` 에 **명시** 존재 (기본값 흘러내림 0건). 수정 전 누락 3개(`PENDING`·`QUEUED`·`RUNNING`) |
| 링크 없음 | 렌더 결과에 `http://`·`https://` 0건(이미지 `cid:` 제외) |

### 4.2 비목표

| 항목 | 이유 |
| --- | --- |
| 주간 리포트 | 일간이 먼저 검증돼야 한다. 같은 구조를 주 단위로 넓히는 것은 이후 |
| 메일 팔레트 값 통일 | D5 — 커버리지만. Step 7 |
| 대시보드 링크 | D6 — 새 base URL env + 인증 문제를 함께 풀어야 한다. `/wall`(P3-2, 비인증)로 링크하면 풀리지만 이 브랜치가 P3-2 에 의존하게 된다 |
| 스크린샷 첨부 | 일간 리포트는 집계이지 개별 Run 증거가 아니다 |
| 메신저(Slack 등) | 상위 설계는 "메일·메신저"라 했으나 메신저 연동은 신규 인프라다. 메일만 |
| AI 요약 | Run 완료 메일의 Gemini 경로는 개별 실패 분석용이다. 일간 집계에 붙일 근거가 아직 없다 |

---

## 5. 검증

| 대상 | 방법 |
| --- | --- |
| `build_daily_report` 제목 4경로 | pytest — 순수 함수 |
| 라벨 SSOT | pytest — `daily_report.py` 소스에 한국어 상태 라벨 리터럴 0건 |
| `date_label` 파라미터화 | pytest — 미전달 시 오늘, 전달 시 그 날짜의 행만 조회 |
| 기존 경로 무영향 | 기존 `tests/test_daily_dashboard.py`·`test_daily_summary*.py` 통과 |
| 스케줄러 비활성 | pytest — `ENABLED=false` 면 `from_env` 가 `None` |
| 수신자 없음 | pytest — 빈 수신자면 발송 시도 없음 |
| 하루 한 통 | pytest — 같은 날짜 두 번 호출 시 SMTP 호출 1회 |
| 재시도 불가 오류 | pytest — claim 유지, 예외 전파 없음, 구조적 로그 |
| 색 커버리지 | pytest — 3개 enum 전수, 기본값 흘러내림 0건 |
| 링크 없음 | pytest — 렌더 HTML 에 외부 URL 0건 |
| 렌더 스모크 | pytest — 4경로 각각 예외 없이 HTML 생성, 제목·시스템 표 포함 |

**SMTP 는 스텁한다.** 실제 발송은 테스트하지 않는다 — `docs/CI.md` 의 "AI/메일(env 미설정)은 CI 밖" 방침과 일치한다.

---

## 6. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| **되돌릴 수 없는 부수효과** | 메일은 사람 받은편지함으로 나간다. 잘못 나가면 취소할 수 없다 | 기본 `false`(D3) + 수신자 비어 있으면 미발송 + 하루 한 통 claim. 운영 투입 전 `RECIPIENTS` 를 본인 주소로 두고 하루 관찰할 것을 `docs/INSTALL.md` 에 적는다 |
| `report_renderer.py` 비대화 | 930 → 약 1,050줄 | D4 — 비공개 헬퍼 경계를 깨는 것보다 낫다. 파일 분할은 Step 7 에서 메일 팔레트 통일과 함께 재검토 |
| `date_label` 이 두 쿼리에 퍼진다 | `get_daily_dashboard` 와 `get_daily_summary` 양쪽에 인자가 는다 | 가산적이고 기본값이 현행 동작이다. 대안(리포트 전용 쿼리 신설)은 집계 로직을 두 벌로 만든다 |
| 색 값 드리프트 잔존 | 커버리지만 메우므로 화면과 메일의 색 값 차이는 남는다 | D5 의 의도된 절충. §1.4 에 실측을 기록했고 Step 7 이 이어받는다 |
| 링크 없는 리포트 | 받은 사람이 상세를 보려면 직접 대시보드를 찾아가야 한다 | D6. P3-2 의 `/wall` 이 병합된 뒤 비인증 링크를 붙이는 것이 자연스러운 후속이다 |

---

## 7. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md`
- P3 분할: `docs/superpowers/specs/2026-08-20-frontend-elevation-p3-1-run-live-design.md` §0
- P2 요약 쿼리: `docs/superpowers/specs/2026-08-19-frontend-elevation-p2-design.md` §3.1
- 일일 배치 선례: `app/contexts/scheduling/run_retention.py`
- 메일 발송·중복 방어: `app/notifications/run_completion_email.py`, `app/notifications/infrastructure/sqlite_email_notification_dedup.py`
- CI 정책: `docs/CI.md`
