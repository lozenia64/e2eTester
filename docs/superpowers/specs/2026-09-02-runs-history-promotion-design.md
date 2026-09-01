# Run 이력 승격 (Runs History Promotion) — Design

**작성일:** 2026-09-02
**상태:** 초안 (사용자 리뷰 대기)
**대상:** `app/web/templates/runs_history.html`, `app/web/static/app.js`, `app/web/frontend/runs-history/`(신규), `app/api/routes_runs.py`, `app/orchestrator/queries/admin_dashboard_queries.py`, `app/web/frontend/styles/shell.css`

---

## 0. 요약

화면 격차 해소 프로그램의 **Cycle 4** — 여섯 사이클 중 네 번째다(`2026-08-24-execute-promotion-design.md` §2). 선례가 확정돼 있으므로 이 문서는 짧다. 화면 폴더 관례 · 넌스크롤 셸 · 승격 규격 5문항 · `bounding_box()` 좌표 계약은 앞 문서들을 참조하고 다시 쓰지 않는다.

이 화면의 사용 맥락은 **"어제·그제 점검이 잘 돌았나 확인"** 이고, 그중 **"빠진 것이 가장 중요"** 하다(둘 다 사용자 확인). 그런데 **현재 화면은 실행된 것만 그린다** — 안 돌아간 날은 화면에 존재하지 않는다. 목적을 정면으로 못 맞추고 있다.

그래서 이 사이클은 앞의 셋과 성격이 다르다.

| | Cycle 1~3 | Cycle 4 |
| --- | --- | --- |
| 성격 | 코드 이관 | **표현 교체** |
| `app.js` 처리 | 이관 | **약 40줄만 삭제**(§1.3) |
| 새 read model | 있음/없음 혼재 | **0개** — 관리자 커버리지 매트릭스를 재사용 |

지배 요소는 **시스템 × 7일 격자**이고, 빈칸이 곧 "안 돌았다"다.

이 사이클이 화면에 주는 변화는 크지만 `app.js` 에 주는 변화는 작다 — 이 화면이 쓰는 렌더 코드 대부분을 **점검 실행 화면이 함께 쓰고 있기 때문**이다(§1.3).

---

## 1. 문제

### 1.1 현재 화면은 없는 것을 보여주지 못한다

`runs_history.html` 은 18줄이고 실질 내용이 빈 `<div id="runs-history-list">` 하나다. 화면 전체를 `app.js` 의 `renderExecutionGroups` 가 그린다 — SUITE 와 하위 Run 을 한 줄로 잇는 "실행 그룹" 스트립이다.

이 표현은 **실행된 것을 잘 보여주지만 실행되지 않은 것은 그리지 않는다.** 예약이 안 돌았거나 PC 절전으로 건너뛴 날은 목록에서 그냥 빠지고, 사용자는 그것을 알 방법이 없다. "잘 돌았나 확인"이 목적인 화면에서 이것이 가장 큰 결함이다.

### 1.2 답이 이미 서버에 있는데 화면이 안 쓴다

`build_admin_coverage_dashboard`(`app/contexts/insights/application/admin_coverage_dashboard.py:140`)가 **시스템 × 21슬롯(7일 × 3시간대) 커버리지 매트릭스**를 이미 집계한다. `not_checked` 셀이 곧 "안 돌았다"이며, 이 화면이 필요로 하는 바로 그 정보다.

그런데 이것은 `/api/admin/dashboard`(`routes_admin.py:44`, `require_admin` 가드) 뒤에 있고, **임원·사용자는 `user` 역할이라 볼 수 없다.**

### 1.3 렌더 코드를 점검 실행 화면과 공유한다 — 삭제할 수 있는 것은 적다

`app.js:82~480` 399줄이 전부 이 화면의 것이라고 보면 틀린다. **실측한 소비자:**

