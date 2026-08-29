# 수트 상세 승격 (Suite Promotion) — Design

**작성일:** 2026-08-29
**상태:** 초안 (사용자 리뷰 대기)
**대상:** `app/web/templates/suite.html`, `app/web/static/app.js`, `app/web/frontend/suite/`(신규), `app/web/frontend/lib/otp-countdown.ts`(신규), `app/api/routes_dashboard.py`, `app/contexts/run/contracts/ports.py`, `SuiteView`

---

## 0. 요약

화면 격차 해소 프로그램의 **Cycle 2** 다. 순서는 `2026-08-24-execute-promotion-design.md` §2 가 정한 여섯 사이클 중 두 번째 — 점검 실행(Cycle 1a·1b 완료) 다음의 수트 상세다.

이 화면의 사용 맥락은 **"실행 중 띄워두고 지켜본다"**(사용자 확인). 그래서 설계는 사후 조회가 아니라 진행 관찰에 맞춘다. 지켜보는 사람이 알고 싶은 것은 두 가지이고(사용자 확인), 둘 다 답한다.

| 알고 싶은 것 | 담당 장치 |
| --- | --- |
| 지금 어느 시스템의 어느 모듈인가 | 진행 중 스텝만 자동 전개되는 수직 파이프라인 |
| 언제 끝나나 | 상단 진도 블록(경과 · ETA) + 각 행의 실측/평균 소요시간 |

레이아웃은 **B안(수직 파이프라인)**, ETA 는 **ETA-2(과거 평균 재사용)**, 펼침은 **항상 자동**이다(전부 사용자 결정, §4).

이 문서를 쓰는 과정에서 **선행 기록의 오류 네 건을 실측으로 정정했다**(§1.4). 그중 둘은 브레인스토밍 중 저자가 사용자에게 잘못 보고한 것이고, 그 위에서 내려진 결정 하나(공유 코드 승격)를 §4 D6 이 다시 세운다.

---

## 1. 문제

### 1.1 이 화면은 이미 진짜 실시간인데, 그것이 보이지 않는다

`bindSuiteSocket`(`app.js:1779`)과 `syncSuiteRunProgressSocket`(`app.js:1524`)이 **WebSocket 두 개**를 쓴다 — 수트 이벤트 소켓과, 현재 실행 중인 하위 Run 의 진행 소켓. 일간 대시보드가 30초 폴링인 것과 대비된다(`2026-08-23-dashboard-mission-control-design.md` §1.3).

그런데 그 실시간성이 화면에서 드러나는 곳은 **진행률 바 몇 픽셀과 배지 색**뿐이다. 승격의 재료가 이미 있고 표현이 없다.

### 1.2 화면이 "지켜보는 도구" 의 형태가 아니다

`suite.html`(85줄)은 헤더 → 진행률 바 → OTP 패널 → 2열 카드 그리드의 세로 스택이고 스크롤한다. 6개 스텝이 2열로 흩어져 **"지금 어디" 가 시선을 끌지 않는다.** 진행 중 스텝은 배지 색으로만 구별된다.

### 1.3 외형이 전부 템플릿 인라인 유틸리티다

`suite.html` 이 쓰는 클래스 중 실제 CSS 정의가 있는 것은 `progress-bar-fill`(`app.css:264`) 하나뿐이다.

| 클래스 | 정의 |
| --- | --- |
| `suite-step-card`(`suite.html:65`) · `otp-panel`(`suite.html:37`) | **없음** — 붙어 있으나 어떤 스타일시트에도 규칙이 없다 |
| 나머지 | Tailwind 유틸리티 **235개** 가 템플릿에 인라인 |

Cycle 0 이 팔레트를, Cycle 1a·1b 가 실행 화면을 정리한 덕에 **이 화면에는 로그 팔레트·상태 라벨 부채가 없다.** 남은 것은 레이아웃과 이관뿐이다.

### 1.4 실측이 선행 기록 네 건을 정정했다

