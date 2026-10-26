# 수트 상세 모듈 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수트 상세 화면의 "모듈 2/8" 숫자 표시를 모듈 칩 목록과, 원형 링 + "지금 실행 중" 카드 요약 블록으로 바꾼다.

**Architecture:** 계산은 DOM 없는 순수 함수(`suite/modules.ts`)로 두고 vitest 로 고정한다. 모든 run 페이로드가 지나가는 `updateSuiteStepModuleProgress` 에서 run 캐시를 채우고, 칩(`steps.ts`)과 요약(`render.ts`)은 그 캐시 + 마지막 수트 스냅샷에서 다시 그린다. 서버·API·WS 변경 없음.

**Tech Stack:** TypeScript(vanilla DOM), Vite, vitest + jsdom, Jinja2 템플릿, CSS(`@property` + conic-gradient), pytest(레이아웃 계약).

**Spec:** `docs/superpowers/specs/2026-10-26-suite-module-dashboard-design.md`

## Global Constraints

- 서버·API·WS 계약 변경 없음. 새 npm 의존성 없음.
- UI 문자열 한국어.
- 상태 색은 기존 토큰만: `--st-{tone}-solid|surface|text|border` (`styles/tokens.generated.css`). 칩 톤은 `normalizeTone()`(`components/status-badge/index.ts`) 결과를 그대로 쓴다 — `failed`→`anomaly`, `queued`→`pending` 매핑 포함.
- 마크업에 Tailwind 색 유틸리티 금지(`tests/test_suite_layout.py::test_no_tailwind_color_utilities`).
- `@media (prefers-reduced-motion: reduce)` 에서 pulse·spin·pop·링 transition 끄고, 카운트업은 즉시 최종값.
- 기존 동작 보존: OTP 패널·카운트다운, 취소 버튼, `expanded_step_order` 자동 펼침, ETA(`computeSuiteEta`).
- 링 분자 = passed + error + anomaly + blocked + cancelled 모듈. 분모 = skipped 아닌 스텝의 모듈 수 합.
- 집계 줄 문구: `✓ {통과} 통과 · ✕ {실패} 실패 · ⊘ {차단} 차단 · 남음 {남음} · {mm:ss} 경과 · {ETA}`. 실패 = error + anomaly. 차단 0 이면 차단 칸 숨김.
- 검증 명령: `npm test`, `npm run typecheck`, `npm run lint`, `python -m pytest tests/test_suite_layout.py -q`, PR 전 `python3 scripts/ci/run_all_gates.py --profile full`(백그라운드).

## Review Focus

1. 실패가 섞인 run(뒤 모듈 BLOCKED)이 끝나면 링이 100%, 남음 0 이어야 한다 → Task 1 `summarizeSuiteModules` 테스트.
2. 끝난 run 은 수트 WS 이벤트마다 재fetch 된다 → 같은 칩을 다시 그려도 pop 이 다시 붙지 않아야 한다 → Task 2 테스트.
3. 끝난 스텝인데 run 페이로드가 아직 캐시에 없을 때 0% 로 깜빡이지 않는다(passed 스텝은 `module_total` 전부 통과로 계산) → Task 1 테스트.
4. 선택 시스템이 전부 skipped / 모듈 0 → 링 0%, NaN 없음 → Task 1 테스트.
5. OTP 대기 중이면 "지금 실행 중" 카드가 대기 톤과 "OTP 입력 대기" 문구로 바뀐다 → Task 1 `describeNow` 테스트.

---

## File Structure