| 덩어리 | 줄 | 소비자 | Cycle 4 |
| --- | --- | --- | --- |
| 스트립 8함수(`buildExecutionGroups` · `isExecutionGroupActive` · `runChipToneKey` · `createRunChip` · `createRunChipConnector` · `summarizeSuiteFromRuns` · `createSuiteStripRow` · `renderExecutionGroups`) | ~200 | **`execute.html:385`** + 이 화면 | **잔류** |
| `createRunListItem` | 85 | `renderExecutionGroups:385` 이 호출 | **잔류** |
| `bindRunsOverview` · `refreshRunList` · `renderRunList` | 51 | `execute.html` 전용 | **잔류** |
| `formatRunTimestamp` | 21 | 위 전부 + **예약**(`:697` · `:728` · `:741`) | **잔류**(지역 복제) |
| `bindRunsHistory` | 40 | **이 화면 전용** | **삭제** |

`execute.html:385` 의 `<div id="runs-list">` 는 "진행 중 / 최근 Run" 구획이고, `renderRunList`(`:397`)가 **같은 `renderExecutionGroups` 를 호출한다.** 즉 스트립 표현은 이 화면 고유물이 아니라 **점검 실행 화면과의 공유물**이다.

따라서 이 사이클이 `app.js` 에서 지울 수 있는 것은 `bindRunsHistory` 약 40줄뿐이고, **`app.js` 는 866 → 약 826줄**이 된다.

`formatRunTimestamp` 는 예약 코드가 계속 쓰므로 옮기지 못한다 — Cycle 2·3 선례대로 **지역 복제**한다(21줄, 중복 1건, Cycle 6 에서 소멸).

**남는 사실 하나:** Cycle 1 이 점검 실행 화면을 승격했지만 그 화면의 Run 목록 구획은 여전히 `app.js` 가 그린다. 이것을 `execute/` 폴더로 옮기는 일은 Cycle 6 의 몫으로 남긴다(§7).

### 1.4 상위 설계의 오류 — `app.js` 는 여기서 죽지 않는다

`2026-08-24-execute-promotion-design.md` §2 는 이렇게 적었다.

> | **4** | Run 이력 | `app.js` 약 640줄 | `app.js` **삭제** · `FG005_ALLOWLIST` 에서 제거 |

**실측은 다르다.** `app.js` 866줄의 구성:

| 구간 | 줄 | 소유 |
| --- | --- | --- |
| `:3~81` 공용 7함수 | 79 | 공용 (`showToast` · `setInlineFeedback` · `readErrorMessage` 등) |
| `:82~480` Run 이력 | 399 | **대부분 Cycle 6** — 40줄만 Cycle 4(§1.3) |
| `:481~866` 예약(cron 빌더) | 386 | **Cycle 6** |

예약 386줄이 남고, 그 소비자는 `schedules.html` 이 아니라 **`execute.html`** 이다 — 점검 실행 화면의 SUITE 카드 안에 cron 빌더가 있고(Cycle 1 D7 이 "Cycle 6 에서 판단"으로 남긴 그것), `__executeLegacy` 다리 3키가 그것을 위해 산다.

**Cycle 4 후 `app.js` 는 약 826줄로 남고**(§1.3), 소멸과 `FG005_ALLOWLIST` 비우기는 Cycle 6 의 몫이다.

---

## 2. 목표 / 비목표 / 성공 기준

### 2.1 목표

1. **안 돌아간 날·시스템이 화면에서 드러난다.**
2. 최근 7일을 **한눈에 훑을 수 있다** — 스크롤 없이.
3. 관리자 커버리지 read model 을 **사용자 권한으로 재사용**한다. 새 read model 0개.
4. 이 화면이 **`app.js` 를 더 이상 소비하지 않는다** — `bindRunsHistory` 약 40줄 삭제, `app.js` 866 → 약 826줄.
5. 점검 실행 화면(`execute.html`)의 Run 목록이 **지금 그대로 동작한다** — 공유 스트립 코드를 건드리지 않는다(§1.3).

### 2.2 비목표 (명시적 YAGNI)

- **실행 그룹 스트립 유지** — SUITE·하위 Run 을 한 줄로 잇던 표현은 버린다(D3). 드릴다운은 간단한 목록으로 대체한다.
- **실시간 소켓 신설** — 조회 전용 화면이다. 오늘 열은 페이지 로드 시점 상태를 보인다.
- **7일보다 긴 기간** — 커버리지 read model 의 창이 7일이다. 더 긴 조회가 필요하다고 확인되면 후속.
- **커버리지 페이로드에 `run_ids` 배열 추가** — D4 에서 기각한다.
- **`/api/admin/dashboard` 에 `user` 통과시키기** — D2 에서 기각한다.
- **`app.js` 소멸** — Cycle 6(§1.4).
- **관리자 화면(`/admin/runs`) 승격** — 이번 순서에 없다.