이 설계를 세우며 호출자를 전수 확인한 결과, 브레인스토밍 초기에 저자가 제시한 전제 중 넷이 틀렸다. 설계가 그 위에 서 있었으므로 남긴다.

| # | 잘못된 전제 | 실측 |
| --- | --- | --- |
| **C1** | `computeRunModuleProgress` 계열을 수트와 런이 공유한다 | **수트 전용.** 호출자는 `updateSuiteStepModuleProgress`(`:1445`)와 `updateSuiteProgressDetailWithModule`(`:1461`) 둘뿐이고 둘 다 수트 함수다. `orderedSelectedRunModules`·`moduleProgressClassName` 도 이 체인 안에서만 쓰인다 |
| **C2** | 수트 OTP 와 런 OTP 가 "거의 같은 코드 두 벌" 이다 | **두 벌이 아니라 경계를 걸쳐 쪼개져 있다.** `updateOtpPanel`(런)은 이미 TS 로 갔고 `main.ts:36` 이 `window.__executeOtpPanel` 로 노출해 `app.js:1847·1875·1882` 의 런 소켓이 호출한다. `updateSuiteOtpPanel`(수트)은 `app.js:1667` 에 남아 있다 |
| **C3** | Cycle 1b 가 "호환 다리를 다음 사이클로 넘기지 않는" 원칙을 세웠다 | **과장이었다.** Cycle 1b 는 `__executeModuleGraph` 등 **세 개**를 지웠고, `app.js:1182` 의 주석이 명시하듯 `__executeLegacy`·`__executeOtpPanel` **둘은 Cycle 4 까지 유지**하기로 의도적으로 남겼다 |
| **C4** | 수트 OTP 패널에 카운트다운이 있다 | **없다.** `suite.html:45` 의 `#suite-otp-countdown` 은 존재하지만 아무도 채우지 않는 죽은 마크업이다. 카운트다운을 넣는 것은 **신규 기능**이며, 사용자 결정으로 이번 범위에 포함한다(D5) |

C1·C2 는 "공유 코드를 먼저 승격한다" 는 결정의 근거였다. 근거가 사라졌으므로 D6 이 그 결정을 다시 세운다.

---

## 2. 목표 / 비목표 / 성공 기준

### 2.1 목표

1. 지켜보는 동안 **"지금 어느 시스템의 어느 모듈"** 이 화면의 지배 정보가 된다.
2. **"언제 끝나나"** 에 답한다 — 경과 · ETA · 스텝별 소요시간.
3. 넌스크롤. 내부 스크롤을 갖는 영역은 **정확히 하나**(스텝 목록).
4. `app.js` 에서 수트 몫 약 568줄을 떼어 `entries/suite.ts` 로 옮긴다.
5. `__executeLegacy` 다리를 **8개 → 5개** 로 줄인다.

### 2.2 비목표 (명시적 YAGNI)

- **간트 타임라인** — 과거를 보는 도구다. 지켜보는 화면의 지배 요소로 맞지 않고, `SuiteStep`(`app/core/suite_models.py:12`)에 `started_at`/`ended_at` 이 없어 도메인·이벤트 wire·스냅샷·프로젝션을 함께 바꿔야 한다. 목적이 그것을 요구하지 않으므로 하지 않는다.
- **`SuiteStep` 도메인 모델 확장** — 위와 같은 이유. 이 사이클은 도메인·이벤트 wire 를 **한 줄도** 건드리지 않는다.
- **수동 펼침** — D4. 상태를 하나로 유지한다.
- **대시보드 WebSocket 신설 · 다크모드 · SPA** — 선행 설계들의 결정 유지.
- **`app.css` 축소** — 이 화면이 `app.css` 에서 쓰는 것은 `progress-bar-fill` 하나뿐이다(§1.3). `FG004_ALLOWLIST` 는 이번에도 비지 않는다(§6).
- **런 상세 OTP 통합** — `__executeOtpPanel` 다리는 런 소켓이 `app.js` 에 남아 있는 한 유지된다. Cycle 3 의 몫이다.
- **`app.js` 소멸** — Cycle 4.

