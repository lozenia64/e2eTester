# 관리자 Run 이력 시스템 지도 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/admin/runs` 상단을 '이번 달 시스템 지도'(ECharts 트리맵 + 한 줄 요약 + 1회 진입 연출)로 바꾸고, 관리자 대시보드와 중복되는 4개 영역과 그 백엔드 데이터를 삭제한다.

**Architecture:** `RunSummaryQueryPort` 에 시스템×상태 집계 메서드 하나를 추가하고, `admin_run_history_board.py` 의 순수 빌더가 `system_map` 페이로드를 만든다. `GET /api/admin/runs/board` 는 `system_map`·`today_start` 만 남는다. 프런트는 레거시 `admin-runs.js` 를 그대로 수정해 이미 로드된 전역 `echarts` 로 트리맵을 그린다.

**Tech Stack:** Python 3.13 / FastAPI / SQLite, Jinja2, 레거시 정적 JS, ECharts 6 (`vendor-echarts`).

**Spec:** `docs/superpowers/specs/2026-10-27-admin-runs-system-map-design.md`

## Global Constraints

- 기간: `Asia/Seoul` 월초 00:00 ~ 조회 시각, `requested_at` 귀속. 월초는 `admin_performance.performance_periods(now)[0]` 재사용.
- 실행 횟수 상태 집합: `ADMIN_VISIBLE_RUN_STATUSES` (PASSED, ANOMALY, FAILED). 이상징후 = ANOMALY + FAILED.
- 새 의존성·차트 라이브러리 금지. UI 문자열 한국어.
- 색 경계 상수: 0% `#10b981` → 5% `#eab308` → 10%+ `#ef4444`, JS 상수 한 곳.
- 연출은 첫 성공 로드 1회, 2초 이내. `silent` 갱신·`prefers-reduced-motion: reduce` 는 무연출.
- 요약 문장은 시스템명 뒤에 조사를 붙이지 않는다.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full` (백그라운드).

## Review Focus

1. 이번 달 Run 0건(월초 새벽) → 빈 상태 문구, JS 예외 없음. → Task 2 빌더 테스트 + Task 3 수동 확인.
2. 이상징후 전부 0 → `top_anomaly` null, 요약 "이번 달 이상징후는 아직 없습니다." → Task 2.
3. 같은 `system_code` 에 과거 이름이 다른 행 → 타일 하나, 최신 이름. → Task 1 SQLite 테스트.
4. 30초 갱신 → 트리맵이 다시 튀어나오지 않음, 열린 드로어·필터 유지. → Task 3 수동 확인.
5. 타일 클릭 후 목록 총건수 = 타일 실행 횟수. → Task 3 수동 확인.

---

### Task 1: 시스템×상태 집계 쿼리

**Files:**
- Modify: `app/contexts/run/contracts/ports.py` (`RunSummaryQueryPort`)
- Modify: `app/contexts/run/infrastructure/sqlite_run_summary_query.py`
- Modify: `app/contexts/run/infrastructure/in_memory_run_summary_query.py`
- Test: `tests/test_admin_runs_api.py` (기존 `_seed`/`_run` 헬퍼 재사용)

**Interfaces:**
- Produces: `async def counts_by_system_status(self, query: RunSummaryFilter) -> list[tuple[str, str, str, int]]` — `(system_code, system_name, status_value, count)`. `system_name` 은 필터를 통과한 행 중 `requested_at` 최신 행의 이름, `None`/빈 값이면 `system_code`. 결과는 `(system_code, status_value)` 정렬.

- [ ] **Step 1: 실패 테스트 작성** — `test_counts_by_system_status_groups_by_code_with_latest_name`: hom PASSED 2건(과거 이름 "구 홈", 최신 이름 "대표홈페이지"), hom ANOMALY 1건, mhm PASSED 1건, hom ERROR 1건, 기간 밖 hom PASSED 1건을 시드. `RunSummaryFilter(statuses=ADMIN_VISIBLE_RUN_STATUSES, requested_since=<기간 시작>)` 로 호출하면
  `== [("hom","대표홈페이지","ANOMALY",1), ("hom","대표홈페이지","PASSED",2), ("mhm", <mhm 이름>, "PASSED", 1)]`.
- [ ] **Step 2: 실행해 실패 확인** — `pytest tests/test_admin_runs_api.py -k counts_by_system_status -v` → FAIL (AttributeError).
- [ ] **Step 3: 구현** — 포트에 시그니처 추가. SQLite는 `daily_status_counts` 와 같은 방식(`_where(query)` 로 `system_code, system_name, status, requested_at` 조회 후 파이썬 집계). InMemory는 `_matches` 로 동일 집계.
- [ ] **Step 4: 통과 확인** — 같은 명령 → PASS.
- [ ] **Step 5: 커밋** — `feat(runs): 시스템×상태 Run 집계 쿼리 추가`

### Task 2: board 페이로드를 system_map 으로 교체

**Files:**
- Modify: `app/contexts/insights/application/admin_run_history_board.py` (전면 축소)
- Modify: `app/orchestrator/queries/run_queries.py:245-299` 및 `_board_row`·관련 import
- Modify: `app/contexts/run/contracts/ports.py`, 두 어댑터 — `list_summaries_for_last_finished_by_system` 삭제(호출자는 board뿐임을 `grep` 으로 재확인. 남은 호출자가 있으면 삭제하지 않는다)
- Test: `tests/test_admin_run_history_board.py` (재작성), `tests/test_admin_runs_api.py:246-268, ~295-325`, `tests/test_admin_runs_http.py:56-72, 124-130`
- Docs: `docs/specs/insights/03-admin-stats.md` §2

**Interfaces:**
- Consumes: Task 1 `counts_by_system_status`.
- Produces (JSON, Task 3이 소비):
  ```json
  {"generated_at": "...", "timezone": "Asia/Seoul", "today_start": "...",
   "system_map": {"period": {"from": "...", "to": "..."},
                  "systems": [{"system_code": "hom", "system_name": "대표홈페이지", "runs": 3, "anomaly": 1}],
                  "top_runs": "hom", "top_anomaly": "hom"}}
  ```
- 순수 함수: `build_system_map(counts: list[tuple[str, str, str, int]], *, period_from: datetime, period_to: datetime) -> dict[str, Any]`, `build_admin_run_history_board(*, now: datetime, tz: ZoneInfo, today_start: datetime, system_map: dict[str, Any]) -> dict[str, Any]`.
- 삭제: `ATTENTION_STATUSES`, `DASHBOARD_TERMINAL`, `TrendStatus`, `BoardRunRow`, `_local_day_key`, `_window_day_keys`, `_status_to_trend_key`, `build_trend_7d`, `merge_daily_status_counts`, `build_by_system_recent`, `summarize_attention_row`, `_board_row`. 삭제 전 각 심볼을 `grep -rn` 해서 다른 호출자가 없는지 확인한다.

- [ ] **Step 1: 빌더 실패 테스트** (`tests/test_admin_run_history_board.py` 재작성)
  - `test_system_map_sums_anomaly_and_failed_and_sorts_by_runs`: counts `[("hom","대표홈페이지","PASSED",5),("hom","대표홈페이지","ANOMALY",1),("hom","대표홈페이지","FAILED",1),("chbot","챗봇","PASSED",2),("chbot","챗봇","ANOMALY",3)]` → `systems == [{"system_code":"hom","system_name":"대표홈페이지","runs":7,"anomaly":2}, {"system_code":"chbot","system_name":"챗봇","runs":5,"anomaly":3}]`, `top_runs == "hom"`, `top_anomaly == "chbot"`.
  - `test_system_map_tie_breaks_by_code`: 두 시스템 runs·anomaly 동률 → `top_runs`·`top_anomaly` 모두 `system_code` 오름차순 첫 번째.
  - `test_system_map_no_anomaly_gives_null`: anomaly 전부 0 → `top_anomaly is None`.
  - `test_system_map_empty`: `[]` → `systems == []`, `top_runs is None`, `top_anomaly is None`.
  - `test_board_payload_keys`: `set(board) == {"generated_at","timezone","today_start","system_map"}`.
- [ ] **Step 2: 실패 확인** — `pytest tests/test_admin_run_history_board.py -v` → FAIL (ImportError).
- [ ] **Step 3: 빌더 구현 및 레거시 심볼 삭제.**
- [ ] **Step 4: `RunQueries.get_admin_run_history_board` 교체** — `period_from = performance_periods(now)[0]`, `counts_by_system_status(RunSummaryFilter(statuses=ADMIN_VISIBLE_RUN_STATUSES, requested_since=period_from))`. `actor_context` 파라미터와 라우트 시그니처는 그대로 둔다(라우트 변경 최소화). 미사용 import 정리.
- [ ] **Step 5: 통합/HTTP 테스트 교체**
  - `tests/test_admin_runs_api.py` 의 board 테스트 → `test_get_admin_run_history_board_system_map_counts_this_month`: 이번 달 PASSED 1, ANOMALY 6, ERROR 1 시드 → `system_map["systems"][0]["runs"] == 7`, `["anomaly"] == 6`, `"kpis" not in board`.
  - `list_summaries_for_last_finished_by_system` 테스트 삭제.
  - `tests/test_admin_runs_http.py` 페이크 반환값을 새 형태로, `test_admin_runs_board_returns_system_map`: `body["system_map"]["systems"] == [...]`, `"today_start" in body`, `"trend_7d" not in body`.
- [ ] **Step 6: 통과 확인** — `pytest tests/test_admin_run_history_board.py tests/test_admin_runs_api.py tests/test_admin_runs_http.py -v` → PASS. 그리고 `pytest -q tests -k "admin or run_summary or runs"` 로 회귀 확인.
- [ ] **Step 7: AC Spec 갱신** — `03-admin-stats.md` §2 표의 board 행을 "이번 달 시스템 지도(`system_map`: 시스템별 정상·이상징후 Run 수, top_runs, top_anomaly)"로, 정의(기간·상태 집합·동률·null 규칙) 3~4줄 추가.
- [ ] **Step 8: 커밋** — `feat(admin-runs): board 를 이번 달 시스템 지도 집계로 교체`

### Task 3: 화면 — 시스템 지도 패널·연출, 중복 영역 삭제

**Files:**
- Modify: `app/web/templates/admin/runs.html` (KPI 그리드·추이·주의·시스템별 최근 결과 마크업과 그 전용 CSS 삭제, 시스템 지도 패널 추가, `vendor-chart.ts` 스크립트 태그 삭제, `admin-runs.js?v=` +1)
- Modify: `app/web/static/admin-runs.js`
- Modify: `tests/frontend/test_vendor_bundles.py:31` — `"admin/runs.html": ("entries/vendor-echarts.ts",)`
- Test: `tests/test_admin_runs_layout.py` (신규, 템플릿 계약)

**Interfaces:**
- Consumes: Task 2 JSON.
- DOM: `#runs-system-map` (패널), `#runs-system-map-chart` (`role="img"`), `#runs-system-map-summary`, `#runs-system-map-empty`, 탐색 섹션 앵커 `#runs-explore`.

