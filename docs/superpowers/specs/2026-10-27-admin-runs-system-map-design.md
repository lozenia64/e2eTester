# 관리자 Run 이력 — 시스템 지도 리뉴얼 — Design

| 항목 | 값 |
| --- | --- |
| 화면 | `/admin/runs` (관리자 > Run 이력) |
| 대상 AC Spec | `docs/specs/insights/03-admin-stats.md` §2 Run 보드 |
| 상태 | draft |

## 1. 의도

회사 임원이 업무 중 **하루 한 번, 각자 노트북으로** 이 화면에 들어온다. 오래 머물지 않는다.
그래서 들어온 순간의 첫 3초가 전부다 — "오!" 하고 감탄이 나오는 연출로, 닫고 나갈 때 두 가지가 머리에 남아야 한다(사용자 결정).

1. 이번 달 **가장 많이 실행된 시스템**은 어디인가
2. 이번 달 **이상징후가 가장 많이 발생한 시스템**은 어디인가

지금 화면에는 이 두 질문에 바로 답하는 요소가 없다. KPI 5칸은 전체·오늘 건수뿐이고, 나머지 상단 요소 상당수는 관리자 대시보드(`/admin`)와 중복된다.

## 2. 목표 / 비목표 / 반목표

**목표**
- 화면 최상단을 **시스템 지도(트리맵)** 한 장으로 바꿔 두 질문에 동시에 답한다(사용자 결정: 시안 C).
- 관리자 대시보드와 중복되는 영역을 **삭제**한다(사용자 결정).
- 시스템 지도에만 강한 진입 연출. 나머지 영역은 차분하게 등장(사용자 결정).

**비목표**
- 탐색(필터·저장 뷰·CSV·카드·드로어) 기능 변경.
- 실행자×시스템 히트맵 내용 변경.
- `admin-runs.js` 의 TS 승격(별도 사이클 몫).

**반목표** — 동작해도 실패로 본다
- 연출이 계속 반복되거나 30초 갱신마다 다시 튀어나와 산만한 것.
- 숫자가 대시보드의 같은 이름 숫자와 다른 의미로 읽히는 것(아래 §4.1 정의를 화면에 명시).
- 동작 줄이기 설정 사용자에게 모션이 나가는 것.

## 3. 화면 구성 (위→아래)

| # | 영역 | 처리 |
|---|------|------|
| 1 | 헤더 (Run 이력 제목·갱신시각) | 유지 |
| 2 | **시스템 지도 · 이번 달** | **신규** — 기존 KPI 5칸 자리 |
| 3 | 실행자×시스템 히트맵 | 유지, 진입 시 페이드업 |
| 4 | 탐색 | 유지, 카드 순차 페이드 |

**삭제** (대시보드 중복, 사용자 결정):
- KPI 5칸 → 대시보드 '이번 달 집계 실행'·'오늘 확인할 모듈'과 중복
- 주의 필요 Top 5 → 대시보드 '오늘 확인할 모듈'과 중복
- 시스템별 최근 결과 → 대시보드 '오늘의 시스템별 점검 결과'와 중복
- 최근 7일 완료 추이 → 대시보드 7일 커버리지와 같은 질문에 답함 *(내 판단, 사용자 미반대)*

## 4. 시스템 지도

### 4.1 데이터 정의

- **기간**: 이번 달 — `Asia/Seoul` 월초 00:00부터 조회 시각까지, `requested_at` 귀속(사용자 결정: "이번 달"). 월초 계산은 `admin_performance.performance_periods()` 를 재사용한다.
- **실행 횟수**: 기간 내 `ADMIN_VISIBLE_RUN_STATUSES`(정상·이상징후) Run 수. *(내 판단)* `run_retention.py` 가 매일 전날 이전 ERROR·CANCELLED 를 지우므로(`RUN_DAILY_PURGE_STATUSES`) 이 둘을 넣으면 월간 수치가 오늘 것만 섞인 잡음이 된다. 사용량 통계와 같은 집합이라 대시보드 수치와도 가깝다.
- **이상징후 건수**: `ANOMALY` + `FAILED` — 기존 KPI `today_anomaly` 와 같은 정의.
- **이상징후 비율**: 이상징후 건수 / 실행 횟수.
- 패널 부제: "정상·이상징후 Run 기준 · 이번 달 1일~지금".
- 시스템명은 `system_code` 로 묶고 이름은 기간 내 가장 최근 행의 `system_name`(없으면 `system_code`)을 쓴다 *(계획 단계 조정: `RunQueries` 에 레지스트리 의존을 새로 넣지 않기 위함)* — 과거 이름 변경으로 한 시스템이 두 타일로 쪼개지지 않게.

### 4.2 API

`GET /api/admin/runs/board` 응답을 다음으로 **교체**한다(필드 삭제 포함).

```json
{
  "generated_at": "...", "timezone": "Asia/Seoul", "today_start": "...",
  "system_map": {
    "period": {"from": "...", "to": "..."},
    "systems": [
      {"system_code": "hom", "system_name": "대표홈페이지", "runs": 1284, "anomaly": 12}
    ],
    "top_runs": "hom",
    "top_anomaly": "chbot"
  }
}
```