### 2.3 성공 기준

| 기준 | 측정 |
| --- | --- |
| 넌스크롤 | 1366 · 1920 · 2560 px 에서 `body` 세로 스크롤 0. 최악 조건(6 시스템 + OTP 대기)에서도 성립 |
| 스크롤 소유권 | 내부 스크롤을 갖는 요소가 스텝 목록 **하나** |
| 진행 중 스텝 가시 | 진행 중 스텝의 모듈 칩이 스크롤 없이 보인다 — `bounding_box()` 좌표로 단언(§5) |
| 자동 펼침 | 펼쳐진 스텝이 `expanded_step_order` 와 항상 일치. 수동 토글 경로 0 |
| ETA | 대기 스텝 baseline 합 + 현재 스텝 잔여. `WAITING_INPUT` 에서 정지 |
| 이관 | `entries/suite.ts` 존재. `app.js` 에 수트 함수 0개, 약 1,381줄 |
| 다리 축소 | `__executeLegacy` 키 8 → 5. 신규 다리 0 |
| 유틸리티 소거 | `suite.html` 에 Tailwind 색 유틸리티 0개 |
| 도메인 불변 | `snapshot_validate` · `projection_validate` 게이트 통과, 진단 diff 0 |

---

## 3. 설계

### 3.1 레이아웃 — 수직 파이프라인, 진행 중 스텝만 전개

```text
┌──────────────────────────────────────────────────────────────────┐
│ 대시보드 / 전체 점검                              ● 실행 중        │  헤더(고정)
├──────────────────────────────────────────────────────────────────┤
│ (OTP 대기 시에만) 🔒 OTP 입력이 필요합니다  02:47 남음 [___][제출] │  고정
├──────────────────────────────────────────────────────────────────┤
│ 스텝 진행                    2 / 6 완료  │        경과            │
│ ▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │       04:12            │  진도 블록(고정)
│                                          │    남은 약 6분          │
├──────────────────────────────────────────────────────────────────┤
│ ✓ HOM · 대표홈              3분 12초        통과 10/10            │
│ ✓ MHM · 모바일대표홈        1분 48초        통과 8/8              │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ ③ FP · 위촉서류            00:42          진행 중 2/3         │ │  ← 자동 전개
│ │   [로그인 ✓] [서류 업로드 ●] [제출 확인]                       │ │
│ │   평균 2분 30초 소요                        Run 상세 →         │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ 4 HRP · 현장출동          평균 2분 05초        대기               │
│ 5 HWTC · 연수원           평균 1분 30초        대기               │
│ 6 CHBOT · 챗봇            평균 55초            대기               │
└──────────────────────────────────────────────────────────────────┘
                              ↑ 이 목록만 내부 스크롤
```

**셸.** `body:has(.suite)` 넌스크롤. `.dash`·`.exec` 가 쓰는 것과 같은 규칙이며 **이번이 세 번째 사용처**이므로 공통 셸로 추출한다 — `2026-08-24-cycle1a-execute-layout.md` 가 "세 번째 화면이 같은 셸을 요구하면 공통으로 뽑는다" 로 남긴 항목을 회수한다(D7).

**세로 구성.** 헤더 · (조건부) OTP 패널 · 진도 블록은 고정, 스텝 목록만 `flex: 1` 이고 내부 스크롤을 갖는다.

**대기 스텝의 「평균 N분」 노출**(사용자 결정). ETA 의 재료를 화면에 그대로 드러낸다. 숫자 하나만 던지지 않고 근거를 함께 보이므로, 추정이 빗나가도 사용자가 이유를 안다. 행 안 우측 텍스트라 세로 예산을 더 쓰지 않는다.

**넌스크롤 예산** — 최악 조건 1366×768 · 시스템 6개 · OTP 대기:

| 영역 | 높이 |
| --- | --- |
| 헤더 | ~48px |
| OTP 패널(대기 시) | ~62px |
| 진도 블록 | ~66px |
| 접힌 행 ×5 | ~205px |
| 전개된 행 ×1 | ~112px |
| 패딩·간격 | ~98px |
| **합계** | **~591px** (가용 ~700px · 여유 ~109px) |

성립하지만 여유가 얇다. 요소를 하나 더 얹으면 깨지므로 §5 의 좌표 계약이 이를 지킨다.

### 3.2 자동 펼침 — 서버가 정한다

수동 펼침이 없으므로(D4) "펼쳐진 스텝" 은 수트 상태의 **순수 함수**다.

```text
진행 중 : waiting_input 스텝이 있으면 그것, 없으면 current_step_index
종료됨  : 첫 error → 없으면 첫 anomaly → 없으면 없음(전부 접힘)
```

이 규칙을 클라이언트에 두면 최초 서버 렌더와 WS 갱신이 **두 벌**이 되어 어긋난다. `SuiteView`(`ws_suites.py:57` 의 `SuiteView.dump`)에 **파생 필드 `expanded_step_order: int | None`** 를 추가한다. 페이지 최초 렌더와 모든 WS 페이로드가 같은 출처를 본다.

도메인 모델(`SuiteStep`·`SuiteRun`)과 이벤트 wire(`SuiteStepSummaryWire`)는 건드리지 않는다 — 뷰 계층 파생이므로 스냅샷·프로젝션 게이트 영역 밖이다.

**행 클릭은 Run 상세 이동**이다(펼침이 아니다). `run_id` 가 없는 대기 스텝은 클릭 대상이 아니다.

### 3.3 ETA — 과거 평균을 SQL 한 방으로

**baseline.** `run_history_index` 프로젝션 테이블(`app/platform/eventing/support.py:183`)에 `system_code` · `started_at` · `ended_at` 이 있고 `idx_run_history_system` 인덱스가 있다.

```sql
SELECT system_code,
       AVG((julianday(ended_at) - julianday(started_at)) * 86400000) AS avg_ms
FROM run_history_index
WHERE ended_at IS NOT NULL AND started_at IS NOT NULL
  AND status = 'PASSED' AND requested_at >= :since
GROUP BY system_code
```

`PASSED` 만 세는 이유: 중간에 끊긴 Run 의 소요시간은 "정상 실행이 얼마나 걸리는가" 의 표본이 아니다. 섞으면 평균이 짧아져 ETA 가 낙관적으로 빗나간다(D3).

**거처.** `RunSummaryQueryPort`(`app/contexts/run/contracts/ports.py:36`)에 `avg_duration_ms_by_system(*, days: int = 30) -> dict[str, int]` 를 추가한다. 이 포트에는 이미 `counts_by_status()` · `last_finished_at_by_system()` 같은 집계 메서드가 있으므로 **새 패턴이 아니라 형제**다. 어댑터는 sqlite · in-memory 둘 다 구현한다.

무거운 `get_system_health`(`insights_health.py`, 30일 Run 이력 순회)는 쓰지 않는다 — 페이지 로드 경로에서 시스템 수만큼 부르는 것은 낭비다.

**주입.** baseline 은 실행 중 변하지 않으므로 `routes_dashboard.py:152` 의 suite 페이지 컨텍스트에 `step_baselines: dict[str, int]` 로 **1회만** 넣는다. WS 페이로드에는 넣지 않는다.

**산술은 클라이언트.** 소켓 이벤트마다 재계산한다.

```text
남은 시간 = Σ(대기 스텝 baseline) + max(0, 현재 스텝 baseline − 현재 스텝 경과)
```

**"현재 스텝 경과" 의 출처.** 스텝 자체에는 시각이 없다(D9). 현재 스텝이 가리키는 **하위 Run 의 `started_at`** 에서 잰다 — 진행 소켓(`syncSuiteRunProgressSocket`)이 이미 그 Run 페이로드를 받고 있으므로 추가 조회가 없다. `started_at` 이 아직 없으면(큐 대기 중) 경과를 0 으로 본다.