- [ ] **Step 1: 템플릿 계약 실패 테스트** — `tests/test_admin_runs_layout.py::test_admin_runs_template_has_system_map_and_no_duplicates`: 템플릿 원문에 `id="runs-system-map-chart"`·`id="runs-system-map-summary"`·`id="runs-explore"` 포함, `runs-kpi-grid`·`runs-trend-canvas`·`runs-attention-list`·`runs-system-recent`·`vendor-chart.ts` 미포함. 그리고 `admin-runs.js` 원문에 `renderKpis`·`renderTrend`·`renderAttention`·`renderSystemRecent`·`boardRunStub` 미포함, `treemap` 포함.
- [ ] **Step 2: 실패 확인** — `pytest tests/test_admin_runs_layout.py -v` → FAIL.
- [ ] **Step 3: 템플릿** — KPI 그리드 자리에 시안 C 패널(어두운 남색 그라데이션, 제목 "시스템 지도 · 이번 달", 부제 "정상·이상징후 Run 기준 · 이번 달 1일~지금", 범례 "정상 → 이상징후 多"). 차트 높이 데스크톱 약 320px·모바일 260px. 탐색 섹션에 `id="runs-explore"`. 히트맵·탐색에 진입 페이드업 클래스(300ms, 순차 80ms) + `@media (prefers-reduced-motion: reduce)` 에서 애니메이션 없음. 🔥 테두리 맥박은 ECharts 대신 CSS로 처리해도 된다.
- [ ] **Step 4: JS 삭제** — `renderKpis`, `trendSegHeight`, `renderTrendFallback`, `renderTrend`, `renderAttention`, `renderSystemRecent`, `boardRunStub`, `resolveRun` 의 attention/recent 분기, 두 클릭 리스너, `state.trendChart`.
- [ ] **Step 5: JS 추가** — `renderSystemMap(map, { animate })`:
  - 색 상수와 `anomalyColor(rate)` (0/0.05/0.10 경계 선형 보간).
  - `echarts.init(#runs-system-map-chart)` 로 `series: [{ type: "treemap", roam: false, nodeClick: false, breadcrumb: { show: false }, data: systems.map(s => ({ name, value: s.runs, itemStyle: { color: anomalyColor(s.anomaly / s.runs) }, systemCode })) }]`. 라벨: 이름(+ 🏆 `top_runs` / 🔥 `top_anomaly`), 실행 N회, "이상징후 N건 · R%".
  - `animate` 가 참이면 `animationDuration: 900, animationEasing: "elasticOut"`, 숫자 카운트업(요약 문장 숫자, 1.4s ease-out cubic). 거짓이거나 `matchMedia("(prefers-reduced-motion: reduce)").matches` 면 `animation: false`, 카운트업 생략.
  - 요약: `이번 달 가장 많이 돈 건 <b>X</b>(N회), 이상징후가 가장 많은 건 <b>Y</b>(M건)입니다.`, `top_anomaly` null → `이번 달 가장 많이 돈 건 <b>X</b>(N회)입니다. 이번 달 이상징후는 아직 없습니다.`. 같은 문장을 차트 `aria-label` 로.
  - `systems` 빈 배열 → 차트 숨기고 `#runs-system-map-empty` "이번 달 완료된 Run이 아직 없습니다." 표시.
  - 클릭(`chart.on("click")`): `applyFiltersToDom({ system_codes: [code], statuses: ["PASSED","ANOMALY"], from: map.period.from, to: map.period.to })` 후 기존 필터 적용 경로(`scheduleFilterLoad` 또는 그와 같은 로드 함수)를 호출하고 `#runs-explore` 로 `scrollIntoView({ behavior: reduced ? "auto" : "smooth" })`.
  - resize 리스너는 히트맵 패턴(`*ResizeBound` 플래그)을 따른다.