- `today_start` 는 탐색의 '오늘' 기간 필터가 쓰므로 유지.
- `kpis`·`trend_7d`·`attention_runs`·`by_system_recent` 는 삭제. 이를 위해서만 존재하던 코드(`build_trend_7d`, `merge_daily_status_counts`, `build_by_system_recent`, `summarize_attention_row`, `BoardRunRow`/`_board_row`, `list_summaries_for_last_finished_by_system` 의 board 호출, `list_comparisons` 의 board 호출)는 다른 호출자가 없으면 함께 지운다. 구현 전 `grep` 으로 호출자를 확인한다.
- `systems` 는 `runs` 내림차순. 이번 달 실행 0회인 등록 시스템은 포함하지 않는다.
- `top_runs`/`top_anomaly`: 동률이면 `system_code` 오름차순 첫 번째. 이상징후가 전부 0이면 `top_anomaly` 는 `null`.
- 집계: `RunSummaryQueryPort` 에 `counts_by_system_status(query) -> list[(system_code, system_name, status, count)]` 를 추가(코드 단위로 묶고 이름은 최신 행, InMemory 동등 구현). 이름 해석은 §4.1. 빌더는 `admin_run_history_board.py` 의 순수 함수로 둔다.

### 4.3 시각

- ECharts `treemap` 시리즈 (이미 페이지에 로드된 `vendor-echarts`). 새 의존성 없음.
- 타일 면적 = `runs`, 색 = 이번 달 이상징후 누적 건수. 0건 초록 → 1건 연노랑 → 3건 노랑 → 5건 주황 → 10건 이상 빨강으로 기준점 사이를 선형 보간한다. 비율은 타일·툴팁에 숫자로 유지한다. (2026-10-29 변경)
- 타일 라벨: 시스템명, 실행 횟수, "이상징후 N건 · R%".
- `top_anomaly` 타일: 이름 뒤 🔥, 흰 테두리. `top_runs` 타일: 🏆.
- 어두운 남색 그라데이션 패널(시안 C) — 화면에서 이 패널만 어둡게 해서 시선이 먼저 가게 한다.
- 하단 한 줄 요약: "이번 달 가장 많이 돈 건 **X**(N회), 이상징후가 가장 많은 건 **Y**(M건)입니다." 조사 문제를 피하려고 시스템명 뒤에 조사를 직접 붙이지 않는다(#167의 교훈). `top_anomaly` 가 null이면 "이번 달 이상징후는 아직 없습니다."
- 빈 상태(이번 달 실행 0): 패널 안에 "이번 달 완료된 Run이 아직 없습니다."
- 타일 클릭 → 탐색 필터를 **시스템 = 그 시스템, 상태 = 정상·이상징후, 기간 = 고급 필터 from/to 를 `system_map.period`** 로 채우고 탐색 섹션으로 스크롤. 목록 건수가 타일 숫자와 일치해야 한다. *(내 판단 — 기존 고급 필터 입력만 채우고 '이번 달' 프리셋은 새로 만들지 않는다)*
- 접근성: 차트 컨테이너에 `role="img"` + 요약 문장과 같은 `aria-label`. 요약 문장 자체가 텍스트 대안이다.
- 모바일 폭: 트리맵 높이 고정(약 260px), 가로 스크롤 없음.

### 4.4 연출

첫 성공 로드에서 **한 번만**, 2초 안에 끝난다.

1. 패널 페이드업 (0~0.4s)
2. 트리맵 타일 확대 등장 — ECharts `animationDuration`/`animationEasing: "elasticOut"`, 타일별 `animationDelay` 로 순차 (0.2~1.2s)
3. 타일·요약의 숫자 카운트업 0→값, ease-out (0.4~1.8s)
4. 🔥 타일 테두리 맥박 3회 후 정지 (1.5s~)
5. 요약 문장 페이드인 (1.6s)

- 히트맵·탐색: 페이드업 1회(300ms, 순차 80ms)만.
- 30초 갱신(`silent`)에서는 애니메이션 없이 값만 반영(`animation: false` 로 `setOption`).
- `prefers-reduced-motion: reduce` 이면 모든 연출 생략, 최종 상태 즉시 표시.

## 5. 제약

- 변경은 `app/web/templates/admin/runs.html`, `app/web/static/admin-runs.js`, 위 백엔드 파일, 테스트, AC Spec에 한정. `admin-runs.js` 는 레거시 정적 JS 그대로 수정한다(TS 승격 비목표).
- 차트 라이브러리 추가 금지. 추이 차트 삭제로 이 페이지에서 Chart.js를 더 쓰지 않으면 `vendor-chart.ts` 스크립트 태그도 제거한다.
- UI 문자열 한국어. 정적 JS 캐시 버전(`admin-runs.js?v=`) 올린다.
- `docs/specs/insights/03-admin-stats.md` §2 를 새 board 응답으로 갱신. 아키텍처 문서에 board 설명이 있으면 동기화.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full`.

## 6. 테스트

- 빌더 단위: 기간 경계(월초 직전/직후), ANOMALY+FAILED 합산, 동률 처리, 이상징후 0 → `top_anomaly` null, 실행 0 시스템 제외.
- 쿼리: SQLite `counts_by_system_status` 가 필터(상태·`requested_since`)를 존중.
- HTTP: board 응답에 `system_map`·`today_start` 존재, 삭제 필드 부재.
- 기존 `test_admin_runs_api.py`·`test_admin_runs_http.py`·`test_admin_run_history_board.py` 의 KPI/추이/주의 단언은 새 계약으로 교체.
- 수동: 실제 데이터로 `/admin/runs` 진입 → 연출 1회, 갱신 시 무연출, 타일 클릭 후 목록 건수 = 타일 숫자, 동작 줄이기 설정 확인.

## 7. 빌더 재량

- 트리맵 세부 스타일(라벨 폰트·간격·툴팁 문구).
- 카운트업을 ECharts 라벨 포매터로 할지 DOM 오버레이로 할지.
- 빈 시스템 영역을 지울 때 남는 CSS 정리 범위.