| 파일 | 역할 |
| --- | --- |
| Create `app/web/frontend/suite/modules.ts` | 순수 계산: 칩 모델, 수트 모듈 집계, 현재 실행 카드 모델 |
| Create `app/web/frontend/suite/modules.test.ts` | 위 함수 테스트 |
| Modify `app/web/frontend/suite/steps.ts` | run 캐시, 칩 렌더(diff + pop) |
| Create `app/web/frontend/suite/steps.test.ts` | 칩 렌더 jsdom 테스트 |
| Modify `app/web/frontend/suite/render.ts` | 요약 블록 렌더(링·카드·집계), 1초 시계, 구 진행바 코드 제거 |
| Modify `app/web/frontend/suite/socket.ts` | 끝난 run 재fetch 도 캐시를 거치게(이미 `updateSuiteStepModuleProgress` 경유 — 확인만) |
| Modify `app/web/frontend/entries/suite.ts` | 1초 시계 시작 |
| Modify `app/web/templates/suite.html` | `.suite-sum` 마크업 교체, 모듈 칩 컨테이너 |
| Modify `app/web/frontend/suite/styles.css` | 칩·링·카드·모션 스타일, 구 `.suite-sum__track/fill` 제거 |
| Modify `tests/test_suite_layout.py` | 새 훅 계약 |

---

### Task 1: 순수 계산 모듈 `suite/modules.ts`

**Files:**
- Create: `app/web/frontend/suite/modules.ts`
- Test: `app/web/frontend/suite/modules.test.ts`
- Modify: `app/web/frontend/suite/render.ts` (`SuiteStepLike` 에 `module_total?: number` 추가만)

**Interfaces:**
- Consumes: `orderedSelectedRunModules(run)`, `computeRunModuleProgress(run)` (`suite/progress.ts`), `normalizeTone(status: string): StatusTone` (`components/status-badge/index.ts`), `SuiteLike`/`SuiteStepLike` (`suite/render.ts`).
- Produces:
  ```ts
  export type ModuleChip = { moduleId: string; name: string; tone: StatusTone };
  export function buildModuleChips(run: unknown): ModuleChip[];

  export type SuiteModuleSummary = {
    done: number; total: number; percent: number;          // percent: 0..100 정수
    passed: number; failed: number; blocked: number; remaining: number;
  };
  export function summarizeSuiteModules(steps: SuiteStepLike[], runs: ReadonlyMap<string, unknown>): SuiteModuleSummary;

  export type NowCard =
    | { kind: "running" | "waiting"; systemName: string; moduleName: string; moduleStartedAt: string | null;
        systemIndex: number; systemTotal: number; moduleIndex: number; moduleTotal: number }
    | { kind: "idle" }                                        // 활성 스텝 없음(시작 전)
    | { kind: "finished"; statusLabel: string; passed: number; failed: number };
  export function describeNow(suite: SuiteLike, runs: ReadonlyMap<string, unknown>, summary: SuiteModuleSummary): NowCard;
  ```

- [ ] **Step 1: 실패하는 테스트 작성** — `modules.test.ts`. 헬퍼는 `progress.test.ts` 의 `mods(...)` 패턴을 복사. 상태값은 서버처럼 대문자로.