| 상황 | 표시 |
| --- | --- |
| `WAITING_INPUT` | ETA **정지** — "입력 대기 중 · 계산 보류". 사람이 언제 입력할지는 예측 대상이 아니고, 섞으면 남은 시간이 계속 늘어 신뢰를 잃는다 |
| baseline 없는 시스템(이력 0) | 행에 "평균 —", ETA 합산에서 제외하고 "일부 제외" 표기 |
| 종료됨 | ETA 자리가 **총 소요시간 + 평균 대비 편차** 로 전환. 편차의 기준은 **Σ(이 수트에 포함된 모든 스텝의 baseline)** 이며, baseline 이 결측인 스텝이 하나라도 있으면 편차를 표시하지 않고 총 소요시간만 보인다 |

### 3.4 이관 경계

**승격 대상은 OTP 카운트다운 하나뿐이다.** C1·C2 이후 실제로 소비자가 둘인 것은 이것뿐이다.

| 대상 | 현재 | 소비자 |
| --- | --- | --- |
| `clearOtpCountdownTimer` · `stopOtpCountdown` · `startOtpCountdown` · `moduleStartedAtFromRun`(`app.js:1132~1192`) | `app.js` | `entries/execute.ts`(런, 기존) + `entries/suite.ts`(수트, 신규 — D5) |

거처는 **`app/web/frontend/lib/otp-countdown.ts`** 다(D6). 부수효과로 `__executeLegacy` 에서 세 키가 빠져 다리가 **8개 → 5개** 로 얇아진다. 이 사이클은 다리를 늘리지 않고 줄인다.

**나머지는 화면 폴더 `app/web/frontend/suite/`** — Cycle 1b 가 세운 화면 폴더 관례를 따른다.

| 파일 | 내용 |
| --- | --- |
| `progress.ts` | `orderedSelectedRunModules` · `computeRunModuleProgress` (순수 · Vitest) |
| `eta.ts` | baseline + 라이브 상태 → 남은 시간 (순수 · Vitest · 신규) |
| `steps.ts` | `updateSuiteStepCard` · `updateSuiteStepModuleProgress` · `findSuiteStepCardByRunId` · `formatStepModuleProgressText` · `refreshFinishedSuiteStepProgress` |
| `render.ts` | `renderSuiteSnapshot` · `updateSuiteProgress` · `updateSuiteActions` · `updateSuiteProgressDetailWithModule` · `currentSuiteId` |
| `socket.ts` | `bindSuiteSocket` · `syncSuiteRunProgressSocket` · `closeSuiteRunProgressSocket` · `resolveActiveSuiteRunId` · `refreshSuiteRunProgress` |
| `actions.ts` | `cancelSuite` · `bindSuiteActions` · `submitSuiteOtp` · `bindSuiteOtpForm` · `updateSuiteOtpPanel` |
| `styles.css` | 유틸리티 235개를 흡수한 컴포넌트 CSS |

`entries/suite.ts` 는 배선만 한다 — `entries/execute.ts`(15줄)와 같은 모양이다.

**`app.js` 절단 — 약 568줄**

| 덩어리 | 줄 |
| --- | --- |
| 수트 전용 20개 (`:1405~1812`) | ~409 |
| `computeRunModuleProgress` 체인 (`:1310~1404`) | ~95 |
| OTP 카운트다운 (`:1132~1192`) → `lib/` 로 이사 | ~61 |
| `DOMContentLoaded` 의 `bindSuiteActions`·`bindSuiteOtpForm`·`bindSuiteSocket` | 3 |
| **합계** | **~568** |

`app.js` **1,949 → 약 1,381줄.** 남는 것은 Run 이력 · Run 상세 · 예약 오버뷰 · 공용이며 Cycle 3·4 의 몫이다.