### 2.3 성공 기준

| 기준 | 측정 |
| --- | --- |
| 미실행 가시화 | 하루 3슬롯이 **모두** 빈 (시스템, 날짜) 칸이 `not_checked` 로 렌더된다. 부분 결측은 정상 톤을 유지한다(D6) |
| 넌스크롤 | 1366 · 1920 · 2560 px 에서 `body` 세로 스크롤 0 |
| 스크롤 소유권 | 내부 스크롤을 갖는 요소가 **드릴다운 하나** — 격자는 고정 |
| 권한 격리 | `allowed_system_codes` 밖 시스템이 사용자 응답에 없다. `/api/admin/dashboard` 는 여전히 `require_admin` |
| 삭제 | `app.js` 에 `bindRunsHistory` 0개 · `DOMContentLoaded` 에서 호출 제거 · 약 826줄 |
| 공유 코드 보존 | `app.js` 에 `renderExecutionGroups` · `createRunListItem` **유지**. `execute.html` 의 "진행 중 / 최근 Run" 이 회귀 없이 동작 |
| 이관 | `entries/runs-history.ts` 존재 · `runs_history.html` 이 `/static/app.js` 를 참조하지 않음 |
| 유틸리티 소거 | `runs_history.html` 에 Tailwind 색 유틸리티 0개 |
| 관리자 화면 불변 | `/admin` 커버리지 히트맵의 응답이 바뀌지 않는다 |

---

## 3. 설계

### 3.1 화면 — 시스템 × 7일 격자

```text
┌──────────────────────────────────────────────────────────────┐
│ Run 이력                     최근 7일                          │ 고정
├──────────────────────────────────────────────────────────────┤
│         8/27   8/28   8/29   8/30   8/31    9/1    9/2       │
│  HOM     ▉      ▉      ▉      ▉      ▉      ▉      ▨         │
│  MHM     ▉      ▉      ░      ▉      ▉      ▉      ▨         │ 격자(고정)
│  FP      ▉      ▩      ▉      ▉      ▉      ▉      ▨         │
│  HRP     ▉      ▉      ▉      ░      ▉      ▉      ░         │
│  HWTC    ▉      ▉      ▉      ▉      ▉      ▉      ▨         │
│  CHBOT   ▉      ▉      ▉      ▉      ▉      ▉      ▨         │
│                                                               │
│  ▉ 정상  ▩ 이상징후  ▤ 점검실패  ░ 미실행  ▨ 진행 중            │
├──────────────────────────────────────────────────────────────┤
│ 8/28 · FP                                          ← 선택된 셀 │
│  22:00  이상징후  모듈 2/3   서류 업로드에서 멈춤    Run 상세 → │ 드릴다운
│  09:00  정상      모듈 3/3                          Run 상세 → │ (내부 스크롤)
└──────────────────────────────────────────────────────────────┘
```

**빈칸(`░`)이 이 화면의 존재 이유다.** 목록 형태로는 표현할 수 없던 "없음"이 격자에서는 자리로 드러난다.

**하루 한 칸, 슬롯은 색 조각으로 보존한다**(사용자 결정). read model 은 하루를 3슬롯으로 주지만 화면은 한 칸으로 합친다. 하루 여러 번 돌면 칸 안이 조각으로 나뉜다.

**셀의 대표 톤은 두 단계로 정한다**(D6). 먼저 **하루 3슬롯이 모두 비었는지** 본다 — 비었으면 `not_checked`(빈칸)다. 하나라도 돌았으면 **돌아간 슬롯들 중 최악**을 따른다: `error > anomaly > running > passed`. 훑는 화면이므로 나쁜 것이 눈에 먼저 들어와야 한다.