```ts
describe("buildModuleChips", () => {
  it("order 순, 톤은 normalizeTone, skipped 는 제외", () => {
    const chips = buildModuleChips({ status: "RUNNING", modules: mods(["b","RUNNING"],["a","PASSED"],["s","SKIPPED"],["f","FAILED"]) });
    // mods 는 배열 순서로 order 를 매기므로 b(0) a(1) s(2) f(3)
    expect(chips.map(c => [c.moduleId, c.tone])).toEqual([["b","running"],["a","passed"],["f","anomaly"]]);
  });
});

describe("summarizeSuiteModules", () => {
  it("BLOCKED 를 끝난 것으로 센다 — 실패 run 이 끝나면 100%", () => {
    const runs = new Map([["r1", { status: "ERROR", modules: mods(["a","PASSED"],["b","ERROR"],["c","BLOCKED"],["d","BLOCKED"]) }]]);
    const s = summarizeSuiteModules([{ order: 0, run_id: "r1", status: "ERROR", module_total: 4 }], runs);
    expect(s).toEqual({ done: 4, total: 4, percent: 100, passed: 1, failed: 1, blocked: 2, remaining: 0 });
  });
  it("캐시에 없는 passed 스텝은 module_total 전부 통과로 친다", () => {
    const s = summarizeSuiteModules([{ order: 0, run_id: "r0", status: "PASSED", module_total: 10 }], new Map());
    expect(s.passed).toBe(10); expect(s.percent).toBe(100);
  });
  it("캐시에 없는 비-passed 스텝·대기 스텝은 전부 남음", () => {
    const s = summarizeSuiteModules([{ order: 0, run_id: null, status: "PENDING", module_total: 3 }], new Map());
    expect(s).toMatchObject({ done: 0, total: 3, remaining: 3, percent: 0 });
  });
  it("skipped 스텝은 분모에서 빠지고, 전부 skipped 면 0% (NaN 아님)", () => {
    const s = summarizeSuiteModules([{ order: 0, run_id: null, status: "SKIPPED", module_total: 4 }], new Map());
    expect(s).toMatchObject({ total: 0, percent: 0 });
  });
  it("anomaly 는 failed 에 합산, cancelled 는 done 에만", () => {
    const runs = new Map([["r", { status: "CANCELLED", modules: mods(["a","ANOMALY"],["b","CANCELLED"],["c","PENDING"]) }]]);
    const s = summarizeSuiteModules([{ order: 0, run_id: "r", status: "CANCELLED", module_total: 3 }], runs);
    expect(s).toMatchObject({ done: 2, failed: 1, passed: 0, remaining: 1 });
  });
});

describe("describeNow", () => {
  const steps = [
    { order: 0, system_name: "대표홈페이지(PC)", run_id: "r0", status: "PASSED", module_total: 2 },
    { order: 1, system_name: "대표홈페이지(모바일)", run_id: "r1", status: "RUNNING", module_total: 3 },
    { order: 2, system_name: "현장출동", run_id: null, status: "SKIPPED", module_total: 4 },
  ];
  it("실행 중 모듈을 카드로 — 시스템 순번은 skipped 제외 기준", () => {
    const runs = new Map([["r1", { status: "RUNNING", modules: [
      { module_id: "a", name: "로그인", order: 0, status: "PASSED" },
      { module_id: "b", name: "보험금청구", order: 1, status: "RUNNING", started_at: "2026-10-26T04:00:00Z" },
      { module_id: "c", name: "로그아웃", order: 2, status: "PENDING" } ] }]]);
    const suite = { status: "RUNNING", steps, current_step_index: 1, active_run_id: "r1" };
    expect(describeNow(suite, runs, summarizeSuiteModules(steps, runs))).toEqual({
      kind: "running", systemName: "대표홈페이지(모바일)", moduleName: "보험금청구",
      moduleStartedAt: "2026-10-26T04:00:00Z", systemIndex: 2, systemTotal: 2, moduleIndex: 2, moduleTotal: 3 });
  });
  it("OTP 대기면 waiting", () => {
    const runs = new Map([["r1", { status: "WAITING_INPUT", modules: [{ module_id: "a", name: "로그인", order: 0, status: "WAITING_INPUT" }] }]]);
    const suite = { status: "WAITING_INPUT", steps, current_step_index: 1, awaiting_input_run_id: "r1" };
    expect(describeNow(suite, runs, summarizeSuiteModules(steps, runs))).toMatchObject({ kind: "waiting", moduleName: "로그인" });
  });
  it("수트가 끝나면 finished — 라벨은 statusLabel", () => {
    const suite = { status: "ANOMALY", steps, current_step_index: 2 };
    const summary = { done: 5, total: 5, percent: 100, passed: 4, failed: 1, blocked: 0, remaining: 0 };
    expect(describeNow(suite, new Map(), summary)).toEqual({ kind: "finished", statusLabel: "이상징후", passed: 4, failed: 1 });
  });
});
```

- [ ] **Step 2: 실패 확인** — Run: `npx vitest run app/web/frontend/suite/modules.test.ts` · Expected: FAIL (모듈 없음).