**신규 다리 0개.** 수트는 `app.js` 와 아무것도 주고받지 않는다. `__executeOtpPanel` 은 런 소켓이 아직 `app.js` 에 있으므로 Cycle 3 까지 그대로 둔다.

### 3.5 함께 없애는 것

**`moduleProgressClassName`(`app.js:1386`)의 하드코딩 색.** `text-red-600` · `text-amber-700` 같은 Tailwind 색 클래스를 상태별로 분기한다. Cycle 0 이 CSS 에서 없앤 병의 JS 버전이며, FG-006 이 템플릿만 보기 때문에 지금까지 잡히지 않았다. `data-tone` 속성 + `suite/styles.css` 규칙으로 바꾼다.

**죽은 훅 클래스.** `suite-step-card`(`suite.html:65`) · `otp-panel`(`suite.html:37`)은 어떤 스타일시트에도 정의가 없다. 컴포넌트 CSS 로 옮기며 정리한다.

**죽은 마크업의 부활.** `#suite-otp-countdown`(`suite.html:45`)은 지금 비어 있다. D5 로 실제 동작을 붙인다.

---

## 4. 결정

| # | 결정 | 근거 |
| --- | --- | --- |
| **D1** | 이 화면은 **진행 관찰용** 으로 설계한다 | "실행 중 띄워두고 지켜볼 때가 대부분"(사용자 확인). 사후 조회 중심 설계는 목적과 어긋난다 |
| **D2** | 레이아웃은 **B안 수직 파이프라인** | 사용자 결정. 종료 후 6줄이 그대로 결과 목록이 되는 것이 강점. A안(2단 관제)은 영역이 셋이라 복잡하고, C안(현재 스텝 전면)은 "언제 끝나나" 에 답하지 못한다 |
| **D3** | ETA 는 **ETA-2**(과거 평균) · baseline 은 `PASSED` Run 만 | 사용자 결정. 실패 Run 을 섞으면 평균이 짧아져 낙관적으로 빗나간다. `run_history_index` 인덱스 덕에 SQL 한 방이면 된다 |
| **D4** | 펼침은 **항상 자동, 수동 없음** | 사용자 결정. 상태가 하나뿐이라 가장 단순하고, Cycle 1a 가 겪은 "갱신 때마다 열림 상태가 사라지는" 문제 계열이 원천적으로 생기지 않는다. 이 결정이 행 클릭의 의미(Run 이동)와 종료 후 거동을 함께 확정한다 |
| **D5** | 수트 OTP 패널에 **카운트다운을 신설**한다 | 사용자 결정. 수트는 OTP 구간에서 멈춰 사람을 기다리므로 "언제까지 입력해야 하나" 가 필요하다. 부수효과로 카운트다운이 진짜 공유분이 되어 D6 을 정당화한다 |
| **D6** | 카운트다운을 **`frontend/lib/otp-countdown.ts`** 로 승격한다 | 사용자 결정("먼저 승격")을 유지하되 거처를 조정했다. 원안의 `frontend/run-progress/` 는 C1 로 근거가 사라졌고(공유는 카운트다운 하나뿐), 파일 하나를 위해 새 폴더를 만들면 이름이 내용보다 크다. `frontend/lib/` 는 이미 화면 무관 공유물(`status.generated.ts`)의 자리다 |
| **D7** | 넌스크롤 셸을 **공통으로 추출**한다 | `.dash`·`.exec`·`.suite` 로 세 번째 소비자가 생겼다. Cycle 1a 계획이 남긴 승격 조건을 충족한다 |
| **D8** | `expanded_step_order` 를 **`SuiteView` 파생 필드** 로 서버가 계산한다 | 클라이언트에 두면 서버 렌더와 WS 갱신이 두 벌이 되어 어긋난다. 도메인·이벤트 wire 를 건드리지 않으므로 스냅샷·프로젝션 게이트 영역 밖이다 |
| **D9** | 도메인 모델과 이벤트 wire 를 **한 줄도 바꾸지 않는다** | 간트 타임라인을 비목표로 둔 결과. `SuiteStep` 에 시각 필드를 넣는 변경은 도메인·wire·스냅샷·프로젝션 4층을 동시에 건드린다 |

