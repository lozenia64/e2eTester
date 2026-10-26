# 수트 상세 모듈 대시보드 — Design

**작성일:** 2026-10-26
**상태:** 초안 (사용자 리뷰 대기)
**대상:** `app/web/templates/suite.html`, `app/web/frontend/suite/`, `app/web/frontend/components/status-hero/`(재사용)
**선행:** `2026-08-29-suite-promotion-design.md` (현재 수트 화면의 구조·소켓·ETA)

---

## 0. 요약

전체 점검(수트) 화면은 실행 중 **띄워두고 계속 지켜보는** 화면이다(사용자 확인). 그런데 진행 표시가
"모듈 2/8 실행 중" 같은 **숫자뿐이라 지켜봐도 무슨 일이 일어나는지 실감이 안 난다**(사용자 원문: "숫자만
올라가는게 답답해").

목표는 하나: **모듈별로 통과/실패/진행 중이 한눈에 보인다**(사용자 원문). 두 곳을 바꾼다.

| 영역 | 결정 (사용자) | 브레인스토밍 목업 |
| --- | --- | --- |
| 시스템 카드 안 | **B안 모듈 칩** — 모듈 이름이 적힌 알약을 실행 순서대로 | `.superpowers/brainstorm/*/content/module-view.html` |
| 상단 요약 (`.suite-sum`) | **C안 원형 게이지 + "지금 실행 중" 카드** | `.superpowers/brainstorm/*/content/summary-view.html` |

실패 알림은 **칩이 빨갛게 바뀌는 것으로 충분**하다(사용자 확인) — 흔들림·토스트·소리 없음.

---

## 1. 목표 · 비목표 · 반목표

**목표**
- 각 시스템 카드에서 모듈별 상태(통과·실패·이상·실행 중·OTP 대기·미실행)를 이름과 함께 즉시 읽을 수 있다.
- 상단에서 전체 진행률(모듈 기준), 지금 돌고 있는 시스템·모듈, 통과/실패 집계, 경과·남은 시간을 본다.
- 상태 전환에 가벼운 애니메이션이 있어 "살아 움직이는" 느낌을 준다.

**비목표**
- 서버·API·WS 계약 변경. 필요한 데이터는 이미 클라이언트에 온다(§3).
- 실패 시 추가 경보(흔들림, 토스트, 소리, 브라우저 알림).
- 다른 화면(대시보드, run 상세, 실행 화면) 변경.
- 수트 재실행·모듈 단위 조작 등 새 기능.

**반목표** (기술적으로 돌아가도 실패로 본다)
- 화면이 산만해서 오히려 지켜보기 피곤해지는 것 — 상시 움직이는 것은 "실행 중" 칩 하나와 라이브 점 하나뿐.
- 숫자가 실제와 어긋나는 것 — 링/집계가 칩과 다른 값을 말하면 안 된다(같은 데이터에서 계산).
- 기존 동작 회귀: OTP 패널, 취소 버튼, 자동 펼침(`expanded_step_order`), ETA.

---

## 2. 화면 동작

### 2.1 시스템 카드 — 모듈 칩

기존 `[data-role="step-module-progress"]` 의 한 줄 텍스트("모듈 2/8 실행 중 · 로그인")를 **칩 목록으로 대체**한다.

| 모듈 상태 | 칩 모양 |
| --- | --- |
| passed | 초록 배경, `✓ 이름` |
| error | 빨강 배경, `✕ 이름` |
| failed (레거시) | `status-badge` 톤 맵을 따른다(현재 anomaly 로 매핑) |
| anomaly | 주황 배경, `! 이름` *(저자 판단: 코드에 이미 구분된 톤)* |
| running | 파랑, 스피너 + 이름, 맥박(pulse) 링 |
| waiting_input | 노랑, `OTP` 표시 + 이름 *(저자 판단)* |
| blocked | 회색 점선 테두리, `⊘ 이름` + "차단" (선행 모듈 실패로 실행 안 됨 — 사용자 결정) |
| pending / queued | 회색 테두리, 이름만 |
| skipped / 선택 제외 모듈 | 표시하지 않음 (`orderedSelectedRunModules` 규칙 그대로) |
| cancelled | 회색, 취소선 *(저자 판단)* |

- 순서: 모듈 `order` 순. 줄바꿈으로 감싼다(접기·"+N" 축약 없음 — *저자 판단*, 목업의 "+6"은 채택하지 않음.
  모듈 최대 10개 수준이라 두 줄 안에 들어간다).
- 칩 상태가 바뀌는 순간 짧은 pop(scale 0.85→1, ~250ms). **모듈별 직전 상태와 비교해 실제로 바뀐 칩만** 튄다.
  끝난 run 페이로드는 수트 WS 메시지마다 다시 fetch 되므로(`refreshFinishedSuiteStepProgress`), "첫 렌더 여부"로 가르면
  이벤트마다 칩이 다시 튄다. 페이지 진입 시 첫 그리기는 애니메이션 없음.
- 칩 클릭 → `/runs/{run_id}` 로 이동 *(저자 판단)*. run 상세에 `data-module-id`(`run.html:85`)가 있으니 모듈 위치로 스크롤할 수단이 있으면 붙인다.
- run 링크(`run_2026…`) 줄은 유지한다.
- **run 이 아직 없는 스텝**(대기): 칩 없이 지금처럼 "대기 중" *(저자 판단: 모듈 이름은 run 생성 전엔 클라이언트에 없다)*.
- **skipped 스텝**: 지금처럼 "건너뜀 (선택 제외)".
- `[data-role="step-module-progress"]` 의 텍스트 요약(`formatStepModuleProgressText`)은 칩 목록 위/옆에 남기지 않는다 —
  칩이 그 정보를 대신한다. 단, 스크린리더용으로 칩 목록에 `aria-label="모듈 3/8 실행 중 · 보험금청구"` 형태로 같은 문구를 단다.

### 2.2 상단 요약 — 링 + "지금 실행 중" 카드

`.suite-sum` 블록을 다음 배치로 바꾼다.

```
┌────────┐  ┌───────────────────────────────────────────┐
│  링    │  │ ● 지금 실행 중 · 0:18                        │
│  54%   │  │ 대표홈페이지(모바일) › 보험금청구             │
│  완료  │  │ 시스템 2/4 · 모듈 3/8                        │
└────────┘  └───────────────────────────────────────────┘
            ✓ 11 통과  ✕ 1 실패  남음 11 · 05:00 경과 · 약 4분 남음
```

- **링**: 전체 모듈 기준 완료율. 분자 = 끝난 모듈 수(passed + failed/error + anomaly + blocked + cancelled — blocked 포함은 사용자 결정),
  분모 = 선택된(skipped 아닌) 스텝들의 모듈 수 합. 링 색은 초록 한 색, 가운데 `%` 숫자.
  값이 바뀌면 링이 부드럽게 차오르고(transition) 숫자는 짧게 카운트업.
  기존 `components/status-hero` 의 `passRateToDegrees` + conic-gradient 방식을 재사용한다(새 SVG/차트 라이브러리 없음).
- **"지금 실행 중" 카드**:
  - 1행: 파란 라이브 점(pulse) + "지금 실행 중 · {현재 모듈 경과 m:ss}". 현재 모듈 경과는 해당 모듈 `started_at` 기준, 1초마다 갱신.
  - 2행(크게): `{시스템명} › {모듈명}`. 모듈명을 아직 모르면 시스템명만.
  - 3행: `시스템 {현재 순번}/{선택 시스템 수} · 모듈 {현재}/{전체}`.
  - OTP 대기 중: 카드 노란 톤, 1행 "OTP 입력 대기", 2행 동일. 기존 OTP 입력 패널·카운트다운은 그대로 둔다 *(저자 판단)*.
  - 수트 종료(passed/anomaly/error/failed/cancelled): 카드가 결과 카드로 바뀐다 — 라이브 점 제거, 1행 "완료"/"취소됨" 등
    상태 라벨, 2행 "통과 N · 실패 M" *(저자 판단)*. 링은 마지막 값에 멈춘다.
- **집계 줄**: `✓ {통과} 통과 · ✕ {실패+이상} 실패 · ⊘ {차단} 차단 · 남음 {미실행} · {수트 경과 mm:ss} 경과 · {ETA 문구}`.
  차단은 실패와 섞지 않고 별도 칸(사용자 결정). 차단 0 이면 그 칸은 숨긴다 *(저자 판단)*.
  이상징후는 실패 숫자에 포함한다 *(저자 판단)*. 경과·ETA 는 기존 `updateSuiteEtaBlock`/`computeSuiteEta` 결과를 그대로 쓴다.
- 기존 `#suite-progress-label`("통과 1/4"), `#suite-progress-bar`, `#suite-progress-detail` 은 이 블록으로 대체되어 사라진다.

### 2.3 모션 접근성

`@media (prefers-reduced-motion: reduce)` 에서 pulse·spin·pop·카운트업·링 transition 을 끈다(값은 즉시 반영).
기존 컴포넌트(`status-hero/styles.css:156` 등)와 같은 방식.

---

## 3. 데이터 — 서버 변경 없음

| 필요한 것 | 출처 (현재 있음) |
| --- | --- |
| 스텝 목록·상태·run_id·현재 스텝 | 수트 스냅샷/WS (`renderSuiteSnapshot`) |
| 스텝별 모듈 수 | `SuiteStep.module_total`(`app/core/suite_models.py`) — 수트 스냅샷/WS `steps[]` 에 실려 온다. `SuiteStepLike` 타입에 필드만 추가. 수트는 전체 모듈로 run 을 만들므로 칩 개수와 일치 |
| 모듈별 이름·상태·order·started_at | run 페이로드 `modules[]` — 활성 run 은 진행 WS(`syncSuiteRunProgressSocket`), 끝난 run 은 수트 WS 메시지마다 `refreshFinishedSuiteStepProgress` → `refreshSuiteRunProgress` 로 재fetch |
| 경과·ETA | 기존 `updateSuiteEtaBlock` |

- 링·집계는 **스텝별 최신 run 페이로드 캐시**(run_id → modules)에서 계산한다. 이 캐시는 지금 없으므로 새로 만든다
  (`noteRunPayload` 는 구독 중인 run 하나만 들고 있다). 모든 run 페이로드가 지나가는 `updateSuiteStepModuleProgress` 에서 채운다.
- 캐시에 아직 없는 끝난 스텝(fetch 전): 스텝 상태가 passed 면 `module_total` 전부 통과로 임시 계산하고,
  그 외 종료 상태는 미실행 종료로 센다. fetch 도착 시 실제 결과로 재계산한다.
- 강제 종료로 잔여 모듈이 대기·실행·입력 대기로 남아도 종료된 run 또는 스텝에서는 취소로 표시한다.
  칩과 완료 집계는 같은 유효 상태를 사용한다. 종료된 run은 활성 ID가 남아 있어도 실행 중 카드에 표시하지 않는다.
- 칩 노드는 모듈 ID별로 재사용해 키보드 포커스와 실행 애니메이션을 보존한다.
  개별 링크의 접근성 이름에는 상태 라벨을, 링의 접근성 이름에는 현재 완료율을 포함한다.
- 같은 목표값의 카운트업은 재시작하지 않으며 목표가 바뀌면 이전 프레임을 무효화한다.
  동일 run 조회의 오래된 HTTP 응답은 최신 응답 또는 WS 스냅샷을 덮어쓰지 않는다.
- 모듈 `started_at` 이 페이로드에 없으면 "지금 실행 중" 1행의 모듈 경과를 생략한다(빌더 확인 필요 — §5).

---

## 4. 구현 제약

- 위치: `app/web/frontend/suite/` 안에서 끝낸다. 순수 계산(칩 목록 모델, 링 집계)은 DOM 없는 함수로 분리하고
  `progress.ts` 와 같은 결로 vitest 테스트를 둔다(`progress.test.ts`, `eta.test.ts` 패턴).
- 스타일: `suite/styles.css` 에 추가. 상태 색은 기존 `status-badge` 톤 토큰을 쓴다(새 색 체계 만들지 않음).
- 새 의존성 없음. 애니메이션은 CSS keyframes/transition, 카운트업만 `requestAnimationFrame` 몇 줄.
- UI 문자열 한국어(AGENTS.md).
- 기존 동작 보존: OTP 패널·카운트다운, 취소 버튼, `expanded_step_order` 자동 펼침, ETA.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full`.

---

## 5. 빌더 재량

- 칩·카드·링의 정확한 크기·간격·폰트, 애니메이션 타이밍 세부값 (목업 수준 참고).
- 새 순수 함수의 이름·파일 분할.
- run 상세에 모듈 앵커가 있는지 확인 후 칩 링크에 붙일지.
- 모듈 `started_at` 이 run 페이로드 `modules[]` 에 실려 오는지 확인(도메인 `RunModule.started_at` 은 존재).
- 기존 `formatStepModuleProgressText`/`updateSuiteProgressDetailWithModule` 의 정리 범위 — 더 이상 쓰이지 않으면 제거.