- [ ] **Step 3: 구현** — `modules.ts`.
  - `buildModuleChips`: `orderedSelectedRunModules` 결과를 `{moduleId: module_id, name, tone: normalizeTone(String(status))}` 로 매핑.
  - `summarizeSuiteModules`: 스텝별로 — `skipped` 스텝은 건너뜀. `run_id` 가 캐시에 있으면 그 run 의 칩 톤으로 셈(passed→passed, error/anomaly→failed, blocked→blocked, cancelled→done 만, 나머지→remaining), total 은 칩 개수. 캐시에 없으면 total=`module_total ?? 0`, 스텝 status 가 passed 면 전부 passed, 아니면 전부 remaining. `percent = total ? Math.round(done/total*100) : 0`, `done = passed+failed+blocked+cancelled`.
  - `describeNow`: 수트 status 가 `pending|running|waiting_input` 이 아니면 `finished`(`statusLabel` 은 `statusLabel()` from status-badge, passed/failed 는 summary 값). 활성 run id 는 `resolveActiveSuiteRunId(suite)`(`socket.ts`) 와 같은 규칙 — 순환 import 를 피하려면 그 함수를 `modules.ts` 로 옮기고 `socket.ts` 가 re-export. 활성 스텝 없음 → `idle`. 있으면 `computeRunModuleProgress(run)` 으로 `moduleIndex=current`, `moduleTotal=total`(run 미캐시 시 `module_total`, index 0), `moduleName`, 해당 모듈 `started_at`. `systemIndex` = skipped 제외한 스텝 중 활성 스텝의 1-기반 위치, `systemTotal` = skipped 제외 스텝 수. kind 는 수트 status 가 waiting_input 이거나 progress.tone==="waiting" 이면 `waiting`.

- [ ] **Step 4: 통과 확인** — Run: `npx vitest run app/web/frontend/suite/ && npm run typecheck` · Expected: PASS, 타입 오류 0.

- [ ] **Step 5: Commit**
```bash
git add app/web/frontend/suite/modules.ts app/web/frontend/suite/modules.test.ts app/web/frontend/suite/render.ts app/web/frontend/suite/socket.ts
git commit -m "feat(suite): 모듈 칩·수트 집계·현재 실행 카드 순수 계산"
```

---

### Task 2: 시스템 카드 — 모듈 칩 렌더

**Files:**
- Modify: `app/web/frontend/suite/steps.ts`
- Modify: `app/web/templates/suite.html:81` (`<p data-role="step-module-progress">` → `<ul class="suite-chips" data-role="step-module-progress" hidden></ul>`)
- Modify: `app/web/frontend/suite/styles.css` (칩 스타일, 구 `[data-role="step-module-progress"][data-tone=…]` 색 규칙 제거)
- Test: `app/web/frontend/suite/steps.test.ts`

**Interfaces:**
- Consumes: `buildModuleChips`, `ModuleChip` (Task 1), `formatStepModuleProgressText` (기존, aria-label 용).
- Produces:
  ```ts
  export const suiteRunCache: Map<string, unknown>;            // run_id → 최신 run 페이로드
  export function renderModuleChips(list: HTMLElement, chips: ModuleChip[], runId: string): void;
  ```
  `updateSuiteStepModuleProgress(run)` 는 시그니처 유지 — 이제 캐시에 넣고, 칩을 그리고, `renderSuiteSummary()`(Task 3) 를 부른다. Task 3 전까지는 그 호출 없이 둔다.

- [ ] **Step 1: 실패하는 테스트** — `steps.test.ts` (jsdom).

```ts
const chip = (moduleId: string, tone: StatusTone): ModuleChip => ({ moduleId, name: moduleId, tone });

it("칩마다 li[data-module-id][data-tone], 이름과 run 링크", () => {
  const ul = document.createElement("ul");
  renderModuleChips(ul, [chip("로그인","passed"), chip("메인","error")], "r1");
  const items = [...ul.querySelectorAll("li")];
  expect(items.map(li => [li.dataset.moduleId, li.dataset.tone])).toEqual([["로그인","passed"],["메인","error"]]);
  expect(ul.querySelector("a")?.getAttribute("href")).toBe("/runs/r1");
});
it("첫 렌더에는 pop 이 없다", () => {
  const ul = document.createElement("ul");
  renderModuleChips(ul, [chip("a","running")], "r1");
  expect(ul.querySelector("[data-pop]")).toBeNull();
});
it("톤이 바뀐 칩만 pop, 같은 데이터 재렌더는 pop 없음", () => {
  const ul = document.createElement("ul");
  renderModuleChips(ul, [chip("a","running"), chip("b","pending")], "r1");
  renderModuleChips(ul, [chip("a","passed"), chip("b","pending")], "r1");
  expect([...ul.querySelectorAll("[data-pop]")].map(li => (li as HTMLElement).dataset.moduleId)).toEqual(["a"]);
  renderModuleChips(ul, [chip("a","passed"), chip("b","pending")], "r1");
  expect(ul.querySelector("[data-pop]")).toBeNull();
});
```