이 2단계가 필요한 이유는 현 운영이 **시스템당 하루 1 Run** 이기 때문이다. `not_checked` 를 `passed` 와 같은 줄에 세워 최악을 고르면 3슬롯 중 2개가 늘 비어 있으므로 **정상인 날도 전부 미실행으로 보인다.** 부분 결측은 정상이고, 전부 결측만이 "안 돌았다"다.

**셸.** `body:has(.runs-history)` — `shell.css` 의 **다섯 번째 소비자**. 셀렉터 한 줄만 추가한다.

**넌스크롤 예산.** 격자는 최대 6행 × 7열로 크기가 고정이라 여유가 크다(앞 화면들과 달리 계산이 빡빡하지 않다). 시스템 수는 `allowed_system_codes` 로 1~6 사이에서 변한다.

**5문항 답**

| # | 답 |
| --- | --- |
| 1 지배 정보 | **시스템 × 7일 격자.** 빈칸이 가장 크게 말한다 |
| 2 스크롤 소유권 | 드릴다운 패널 하나. 격자는 고정 |
| 3 살아있음 | 없음(조회 전용). 오늘 열은 로드 시점 상태 |
| 4 추출 컴포넌트 | **신규 승격 0.** `status-badge` 재사용, 격자는 이 화면 전용 |
| 5 완료 신호 | `entries/runs-history.ts` 존재 · `app.js` 약 826줄 · `runs_history.html` 이 `app.js` 를 안 씀 |

### 3.2 데이터 경로 — 권한은 데이터 계층에서 건다

현재 구조:

```text
GET /api/admin/dashboard          require_admin
  └ AdminDashboardQueries.get_coverage_dashboard()
      ├ _list_summaries_since(since)      run_history_index 페이지네이션
      ├ self._registry.list_systems()     ← 전 시스템, 필터 없음
      └ build_admin_coverage_dashboard(systems, run_rows, now=now, tz=tz)
```

빌더는 깨끗하다 — `systems` 를 인자로 받고 관리자 개념이 안에 없다(`CoverageRunRow` 는 `run_id` · `system_code` · `status` · `requested_at` 4필드뿐). **권한 필터를 걸 자리는 쿼리 계층이다.**

**사용자용 엔드포인트를 새로 연다.**

```text
GET /api/runs/coverage            get_current_user
  └ get_coverage_dashboard(system_codes=current_user.allowed_system_codes)
```

`get_coverage_dashboard` 에 `system_codes: list[str] | None = None` 를 더한다. 주어지면 `list_systems()` 결과를 거르고 `run_rows` 도 그 코드로 좁힌다. **`/api/admin/dashboard` 는 인자 없이 호출하므로 응답이 그대로다**(성공 기준 "관리자 화면 불변").

경로를 `/api/runs/coverage` 로 둔 것은 이 화면이 Run 이력이기 때문이다. `/api/dashboard/*` 는 일간 대시보드의 것이라 섞지 않는다.

### 3.3 드릴다운 — 셀의 `run_id` 를 쓰지 않는다

`_cell_status`(`admin_coverage_dashboard.py:88`)는 슬롯 안 Run 목록을 **하나로 접는다.** 최신순 정렬 후 종료 상태인 첫 건을 대표로 뽑고 그 `run_id` 만 남긴다 — 나머지는 페이로드에서 사라진다.

따라서 커버리지 응답만으로 드릴다운을 만들면 하루 최대 3건(슬롯당 1건)만 보이고, **같은 슬롯에서 재실행한 Run 이 숨는다.** 실패 후 재실행해 통과한 경우 재실행 사실이 보이지 않는데, "잘 돌았나 확인"이 목적인 화면에서 그것은 오해를 만든다.

**셀 클릭 시 별도로 조회한다.**

```text
격자     : GET /api/runs/coverage                 페이지 로드 1회
드릴다운 : GET /api/runs?system_code=…&day=…      셀 클릭 시
```

기존 `/api/runs` 가 이미 `scope` · `limit` 필터를 받으므로 날짜·시스템 필터를 더하는 쪽이 새 엔드포인트를 또 만드는 것보다 낫다. **그 파라미터가 현재 있는지는 구현 계획에서 실측한다** — 없으면 추가가 필요하고 그만큼 서버 변경이 늘어난다.

**실패 처리:** 드릴다운 조회가 실패해도 격자는 살아 있어야 한다. 패널에 실패를 표시하고 격자는 건드리지 않는다.