---

## 5. 테스트와 게이트

| 대상 | 위치 | 단언 |
| --- | --- | --- |
| ETA 산술 | Vitest `suite/eta.test.ts` | 대기 스텝 합산 · 현재 스텝 잔여가 음수로 가지 않음 · `WAITING_INPUT` 정지 · baseline 결측 시 제외와 "일부 제외" 표기 · 전 스텝 baseline 결측 시 ETA 미표시 |
| 모듈 진행 계산 | Vitest `suite/progress.test.ts` | 진행 중 / 이상 / 실패 / 완료 각 경로의 `current·total·tone` |
| 자동 펼침 규칙 | pytest (뷰 단위) | 진행 중 → `current_step_index` · `waiting_input` 우선 · 종료 시 첫 error → 첫 anomaly → `None` |
| baseline 쿼리 | pytest | `PASSED` 만 집계 · 미완료 Run 제외 · 이력 없는 시스템은 키 부재 · in-memory 어댑터와 sqlite 결과 일치 |
| 넌스크롤 | Playwright | 1366 · 1920 · 2560 px 에서 `body` 세로 스크롤 0 |
| 스크롤 소유권 | Playwright | 내부 스크롤 요소가 스텝 목록 하나 |
| 진행 중 스텝 가시 | Playwright | 전개된 스텝의 모듈 칩이 **`bounding_box()` 기준 뷰포트 안** |
| 도메인 불변 | 기존 `snapshot_validate` · `projection_validate` | diff 0 |

**`is_visible()` 을 쓰지 않는다.** Cycle 1a 에서 실행 버튼이 1366×768 기준 1,188px 아래(화면 밖)에 있었는데 `is_visible()` 단언이 통과했다 — Playwright 의 그것은 `display`·`visibility`·크기만 보고 뷰포트 밖 요소를 통과시킨다(`2026-08-24-execute-promotion-design.md` §8.2.1). 넌스크롤 예산 여유가 109px 뿐인 이 화면에서 같은 실수를 반복하면 결함이 그대로 숨는다.

각 단언은 **"이 단언이 실패할 수 있는 실제 경우는 무엇인가"** 에 답해야 한다. 답하지 못하는 단언은 통과 여부와 무관하게 아무것도 지키지 않는다.

---

## 6. 리스크 · 한계

| 리스크 | 내용 | 대응 |
| --- | --- | --- |
| 넌스크롤 여유가 109px 뿐 | 요소를 하나 더 얹으면 깨진다 | 좌표 계약 회귀 테스트(§5). 스텝 수는 최대 6(시스템 수)로 상한이 있다 |
| ETA 가 빗나간다 | 과거 평균은 자가 치유·재시도·네트워크 지연을 예측하지 못한다 | "약 N분" 으로만 표기하고 분 단위로 절사한다. 대기 스텝의 「평균 N분」 을 함께 노출해 근거를 보인다(사용자 결정) |
| baseline 이 비어 있는 초기 환경 | 새 시스템·초기 배포 직후엔 `PASSED` 이력이 없다 | 행은 "평균 —", ETA 는 해당 스텝을 제외하고 "일부 제외" 표기. 전부 결측이면 ETA 를 표시하지 않고 경과만 보인다 |
| 자동 펼침이 사용자 의사를 무시한다 | 지나간 스텝의 모듈을 들여다볼 수 없다 | D4 의 의도된 절충(사용자 결정). 상세는 Run 상세 링크가 담당한다. 필요가 확인되면 후속 사이클에서 되돌린다 |
| Cycle 2 가 `app.css` 를 줄이지 않는다 | 이 화면이 `app.css` 에서 쓰는 것은 `progress-bar-fill` 하나뿐이다 | 의도된 결과다. `FG004_ALLOWLIST` 는 Cycle 3~6 이 비운다. Cycle 1b(−661줄)와 성격이 다름을 미리 기록한다 |
| WS 두 개의 수명 관리 | 수트 소켓 + 하위 Run 진행 소켓. 스텝이 넘어갈 때 후자를 갈아끼운다 | `syncSuiteRunProgressSocket`·`closeSuiteRunProgressSocket` 의 기존 로직을 **동작 변경 없이** 이관한다. 이관 중 소켓 누수 여부를 실물로 확인한다 |