- [ ] **Step 2: 실패 확인** — Run: `npx vitest run app/web/frontend/suite/steps.test.ts` · Expected: FAIL.

- [ ] **Step 3: 구현**
  - `renderModuleChips`: 기존 `li` 를 `data-module-id` 로 찾아 직전 톤을 읽고 목록을 새로 만든다. 각 `li.suite-chip[data-module-id][data-tone]` 안에 `<a href="/runs/{runId}">` + 아이콘 span + 이름. 아이콘: passed `✓`, error `✕`, anomaly `!`, blocked `⊘`, waiting_input `OTP`, running 은 `<span class="suite-chip__spin">`, 그 외 없음. blocked 는 이름 뒤 "차단". 이전에 같은 id 가 있었고 톤이 달라졌을 때만 `data-pop` 을 붙이고 `animationend` 에서 제거. 이름은 `textContent` 로(마크업 주입 금지).
  - `updateSuiteStepModuleProgress`: `suiteRunCache.set(runId, run)` → `progressNode` 를 칩 목록으로 렌더, `aria-label` = 기존 `formatStepModuleProgressText(...)`, 칩 0개면 `hidden`. `updateSuiteProgressDetailWithModule` 호출은 Task 3 에서 대체되므로 남겨 둔다.
  - `updateSuiteStepCard` 의 `!step.run_id` 분기: `progressNode.replaceChildren()` + `hidden`.
  - CSS(`suite/styles.css`): `.suite-chips`(flex-wrap, gap .375rem, 목록 리셋), `.suite-chip`(pill, 0.75rem, 테두리 `--pl-border`, 텍스트 `--pl-text-subtle`), 톤별 `[data-tone="X"]` → `background: var(--st-X-surface); border-color: var(--st-X-border); color: var(--st-X-text)` (passed·error·anomaly·running·waiting_input), blocked → `border-style: dashed` + subtle 색, cancelled → `text-decoration: line-through`. running 칩 pulse 링 keyframes, 스피너 keyframes, `[data-pop]` pop keyframes(scale .85→1, 250ms). reduced-motion 블록에서 셋 다 `animation: none`.

- [ ] **Step 4: 통과 확인** — Run: `npm test && npm run typecheck && npm run lint && python -m pytest tests/test_suite_layout.py -q` · Expected: 전부 PASS (`step-module-progress` 훅 유지).

- [ ] **Step 5: Commit**
```bash
git add app/web/frontend/suite/steps.ts app/web/frontend/suite/steps.test.ts app/web/templates/suite.html app/web/frontend/suite/styles.css
git commit -m "feat(suite): 시스템 카드에 모듈 칩 표시"
```

---

### Task 3: 상단 요약 — 링 + "지금 실행 중" 카드 + 집계 줄

**Files:**
- Modify: `app/web/templates/suite.html:55-66` (`.suite-sum` 내용 교체)
- Modify: `app/web/frontend/suite/render.ts` (`updateSuiteProgress`·`updateSuiteProgressDetailWithModule` 대체)
- Modify: `app/web/frontend/suite/steps.ts` (`updateSuiteProgressDetailWithModule` 호출 → `renderSuiteSummary()`)
- Modify: `app/web/frontend/entries/suite.ts` (시계 시작)
- Modify: `app/web/frontend/suite/styles.css`
- Modify: `tests/test_suite_layout.py` (`test_js_hooks_survive` 훅 목록)
- Test: `app/web/frontend/suite/render.test.ts` (create)