### 3.4 이관 경계 — 삭제가 이관보다 크다

`app.js:82~480` 399줄의 운명:

소비자 실측(§1.3)이 결론을 뒤집었다. **삭제되는 것은 `bindRunsHistory` 40줄뿐이다.** 스트립 8함수와 `createRunListItem` 은 `execute.html` 이 쓰므로 잔류한다.

| 덩어리 | 줄 | 운명 |
| --- | --- | --- |
| `bindRunsHistory` | 40 | **삭제** — 격자가 대체(D3) |
| 스트립 8함수 · `createRunListItem` · `bindRunsOverview` · `refreshRunList` · `renderRunList` | ~336 | **잔류** — `execute.html` 소비(Cycle 6) |
| `formatRunTimestamp` | 21 | **잔류 + 지역 복제** — 예약이 계속 씀 |

D3 의 "폐기"는 **이 화면이 스트립을 더 이상 쓰지 않는다**는 뜻이지 코드 삭제가 아니다. 코드는 점검 실행 화면과 함께 Cycle 6 까지 산다.

`app/web/frontend/runs-history/`:

| 파일 | 내용 |
| --- | --- |
| `coverage.ts` | 격자 렌더 — 셀 톤·빈칸·슬롯 색 조각 |
| `drilldown.ts` | 선택 셀의 Run 목록 + 선택 상태 |
| `format.ts` | `formatRunTimestamp` 이관 |
| `styles.css` | 격자·드릴다운 CSS |
| `entries/runs-history.ts` | 배선만 |

**지역 복제 1건.** `bindRunsHistory` 실측 결과 `showToast` · `setInlineFeedback` · `readErrorMessage` 를 쓰지 않는다(조회 전용, 상태 문구만 갱신) — 공용 7함수 복제는 **0건**이다. 다만 `formatRunTimestamp` 는 예약 코드가 계속 쓰므로 옮기지 못하고 `format.ts` 로 **복제**한다(중복 1건, Cycle 6 소멸).

**`app.js` 866 → 약 826줄.**

---

## 4. 결정