---

## 7. 이후 — 이 문서가 남기는 것

| 항목 | 비고 |
| --- | --- |
| `app.js` 잔여 **1,384줄**(실측, 아래 §7.1) | Cycle 3(런 상세) → 4(Run 이력, 여기서 소멸) |
| `__executeOtpPanel` 다리 | Cycle 3 에서 런 소켓이 TS 로 가면 소멸 |
| `__executeLegacy` 잔여 **5키**(실측) | Cycle 4 |
| `FG004_ALLOWLIST` 의 `app.css` | Cycle 3~6 이 절씩 이사 |
| `FG005_ALLOWLIST` 의 `/static/app.js` | Cycle 4 |
| 공통 넌스크롤 셸 | D7 로 이번에 추출. Cycle 3 이 네 번째 소비자가 된다 |
| `SuiteStep` 시각 필드 · 간트 타임라인 | 사후 분석 요구가 생기면 별도 사이클. 도메인·wire·스냅샷·프로젝션 4층 변경 |
| ETA 정확도 개선 | 시스템별이 아니라 **모듈별** baseline 을 쓰면 정밀해진다. `insights_breakdown.py:119` 에 재료가 있다. 현재 정확도로 부족하다고 확인되면 후속 |

### 7.1 Cycle 2 실측 (구현 완료 시점)

추정이 아니라 브랜치 `feat/suite-promotion` 의 실제 값이다.

| 항목 | 예상 | 실측 |
| --- | --- | --- |
| `app.js` 줄 수 | 1,949 → 약 1,381 | 1,949 → **1,384** (−565) |
| `__executeLegacy` 키 | 8 → 5 | 8 → **5** (`setInlineFeedback` · `readErrorMessage` · `bindScheduleBuilder` · `buildScheduleCron` · `refreshScheduleList`) |
| 수트 `window.__execute*` 다리 | 0 신설 | **0** — `app/web/frontend/suite/` 에 `__execute` 참조 없음(grep 확인) |

**`app/web/frontend/suite/` 파일별 줄 수** — 전부 FG-004(400줄) 미만:

| 파일 | 줄 |
| --- | --- |
| `progress.ts` | 116 |
| `progress.test.ts` | 47 |
| `eta.ts` | 52 |
| `eta.test.ts` | 52 |
| `steps.ts` | 114 |
| `render.ts` | 219 |
| `socket.ts` | 147 |
| `actions.ts` | 199 |
| `styles.css` | 339 |

**공유 승격:** `app/web/frontend/lib/otp-countdown.ts` 67줄 · `app/web/frontend/entries/suite.ts` 12줄(배선만).

---

## 8. 참조

- 프로그램 상위 설계: `docs/superpowers/specs/2026-08-24-execute-promotion-design.md` (§2 여섯 사이클 · §4.2 승격 규격 5문항 · §8.2.1 검증 교훈 · D4 컴포넌트 승격 규칙)
- 직전 사이클: `docs/superpowers/plans/2026-08-24-cycle1b-execute-migration.md`
- 대체 대상 AC Spec: `docs/specs/dashboard/03-run-suite-views.md` (`SPEC-UI-003` §1 Run/Suite 상세)
- 수트 사가: `docs/specs/suite/01-saga-lifecycle.md`
- 게이트 SSOT: `scripts/check_frontend_gates.py` · `docs/CI.md`
- 상태 SSOT: `app/core/status_labels.py` → `app/web/frontend/styles/tokens.generated.css`