**Interfaces:**
- Consumes: `summarizeSuiteModules`, `describeNow`, `NowCard` (Task 1), `suiteRunCache` (Task 2), `passRateToDegrees(passed, total)` (`components/status-hero/index.ts`), 기존 `updateSuiteEtaBlock`, `formatClock`.
- Produces:
  ```ts
  export function renderSuiteSummary(): void;          // 마지막 스냅샷 + suiteRunCache 로 링·카드·집계 갱신
  export function startSuiteClock(): void;             // setInterval 1000ms → 경과·모듈 경과·ETA 갱신
  export function animateCount(node: HTMLElement, to: number): void;
  ```
  `renderSuiteSnapshot(suite)` 는 스냅샷을 모듈 변수 `lastSuite` 에 저장하고 `renderSuiteSummary()` 를 부른다.

새 마크업 훅(템플릿 — 서버 첫 페인트는 0% / 빈 카드):
```
section.suite-sum
  div.suite-ring#suite-ring  (style="--ring-deg:0deg")  > span.suite-ring__value#suite-ring-value "0" + span.suite-ring__unit "% 완료"
  div.suite-now#suite-now[data-kind]  > p.suite-now__eyebrow#suite-now-eyebrow · p.suite-now__title#suite-now-title · p.suite-now__meta#suite-now-meta
  p.suite-counts#suite-counts > span#suite-count-passed · span#suite-count-failed · span#suite-count-blocked · span#suite-count-remaining · span#suite-progress-elapsed · span#suite-progress-eta
```

카드 문구(kind 별):
| kind | eyebrow | title | meta |
| --- | --- | --- | --- |
| running | `지금 실행 중 · {m:ss}` (moduleStartedAt 없으면 `지금 실행 중`) | `{시스템} › {모듈}` (모듈명 없으면 시스템만) | `시스템 {i}/{n} · 모듈 {j}/{m}` |
| waiting | `OTP 입력 대기` | 동일 | 동일 |
| idle | `시작 대기 중` | `—` | 빈 문자열 |
| finished | `{statusLabel}` | `통과 {passed} · 실패 {failed}` | 빈 문자열 |

- [ ] **Step 1: 실패하는 테스트** — `render.test.ts` (jsdom). `beforeEach` 에서 위 마크업을 `document.body.innerHTML` 로 심고 `matchMedia` 를 reduce=true 로 스텁(카운트업 즉시 반영).

```ts
it("스냅샷 + 캐시로 링·집계·카드를 채운다", () => {
  suiteRunCache.set("r1", { status: "RUNNING", modules: [
    { module_id: "a", name: "로그인", order: 0, status: "PASSED" },
    { module_id: "b", name: "보험금청구", order: 1, status: "RUNNING" } ] });
  renderSuiteSnapshot({ status: "RUNNING", current_step_index: 0, active_run_id: "r1",
    steps: [{ order: 0, system_name: "모바일", system_code: "mhm", run_id: "r1", status: "RUNNING", module_total: 2 }] });
  expect(byId("suite-ring-value").textContent).toBe("50");
  expect(byId("suite-ring").style.getPropertyValue("--ring-deg")).toBe("180deg");
  expect(byId("suite-now").dataset.kind).toBe("running");
  expect(byId("suite-now-title").textContent).toBe("모바일 › 보험금청구");
  expect(byId("suite-count-passed").textContent).toBe("✓ 1 통과");
  expect(byId("suite-count-blocked").hidden).toBe(true);
});
it("차단이 있으면 차단 칸을 보인다", () => { /* modules 에 BLOCKED 하나 → "⊘ 1 차단", hidden=false */ });
it("끝나면 finished 카드", () => { /* status: "PASSED" → data-kind="finished", eyebrow "정상" */ });
```

- [ ] **Step 2: 실패 확인** — Run: `npx vitest run app/web/frontend/suite/render.test.ts` · Expected: FAIL.