| # | 결정 | 근거 |
| --- | --- | --- |
| **D1** | 지배 요소를 **시스템 × 7일 격자**로 바꾼다 | 사용자 결정. 목적이 "잘 돌았나 확인"이고 그중 "빠진 것이 가장 중요"한데, 현재의 목록 형태는 **없는 것을 그리지 못한다**(§1.1) |
| **D2** | 사용자용 엔드포인트를 **새로 열고** 권한 필터를 쿼리 계층에 건다 | `require_admin` 을 느슨하게 만들면 그 경로의 다른 응답까지 권한 판단이 흐려진다. 화면에서 거르는 것은 권한이 아니라 은닉이다. `run_execute`(`routes_dashboard.py:67`)가 이미 `allowed_system_codes` 로 거르는 같은 패턴이다 |
| **D3** | 이 화면은 실행 그룹 스트립을 **더 이상 쓰지 않고** 드릴다운은 간단한 목록으로. **단 코드는 삭제하지 않는다** | 사용자 결정(표현 교체). 격자가 최상위가 되면 스트립의 역할이 겹친다. 코드를 지울 수 없는 것은 `execute.html:385` 가 같은 함수를 쓰기 때문이다(§1.3) — 지우면 점검 실행 화면이 깨진다 |
| **D4** | 커버리지 페이로드에 `run_ids` 배열을 **추가하지 않는다.** 드릴다운은 별도 조회 | 접는 규칙(`_cell_status`)은 관리자 히트맵의 의도다. 사용자 화면 사정으로 그 페이로드를 부풀리면 7일×3슬롯×6시스템 = 126셀에 안 쓸 배열이 붙는다 |
| **D5** | 하루 한 칸, **슬롯은 색 조각으로 보존** | 사용자 결정. 현 운영은 시스템당 하루 1 Run 이라 3슬롯이 과하지만, 없앤 정보를 되살리려면 read model 을 다시 만들어야 한다. 시각적으로만 합친다 |
| **D6** | 셀 톤은 **2단계**로 정한다 — 하루 3슬롯이 **모두** 비면 `not_checked`, 하나라도 돌았으면 **돌아간 것들 중 최악**(`error > anomaly > running > passed`) | 단순 최악 규칙은 틀린다. 현 운영이 시스템당 하루 1 Run 이라 3슬롯 중 2개가 늘 비어 있어, `not_checked` 를 최악 후보에 넣으면 **정상인 날도 전부 미실행으로 보인다.** 부분 결측은 정상이고 전부 결측만이 "안 돌았다"다 |
| **D7** | 상위 설계의 "Cycle 4 에서 `app.js` 삭제"를 **정정한다** | 실측에서 틀렸다(§1.4). 예약 386줄이 남고 그 소비자가 `execute.html` 이다. 소멸은 Cycle 6 |
| **D8** | 드릴다운의 권한 축을 **시스템(`allowed_system_codes`)** 으로 건다 — 요청자(`user_id`) 축이 아니다 | 격자가 시스템 축이라 축이 다르면 **초록 칸인데 목록이 비는** 불일치가 난다. 더 근본적으로, 이 화면이 답해야 할 질문은 "내가 돌린 게 뭐냐"가 아니라 **"이 시스템 점검이 돌았느냐"** 다 — 예약 실행 Run 은 요청자 축에 잡히지 않는다 |
| **D9** | 드릴다운 응답에서 `created_by_user_id` · `created_by_user_name` 을 **뺀다** | D8 이 조회 범위를 요청자에서 시스템으로 넓히므로, 그대로 두면 남의 이름이 새 화면에 실려 나간다. 화면이 쓰지 않는 값이다(D3 의 간단한 목록은 시간·상태·모듈 수·링크뿐). **레이아웃 변경의 부수효과로 노출 범위를 넓히지 않는다** |
| **D10** | 스트립 8함수와 `createRunListItem` 을 **삭제하지 않는다** | `execute.html:385` 가 `renderRunList` → `renderExecutionGroups` 로 같은 코드를 쓴다(§1.3). 이 사이클의 삭제는 `bindRunsHistory` 40줄뿐이다 |

---

## 5. 테스트와 게이트

| 대상 | 위치 | 단언 |
| --- | --- | --- |
| 시스템 필터 | pytest | `allowed_system_codes` 밖 시스템이 응답에 없음 · 인자 없으면 전체 |
| 관리자 불변 | pytest | `/api/admin/dashboard` 가 여전히 `require_admin` · 응답 스키마 불변 |
| 격자 렌더 | Vitest `coverage.test.ts` | **3슬롯 전부 비면** `not_checked` · **1슬롯만 돌고 2개 비면 그 슬롯의 톤**(부분 결측은 정상) · 돌아간 것들 중 최악이 셀 톤 · 슬롯이 한 칸 안 조각으로 · 시스템 1개일 때도 성립 |
| 드릴다운 | Vitest `drilldown.test.ts` | 셀 선택 상태 · 목록 렌더 · **조회 실패 시 격자는 살아 있음** |
| 레이아웃 | pytest 템플릿 렌더 | 격자 구조 · JS 훅 생존 · 색 유틸리티 0 |
| 넌스크롤·소유권 | Playwright | 3뷰포트 스크롤 0 · 내부 스크롤러 **드릴다운 하나** |
| 삭제 확인 | pytest 또는 grep 기반 테스트 | `app.js` 에 `createRunListItem` · `createSuiteStripRow` · `buildExecutionGroups` 0개 |

`is_visible()` 로 가시성을 단언하지 않는다 — 뷰포트 밖 요소를 통과시킨다(`2026-08-24-execute-promotion-design.md` §8.2.1).

---

## 6. 리스크 · 한계