- [ ] **Step 6: `loadBoard`** — 기존 render 4개 호출 자리에 `renderSystemMap(state.board.system_map, { animate: !silent && !state.systemMapShown })` 를 넣고, 첫 렌더 후 `state.systemMapShown = true`.
- [ ] **Step 7: 통과 확인** — `pytest tests/test_admin_runs_layout.py tests/frontend tests/test_legacy_js_status_labels.py -v` → PASS (`npm run build` 가 필요하면 먼저 실행). `npm run lint` 는 TS 대상이므로 해당 없음.
- [ ] **Step 8: 수동 검증** — `.agents/skills/e2e-browser/SKILL.md` 를 따라 앱을 띄우고 `/admin/runs` 에 접속한다. Review Focus 1·4·5와 연출 1회·reduced-motion(DevTools 렌더링 에뮬레이션)을 확인하고 스크린샷을 남긴다.
- [ ] **Step 9: 커밋** — `feat(admin-runs): 이번 달 시스템 지도와 진입 연출, 대시보드 중복 영역 삭제`

### Task 4: 전체 게이트

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 을 백그라운드로 실행 → 전부 PASS. 실패하면 원인을 수정하고 해당 Task 커밋에 이어 커밋한다.
- [ ] 아키텍처 문서(`docs/E2E_ARCHITECTURE.md`)에 board 응답 설명이 있으면 동기화(현재 grep 상 없음 — 게이트의 문서 규칙이 요구할 때만).