- [ ] **Step 3: 구현**
  - 템플릿: 위 마크업으로 교체. `suite-progress-label`·`suite-progress-bar`·`suite-progress-detail` 삭제.
  - `render.ts`: `updateSuiteProgress` 를 `renderSuiteSummary` 로 대체(구 진행바·라벨·detail 코드 삭제, `updateSuiteEtaBlock` 은 유지하고 거기서 호출). `updateSuiteProgressDetailWithModule` 삭제. 링: `--ring-deg = passRateToDegrees(done, total)deg`, `data-tone` 없이 passed 색. 값 노드는 `animateCount`. 집계 칸 텍스트는 Global Constraints 문구 그대로(각 칸 개별 span, 사이 구분자는 CSS `::before " · "`).
  - `animateCount(node, to)`: 이전 값(`node.dataset.value`)에서 `to` 로 ~600ms easeOutCubic `requestAnimationFrame`; `matchMedia("(prefers-reduced-motion: reduce)").matches` 이거나 값이 같으면 즉시 대입.
  - `startSuiteClock()`: `setInterval(() => lastSuite && renderSuiteSummary(), 1000)`. 카운트업은 값이 같으면 즉시 대입이므로 매초 재렌더해도 움직이지 않는다. `entries/suite.ts` 의 DOMContentLoaded 에서 호출.
  - `steps.ts`: `updateSuiteStepModuleProgress` 끝에서 `renderSuiteSummary()` 호출.
  - CSS: `@property --ring-deg { syntax: "<angle>"; inherits: false; initial-value: 0deg; }` + `.suite-ring` 은 `status-hero__ring` 과 같은 conic-gradient 도넛(`--st-passed-solid` / `--pl-border`, 지름 6.5rem), `transition: --ring-deg .8s var(--ease-out)`. `.suite-sum` 을 grid(링 | 카드, 아래 집계 줄 전폭). `.suite-now` 기본 `--st-running-surface/border`, eyebrow 앞 라이브 점(pulse), `[data-kind="waiting"]` → waiting_input 토큰, `[data-kind="finished"|"idle"]` → `--pl-bg`/`--pl-border` + 라이브 점 숨김. 숫자 `font-variant-numeric: tabular-nums`. reduced-motion: ring transition·pulse 끔. 구 `.suite-sum__head/__label/__track/__fill/__foot` 규칙 삭제.
  - `tests/test_suite_layout.py::test_js_hooks_survive`: `id="suite-ring"`, `id="suite-now"`, `id="suite-counts"`, `id="suite-progress-elapsed"`, `id="suite-progress-eta"` 추가.

- [ ] **Step 4: 통과 확인** — Run: `npm test && npm run typecheck && npm run lint && python -m pytest tests/test_suite_layout.py -q` · Expected: 전부 PASS. `grep -rn "suite-progress-label\|suite-progress-bar\|suite-progress-detail\|updateSuiteProgressDetailWithModule" app/` → 결과 없음.

- [ ] **Step 5: Commit**
```bash
git add app/web/templates/suite.html app/web/frontend/suite/ app/web/frontend/entries/suite.ts tests/test_suite_layout.py
git commit -m "feat(suite): 상단 요약을 진행 링·현재 실행 카드로 교체"
```

---

### Task 4: 전체 게이트 + 화면 확인

- [ ] **Step 1:** `python3 scripts/ci/run_all_gates.py --profile full` (백그라운드) · Expected: 전체 PASS. 실패 시 출력 그대로 보고.
- [ ] **Step 2:** `.agents/skills/e2e-browser/SKILL.md` 를 읽고 그 절차로 수트 화면을 띄워 확인: 실행 중 칩 pulse·스피너, 상태 전환 pop(같은 칩 반복 pop 없음), 링 차오름, 카드 모듈 경과 1초 갱신, OTP 대기 시 카드 노란 톤, 종료 후 결과 카드. 실사이트 수트를 돌릴 수 없으면 그 사실을 보고하고 jsdom 테스트 결과만으로 대체했음을 명시.
- [ ] **Step 3:** 문서 — `docs/DOCS_GOVERNANCE.md` 의 PR DoD 확인 후 필요하면 설계 문서 상태를 "구현 완료"로 갱신하고 커밋.