| 리스크 | 내용 | 대응 |
| --- | --- | --- |
| 실행 그룹 스트립을 버린다 | SUITE 와 하위 Run 의 연결이 한 줄로 보이던 표현이 이 화면에서 사라진다 | D3 의 의도된 절충(사용자 결정). 드릴다운 목록에 SUITE 배지로 표시하고, 연결 전체를 보려면 수트 상세로 간다. 표현 자체는 점검 실행 화면에 그대로 남는다 |
| 공유 코드를 남긴 채 소비자만 뗀다 | `app.js` 정리가 기대만큼 안 된다 | 실측이 그렇다(§1.3). 무리하게 지우면 `execute.html` 이 깨진다. 정리는 Cycle 6 에서 점검 실행 화면의 Run 목록을 옮길 때 함께 끝난다 |
| `/api/runs` 라우트에 날짜·시스템 필터가 없다 | 드릴다운이 서버 변경을 요구한다 | **실측 완료.** 쿼리 계층 `list_run_summaries_page` 에 `system_code` · `requested_since` · `requested_before` 가 **이미 있다**(`run_queries.py:167`). 라우트 한 겹만 추가한다 |
| 드릴다운의 권한 축이 격자와 다르다 | `list_runs` 는 비관리자를 `user_id` 로 거른다(`routes_runs.py:29`). 격자는 `allowed_system_codes`(시스템 축)로 거르므로, 그대로 두면 **초록 칸인데 드릴다운이 비는** 불일치가 난다 | 드릴다운도 **시스템 축**으로 건다(D8). 예약 실행 Run 은 요청자가 없거나 다른 사람이라 요청자 축으로는 "잘 돌았나"에 답할 수 없다 |
| 시스템 축으로 넓히면 남의 이름이 보인다 | `summarize_row` 가 `created_by_user_name` 을 싣는다(`summary.py:45`) | 드릴다운 응답에서 **실행자 2필드를 뺀다**(D9). 화면이 쓰지 않는 값이고, 레이아웃 변경의 부수효과로 노출 범위를 넓히지 않는다 |
| 7일 창이 짧을 수 있다 | 더 과거를 보려면 이 화면으로는 안 된다 | 커버리지 read model 의 창이 7일이다. 필요가 확인되면 후속 사이클에서 창을 늘린다 |
| 하루 한 칸이 정보를 뭉갠다 | 하루 3번 도는 시스템에서 조각이 작아진다 | D5 — 조각으로 보존하고 드릴다운이 전량을 보인다. 현 운영은 시스템당 하루 1 Run 이다 |
| 관리자 쿼리에 인자를 더한다 | `/admin` 회귀 위험 | 기본값 `None` 으로 기존 호출부 무변경. §5 가 관리자 응답 불변을 단언한다 |

---

## 7. 이후 — 이 문서가 남기는 것

| 항목 | 다음 |
| --- | --- |
| `app.js` 잔여 약 826줄 | Cycle 6(예약 + 점검 실행 Run 목록, 여기서 소멸) |
| `__executeLegacy` 5키 | Cycle 6 |
| `FG005_ALLOWLIST` 의 `/static/app.js` | Cycle 6 |
| `FG004_ALLOWLIST` 의 `app.css` | Cycle 5~6 |
| 공통 셸 | 다섯 화면이 쓴다 |
| `execute.html` 의 "진행 중 / 최근 Run" 구획 | Cycle 6 — 스트립 8함수 · `createRunListItem` · `bindRunsOverview` 계열 약 336줄이 여기 묶여 있다(§1.3) |
| `format.ts` 의 `formatRunTimestamp` 중복 1건 | Cycle 6(예약이 원본을 놓을 때) |
| 7일보다 긴 기간 조회 | 필요가 확인되면 |
| `/admin/runs` 승격 | 이번 순서에 없다 |

---

## 8. 참조

- 프로그램 상위 설계: `docs/superpowers/specs/2026-08-24-execute-promotion-design.md` (§2 여섯 사이클 · §4.2 승격 규격 5문항 · §8.2.1 검증 교훈)
- 직전 사이클: `docs/superpowers/specs/2026-08-31-run-detail-promotion-design.md` (D2 스크롤 규격 완화 · D4 규칙 소유자 판단)
- 커버리지 read model: `app/contexts/insights/application/admin_coverage_dashboard.py`
- 대체 대상 AC Spec: `docs/specs/dashboard/03-run-suite-views.md` (`SPEC-UI-003` §2 Run 이력)
- 게이트 SSOT: `scripts/check_frontend_gates.py` · `docs/CI.md`
- 상태 SSOT: `app/core/status_labels.py` → `app/web/frontend/styles/tokens.generated.css`
