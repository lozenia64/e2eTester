# Cycle 3: 런 상세 승격 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 런 상세를 넌스크롤 2열(좌 모듈 / 우 로그)로 승격하고, `app.js` 의 런 상세 몫 약 531줄을 `entries/run.ts` 로 이관한다.

**Architecture:** **서버는 한 줄도 바뀌지 않는다** — 순수 프런트엔드 사이클이다(설계 D4). 순수 로직(초점 계산·로그 상한)을 먼저 세워 Vitest 로 잠그고, 그 위에 DOM 모듈을 얹은 뒤, 마지막에 **전환**(템플릿 재작성 + 배선 + `app.js` 절단)을 한 커밋으로 원자적으로 끝낸다. Cycle 1b·2 가 세운 화면 폴더 관례를 그대로 따르므로 새로 정할 구조는 없다.

**Tech Stack:** TypeScript 5.6 · Vite 6 다중 엔트리 · Vitest 3 + jsdom · Jinja2 · Tailwind v4 · pytest + Playwright

**Spec:** `docs/superpowers/specs/2026-08-31-run-detail-promotion-design.md`

## Global Constraints

- **서버 변경 0줄.** `app/` 아래 파이썬을 건드리지 않는다. `snapshot_validate` · `projection_validate` diff 0(설계 D4·§2.2).
- **스크롤 소유권은 "열마다 하나"**(설계 D2) — 좌우로 분할된 열은 각자 하나씩 가질 수 있다. **세로로 쌓인 영역은 여전히 하나뿐이다.**
- **색 SSOT 는 `app/core/status_colors.py` 의 `PALETTE`.** 새 hex 를 적지 않는다. FG-002 가 `templates/`·`static/*.js` 까지 스캔한다.
- **상태 라벨·톤은 서버 주입만**(FG-003 · FG-006). 배지는 `components/status-badge` 를 쓴다.
- **`/static/` 직접 참조 금지**(FG-005). 자산은 `_assets.html` 매크로 경유.
- **파일 400줄 상한**(FG-004).
- **신규 다리 0개.** `run/` 은 `window.__execute*` 를 참조하지 않는다. `setInlineFeedback`·`readErrorMessage` 는 지역 복제한다(설계 §3.4).
- **`is_visible()` 로 가시성을 단언하지 않는다.** `bounding_box()` 좌표로 단언한다.
- **로그 상한은 표시에만 건다.** 복사·다운로드는 전량 대상(설계 D3).
- **UI 문자열은 한국어**(AGENTS.md).
- **문서 커밋 전 `python -m ruff format --check .`** — 마크다운 안 Python 코드블록도 검사 대상이다(Cycle 2 에서 두 번 게이트를 깼다).
- **PR 전 필수:** `python3 scripts/ci/run_all_gates.py --profile full`

## File Structure

| 파일 | 책임 | 상태 |
| --- | --- | --- |
| `app/web/frontend/run/focus.ts` | 초점 모듈 계산(순수) | **신규** |
| `app/web/frontend/run/log.ts` | 로그 수집·필터·렌더·상한·내보내기 | **신규** |
| `app/web/frontend/run/modules.ts` | 모듈 카드 DOM · 초점 반영 | **신규** |
| `app/web/frontend/run/progress.ts` | 진행 바 · 경과 타이머 | **신규** |
| `app/web/frontend/run/actions.ts` | 취소·재실행·OTP 제출 | **신규** |
| `app/web/frontend/run/socket.ts` | 런 WS · 비교 칩 갱신 | **신규** |
| `app/web/frontend/run/styles.css` | 화면 CSS | **신규** |
| `app/web/frontend/entries/run.ts` | 배선만 | **신규** |
| `app/web/frontend/styles/shell.css` | `.run` 셀렉터 추가 | 수정 |
| `app/web/templates/run.html` | 마크업 전면 재작성 | 수정 |
| `app/web/static/app.js` | 런 상세 몫 ~531줄 삭제 | 수정 |
| `app/web/frontend/entries/main.ts` | `window.__executeOtpPanel` 제거 | 수정 |
| `app/web/frontend/execute/legacy-bridge.ts` | 해당 타입 선언 제거 | 수정 |
| `vite.config.ts` | `run` 엔트리 등록 | 수정 |

---

### Task 1: 초점 계산 (순수)

설계 D4 의 핵심. 서버가 아니라 여기가 규칙의 **유일한** 소유자다.

**Files:**
- Create: `app/web/frontend/run/focus.ts`
- Create: `app/web/frontend/run/focus.test.ts`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `type FocusModule = { module_id: string; order: number; status: string }`
  - `computeFocusModuleId(modules: FocusModule[]): string | null`
  - Task 5(`modules.ts`)·Task 6(`socket.ts`)이 소비한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`app/web/frontend/run/focus.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { computeFocusModuleId } from "./focus";

const m = (...specs: Array<[string, string]>) =>
  specs.map(([module_id, status], order) => ({ module_id, order, status }));

describe("computeFocusModuleId", () => {
  it("error 가 최우선이다", () => {
    expect(
      computeFocusModuleId(m(["a", "passed"], ["b", "anomaly"], ["c", "error"], ["d", "running"])),
    ).toBe("c");
  });

  it("error 가 여럿이면 order 가 가장 앞선 것", () => {
    expect(computeFocusModuleId(m(["a", "error"], ["b", "error"]))).toBe("a");
  });

  it("error 가 없으면 첫 anomaly", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "anomaly"], ["c", "running"]))).toBe("b");
  });

  it("둘 다 없으면 첫 running", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "running"], ["c", "pending"]))).toBe("b");
  });

  it("waiting_input 도 현재 모듈로 본다 — OTP 대기는 사람이 볼 자리다", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "waiting_input"]))).toBe("b");
  });

  it("전부 정상이면 null", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "passed"]))).toBeNull();
  });

  it("아직 시작 전이면 null", () => {
    expect(computeFocusModuleId(m(["a", "pending"], ["b", "pending"]))).toBeNull();
  });

  it("모듈이 없으면 null 이고 던지지 않는다", () => {
    expect(computeFocusModuleId([])).toBeNull();
  });

  it("order 가 배열 순서와 다르면 order 를 따른다", () => {
    const shuffled = [
      { module_id: "late", order: 5, status: "error" },
      { module_id: "early", order: 1, status: "error" },
    ];
    expect(computeFocusModuleId(shuffled)).toBe("early");
  });

  it("상태 대소문자가 섞여도 같게 판정한다", () => {
    expect(computeFocusModuleId(m(["a", "PASSED"], ["b", "ERROR"]))).toBe("b");
  });

  it("건너뛴 모듈은 초점이 되지 않는다", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "skipped"], ["c", "passed"]))).toBeNull();
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npm run test -- focus`
Expected: FAIL — `Cannot find module './focus'`

- [ ] **Step 3: 구현한다**

`app/web/frontend/run/focus.ts`:

```typescript
// 어느 모듈에 초점을 둘 것인가 — Run 모듈 상태의 순수 함수(설계 §3.2·D4).
//
// 규칙의 소유자는 여기 하나뿐이다. 서버가 아니라 클라이언트가 갖는 이유는
// RunView.dump_from_summary 가 modules=[] 로 비우기 때문이다 — 초점이 바뀌는
// 계기(모듈 상태 변화)가 모듈 단위 이벤트로 오므로 서버는 snapshot 에서만
// 계산할 수 있고, 그러면 서버·클라이언트 두 벌이 된다.

export type FocusModule = { module_id: string; order: number; status: string };

const ERROR = "error";
const ANOMALY = "anomaly";
const CURRENT = new Set(["running", "waiting_input"]);

function firstBy(modules: FocusModule[], match: (status: string) => boolean): string | null {
  const hit = [...modules]
    .sort((left, right) => left.order - right.order)
    .find((module) => match(String(module.status).toLowerCase()));
  return hit ? hit.module_id : null;
}

export function computeFocusModuleId(modules: FocusModule[]): string | null {
  if (!modules.length) return null;
  return (
    firstBy(modules, (s) => s === ERROR) ??
    firstBy(modules, (s) => s === ANOMALY) ??
    firstBy(modules, (s) => CURRENT.has(s))
  );
}
```

- [ ] **Step 4: 통과 확인**

Run: `npm run test -- focus && npm run typecheck && npm run lint`
Expected: PASS (11 tests)

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/run/focus.ts app/web/frontend/run/focus.test.ts
git commit -m "feat(run): 초점 모듈 계산 — 규칙의 단일 소유자"
```

---

### Task 2: 로그 저장소와 상한

설계 D3. 표시는 자르고 내보내기는 자르지 않는다.

**Files:**
- Create: `app/web/frontend/run/log.ts`
- Create: `app/web/frontend/run/log.test.ts`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `type LogEntry = { moduleId: string; message: string }`
  - `resetLog(entries: LogEntry[]): void` — 스냅샷에서 전량 교체
  - `pushLog(entry: LogEntry): void`
  - `setModuleFilter(moduleId: string, opts?: { manual?: boolean }): void`
  - `setSearch(term: string): void`
  - `isFilterManual(): boolean`
  - `visibleEntries(): LogEntry[]` — 필터 적용 + **최근 2,000줄**
  - `hiddenCount(): number` — 상한에 잘린 줄 수
  - `exportText(): string` — 필터는 적용, **상한은 적용하지 않음**
  - Task 6(`socket.ts`)과 Task 7(전환)이 소비한다

- [ ] **Step 1: 원본을 읽는다**

`app/web/static/app.js:907~1050` 의 `logEntryMatchesFilters` · `formatLogLine` · `createLogLineNode` · `renderLogConsole` · `appendLogEntry` · `loadLogEntriesFromRun` · `logExportText` · `currentRunId` · `copyLogsToClipboard` · `downloadLogs` · `bindLogControls` 를 읽는다. 필터가 **모듈 선택 + 검색어** 두 축이라는 것과, `appendLogEntry` 가 `nearBottom` 일 때만 자동 스크롤한다는 것을 확인한다(그 동작은 유지한다).

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`app/web/frontend/run/log.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import {
  exportText,
  hiddenCount,
  isFilterManual,
  pushLog,
  resetLog,
  setModuleFilter,
  setSearch,
  visibleEntries,
} from "./log";

const line = (moduleId: string, message: string) => ({ moduleId, message });

beforeEach(() => {
  resetLog([]);
  setModuleFilter("", { manual: false });
  setSearch("");
});

describe("필터", () => {
  it("모듈로 좁힌다", () => {
    resetLog([line("a", "hello"), line("b", "world")]);
    setModuleFilter("a");
    expect(visibleEntries().map((e) => e.message)).toEqual(["hello"]);
  });

  it("검색어는 대소문자를 가리지 않는다", () => {
    resetLog([line("a", "TimeoutError"), line("a", "ok")]);
    setSearch("timeout");
    expect(visibleEntries()).toHaveLength(1);
  });

  it("모듈과 검색어가 함께 걸린다", () => {
    resetLog([line("a", "boom"), line("b", "boom")]);
    setModuleFilter("b");
    setSearch("boom");
    expect(visibleEntries()).toHaveLength(1);
  });
});

describe("자동/수동 필터", () => {
  it("기본은 자동이다", () => {
    expect(isFilterManual()).toBe(false);
  });

  it("사용자가 바꾸면 수동이 된다", () => {
    setModuleFilter("a", { manual: true });
    expect(isFilterManual()).toBe(true);
  });

  it("수동으로 바뀐 뒤에도 자동 호출은 값을 덮지 않는다", () => {
    setModuleFilter("a", { manual: true });
    setModuleFilter("b");
    expect(visibleEntries).toBeDefined();
    expect(isFilterManual()).toBe(true);
    resetLog([line("a", "keep"), line("b", "drop")]);
    expect(visibleEntries().map((e) => e.message)).toEqual(["keep"]);
  });
});

describe("표시 상한 2,000줄", () => {
  const many = (n: number) => Array.from({ length: n }, (_, i) => line("a", `line-${i}`));

  it("2,000줄을 넘으면 최근 것만 보인다", () => {
    resetLog(many(2500));
    expect(visibleEntries()).toHaveLength(2000);
    expect(visibleEntries()[0].message).toBe("line-500");
  });

  it("잘린 줄 수를 센다", () => {
    resetLog(many(2500));
    expect(hiddenCount()).toBe(500);
  });

  it("2,000줄 이하면 아무것도 안 자른다", () => {
    resetLog(many(10));
    expect(hiddenCount()).toBe(0);
  });

  it("상한은 필터 적용 뒤에 걸린다", () => {
    resetLog([...many(2500), line("z", "other")]);
    setModuleFilter("z");
    expect(visibleEntries()).toHaveLength(1);
    expect(hiddenCount()).toBe(0);
  });
});

describe("내보내기", () => {
  it("상한을 적용하지 않는다 — 조사 도구의 본질", () => {
    resetLog(Array.from({ length: 2500 }, (_, i) => line("a", `L${i}`)));
    expect(exportText().split("\n")).toHaveLength(2500);
  });

  it("필터는 적용한다", () => {
    resetLog([line("a", "keep"), line("b", "drop")]);
    setModuleFilter("a");
    expect(exportText()).toBe("[a] keep");
  });
});

describe("추가", () => {
  it("push 한 줄이 보인다", () => {
    resetLog([]);
    pushLog(line("a", "first"));
    expect(visibleEntries()).toHaveLength(1);
  });
});
```

`exportText()` 의 줄 형식(`[a] keep`)은 원본 `formatLogLine`(`app.js:917`)이 만드는 것과 **같아야 한다.** Step 1 에서 읽은 실제 형식에 기대값을 맞춘다 — 다르면 테스트가 아니라 기대값을 고친다.

- [ ] **Step 3: 실패를 확인한다**

Run: `npm run test -- log`
Expected: FAIL — 모듈 없음

- [ ] **Step 4: 구현한다**

`app/web/frontend/run/log.ts` 를 만든다. 원본 로직을 옮기되 DOM 을 모르는 **저장소 계층**으로 한정한다 — 렌더는 Task 7 의 화면 코드가 맡는다.

```typescript
// 실행 로그 저장소 — 필터·상한·내보내기. DOM 을 모른다(설계 §3.3).
//
// 상한은 표시에만 건다. 복사·다운로드는 전량을 대상으로 한다 — 조사 도구의
// 본질이라 잘라내면 안 된다.

const DISPLAY_CAP = 2000;
```

`isFilterManual()` 이 `true` 인 동안 `setModuleFilter(id)`(manual 생략)는 **아무 일도 하지 않는다**(설계 D7).

- [ ] **Step 5: 통과 확인**

Run: `npm run test -- log && npm run typecheck && npm run lint`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/web/frontend/run/log.ts app/web/frontend/run/log.test.ts
git commit -m "feat(run): 로그 저장소 — 표시 2,000줄 상한, 내보내기는 전량"
```

---

### Task 3: 진행 계산

**Files:**
- Create: `app/web/frontend/run/progress.ts`
- Create: `app/web/frontend/run/progress.test.ts`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `formatClock(milliseconds: number): string`
  - `summarizeModules(modules: Array<{ status: string }>): { passed: number; failed: number; total: number; percent: number }`
  - Task 6(`socket.ts` 의 `renderProgress`·`startRuntimeTicker`)이 소비한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```typescript
import { describe, expect, it } from "vitest";
import { formatClock, summarizeModules } from "./progress";

describe("formatClock", () => {
  it("분:초로 찍는다", () => {
    expect(formatClock(65_000)).toBe("01:05");
  });

  it("0 도 형식을 지킨다", () => {
    expect(formatClock(0)).toBe("00:00");
  });

  it("한 시간을 넘으면 분이 60을 넘어간다", () => {
    expect(formatClock(3_725_000)).toBe("62:05");
  });

  it("음수는 00:00 으로 눕힌다", () => {
    expect(formatClock(-5_000)).toBe("00:00");
  });
});

describe("summarizeModules", () => {
  const mods = (...s: string[]) => s.map((status) => ({ status }));

  it("통과·실패를 센다", () => {
    const r = summarizeModules(mods("passed", "passed", "error", "pending"));
    expect(r.passed).toBe(2);
    expect(r.failed).toBe(1);
    expect(r.total).toBe(4);
  });

  it("anomaly 도 실패로 센다", () => {
    expect(summarizeModules(mods("anomaly")).failed).toBe(1);
  });

  it("skipped 는 분모에서 뺀다", () => {
    const r = summarizeModules(mods("passed", "skipped"));
    expect(r.total).toBe(1);
  });

  it("모듈이 없으면 percent 가 0 이고 나눗셈이 터지지 않는다", () => {
    expect(summarizeModules([]).percent).toBe(0);
  });
});
```

`formatClock` 의 실제 출력 형식은 `app.js:1052` 를 읽고 맞춘다. 다르면 기대값을 고친다.

- [ ] **Step 2: 실패를 확인한다**

Run: `npm run test -- progress`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 구현한다**

`app.js:1052`(`formatClock`)와 `:1066`(`updateRunProgress`)의 계산 부분을 옮긴다. DOM 접근은 넣지 않는다 — `updateRunProgress` 의 DOM 부분은 Task 7 이 화면 코드로 가져간다.

- [ ] **Step 4: 통과 확인**

Run: `npm run test -- progress && npm run typecheck && npm run lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/run/progress.ts app/web/frontend/run/progress.test.ts
git commit -m "feat(run): 진행 계산과 경과 형식"
```

---

### Task 4: 셸에 `.run` 추가

Cycle 2 가 D7 로 공통 추출해 둔 것을 한 줄로 재사용한다.

**Files:**
- Modify: `app/web/frontend/styles/shell.css`
- Test: `tests/frontend/test_shell_css_ownership.py`

**Interfaces:**
- Consumes: 없음
- Produces: `body:has(.run)` 넌스크롤 셸. Task 7 의 `run.html` 이 `.run` 을 붙여 소비한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/frontend/test_shell_css_ownership.py` 의 파라미터에 `.run` 을 추가한다.

```python
@pytest.mark.parametrize(
    "selector",
    ["body:has(.dash)", "body:has(.exec)", "body:has(.suite)", "body:has(.run)"],
)
def test_shell_owns_all_screens(selector: str) -> None:
    assert selector in _text("shell.css")
```

기존 테스트 함수명이 `test_shell_owns_all_three_screens` 이면 `_all_screens` 로 바꾼다 — 네 개가 됐으므로 이름이 거짓이 된다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_shell_css_ownership.py -v`
Expected: FAIL — `body:has(.run)` 없음

- [ ] **Step 3: 셀렉터를 추가한다**

`shell.css` 의 셀렉터 목록 **모든 블록**에 `body:has(.run)` 을 넣는다. 루트 블록 하나만 고치고 `main` · `main > div` · 미디어쿼리 블록을 빠뜨리면 셸이 절반만 걸린다.

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/frontend/test_shell_css_ownership.py tests/test_dashboard_viewport.py tests/test_execute_viewport.py tests/test_suite_viewport.py -v`
Expected: PASS. 셀렉터만 추가했으므로 기존 세 화면이 한 건도 바뀌면 안 된다.

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/styles/shell.css tests/frontend/test_shell_css_ownership.py
git commit -m "feat(styles): 넌스크롤 셸에 런 상세 추가 — 네 번째 소비자"
```

---

### Task 5: 모듈 카드 DOM

**Files:**
- Create: `app/web/frontend/run/modules.ts`
- Create: `app/web/frontend/run/modules.test.ts`

**Interfaces:**
- Consumes: Task 1 의 `computeFocusModuleId`, 기존 `components/status-badge`
- Produces:
  - `updateModuleCard(module: unknown): void`
  - `applyFocus(root?: ParentNode): string | null` — DOM 의 모듈 상태를 읽어 초점을 계산하고 `data-focus="true"` 를 한 곳에만 세운다. 계산된 `module_id` 를 돌려준다
  - Task 6(`socket.ts`)·Task 7(`entries/run.ts`)이 소비한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import { applyFocus } from "./modules";

function host(...specs: Array<[string, string]>) {
  document.body.innerHTML = specs
    .map(
      ([id, status], order) =>
        `<li class="run-mod" data-module-id="${id}" data-order="${order}" data-status="${status}"></li>`,
    )
    .join("");
  return document.body;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("applyFocus", () => {
  it("초점 모듈에만 data-focus 를 세운다", () => {
    host(["a", "passed"], ["b", "error"], ["c", "pending"]);
    expect(applyFocus()).toBe("b");
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(1);
    expect(document.querySelector('[data-focus="true"]')!.getAttribute("data-module-id")).toBe("b");
  });

  it("초점이 옮겨가면 이전 것을 지운다", () => {
    host(["a", "running"], ["b", "pending"]);
    applyFocus();
    document.querySelector('[data-module-id="a"]')!.setAttribute("data-status", "passed");
    document.querySelector('[data-module-id="b"]')!.setAttribute("data-status", "error");
    expect(applyFocus()).toBe("b");
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(1);
  });

  it("초점이 없으면 아무것도 세우지 않는다", () => {
    host(["a", "passed"], ["b", "passed"]);
    expect(applyFocus()).toBeNull();
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(0);
  });

  it("모듈이 없어도 던지지 않는다", () => {
    expect(applyFocus()).toBeNull();
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npm run test -- modules`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 구현한다**

`app.js:853`(`updateModuleCard`)·`:1059`(`rememberModuleState`)를 옮기고 `applyFocus` 를 새로 쓴다. `applyFocus` 는 DOM 의 `data-status` 를 읽어 `computeFocusModuleId` 에 넘긴다 — 서버 값을 기다리지 않는다(설계 D4).

`updateModuleCard` 가 상태를 갱신한 뒤에는 **반드시 `applyFocus()` 를 호출**해야 초점이 낡지 않는다.

- [ ] **Step 4: 통과 확인**

Run: `npm run test && npm run typecheck && npm run lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/web/frontend/run/modules.ts app/web/frontend/run/modules.test.ts
git commit -m "feat(run): 모듈 카드 DOM 과 초점 반영"
```

---

### Task 6: 액션·소켓

**Files:**
- Create: `app/web/frontend/run/actions.ts`
- Create: `app/web/frontend/run/socket.ts`

**Interfaces:**
- Consumes: Task 1(`computeFocusModuleId`) · Task 2(`resetLog`·`pushLog`·`setModuleFilter`) · Task 3(`formatClock`·`summarizeModules`) · Task 5(`updateModuleCard`·`applyFocus`), `components/otp-panel` 의 `updateOtpPanel`, `lib/otp-countdown`
- Produces:
  - `bindRunActions(): void` · `bindOtpForm(): void` (`actions.ts`)
  - `bindRunSocket(): void` · `renderProgress(): void` · `startRuntimeTicker(): void` (`socket.ts`)
  - Task 7 의 `entries/run.ts` 가 이들을 부른다

- [ ] **Step 1: 옮긴다**

| 파일 | 옮길 함수 (`app.js` 줄) |
| --- | --- |
| `actions.ts` | `otpFeedbackNode`(1141) · `submitOtp`(1145) · `bindOtpForm`(1177) · `updateRunActions`(1198) · `cancelRun`(1215) · `rerunRun`(1234) · `bindRunActions`(1252) |
| `socket.ts` | `bindRunSocket`(1264) · `updateComparisonPanel`(1329) |

**다리를 쓰지 않는다.** `window.__executeOtpPanel?.updateOtpPanel(...)` 세 자리(`app.js:1285·1313·1320`)는 `components/otp-panel` 에서 **직접 import** 로 바꾼다. `window.__statusBadge` 도 `components/status-badge` 직접 import 로 바꾼다.

`setInlineFeedback` · `readErrorMessage` 는 `run/` 안에 **지역 복제**한다(설계 §3.4). `app.js` 원본은 그대로 두고 Cycle 4 가 지운다.

- [ ] **Step 2: 소켓 핸들러에 초점·필터를 연결한다**

`bindRunSocket` 안에서:

- `snapshot` 이벤트 → 모듈 전량 갱신 후 `applyFocus()`
- `message.payload.module` 이 있는 모든 이벤트 → `updateModuleCard` 후 `applyFocus()`
- `applyFocus()` 가 돌려준 `module_id` 로 `setModuleFilter(id)` 를 부른다 — **manual 플래그 없이** 부르므로 사용자가 필터를 손댔으면 무시된다(설계 D7)
- 같은 자리에서 `renderProgress()` 도 부른다. `renderProgress` 는 DOM 의 모듈 상태를 모아 Task 3 의 `summarizeModules` 에 넘기고 `#run-progress-bar`·`#run-progress-label` 을 갱신한다
- `module_log` 이벤트 → `pushLog({moduleId, message})` 후 로그 콘솔에 한 줄 덧붙인다. `snapshot` 이벤트 → `resetLog(...)` 로 전량 교체
- `startRuntimeTicker()` 는 `app.js:1101`(`tickRunningElapsed`)·`:1124` 를 옮긴 것으로, 1초마다 경과를 `formatClock` 으로 찍는다

- [ ] **Step 3: 확인한다**

Run: `npm run typecheck && npm run lint && npm run test`
Expected: PASS. 아직 어떤 화면도 부르지 않으므로 동작 변화는 없다.

Run: `grep -rn "__execute" app/web/frontend/run/`
Expected: 출력 없음(신규 다리 0)

FG-004 로 400줄을 넘으면 책임 단위로 쪼갠다.

- [ ] **Step 4: 커밋**

```bash
git add app/web/frontend/run
git commit -m "feat(run): 액션·소켓 모듈 — 다리 대신 직접 import"
```

---

### Task 7: 전환 — 템플릿·스타일·배선·`app.js` 절단

한 커밋에 묶는다. 마크업만 바꾸면 옛 JS 가 훅을 못 찾고, JS 만 바꾸면 옛 마크업이 안 맞는다.

**Files:**
- Create: `app/web/frontend/run/styles.css`
- Create: `app/web/frontend/entries/run.ts`
- Modify: `app/web/templates/run.html` (전면 재작성)
- Modify: `app/web/frontend/entries/main.ts` · `app/web/frontend/execute/legacy-bridge.ts`
- Modify: `vite.config.ts` · `app/web/static/app.js`
- Test: `tests/test_run_layout.py`

**Interfaces:**
- Consumes: Task 1~6 전부
- Produces: 완성된 화면

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_run_layout.py`. 픽스처는 `tests/test_suite_layout.py`(Cycle 2)를 따르고 라우트만 `GET /runs/{id}` 로 바꾼다.

```python
def test_root_carries_the_run_shell_class(client) -> None:
    assert 'class="run' in _html(client)


def test_two_column_layout(client) -> None:
    html = _html(client)
    assert 'id="run-module-list"' in html
    assert 'id="log-console"' in html
    assert "md:grid-cols-2 xl:grid-cols-3" not in html


def test_comparison_is_a_header_chip_not_a_section(client) -> None:
    """설계 D6 — 전용 섹션을 쌓으면 넌스크롤 예산이 깨진다."""
    html = _html(client)
    assert 'id="comparison-panel"' not in html
    assert 'data-role="comparison-chip"' in html


def test_module_rows_carry_focus_inputs(client) -> None:
    """applyFocus 가 DOM 에서 읽는 값들."""
    html = _html(client)
    assert "data-module-id=" in html
    assert "data-order=" in html
    assert "data-status=" in html


def test_js_hooks_survive(client) -> None:
    html = _html(client)
    for hook in (
        'id="run-status"',
        'id="run-cancel"',
        'id="run-rerun"',
        'id="run-progress-bar"',
        'id="otp-panel"',
        'id="otp-form"',
        'id="otp-countdown"',
        'id="log-console"',
        'id="log-filter"',
        'id="log-search"',
        'id="log-copy"',
        'id="log-download"',
        'data-role="failure-analysis"',
        'data-role="module-artifacts-list"',
    ):
        assert hook in html, hook


def test_no_tailwind_color_utilities(client) -> None:
    import re

    html = _html(client)
    assert not re.findall(
        r'class="[^"]*\b(?:bg|text|border)-(?:gray|amber|red|emerald|indigo|blue|violet)-\d{2,3}',
        html,
    )
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_run_layout.py -v`
Expected: FAIL — `.run` 클래스 · 2열 · 비교 칩 없음

- [ ] **Step 3: 템플릿을 재작성한다**

설계 §3.1 구조로 다시 쓴다. 뼈대:

```jinja
{% extends "base.html" %}
{% block title %}{{ run.system_name }} Run{% endblock %}

{% block head_extra %}
{% import "_assets.html" as run_assets %}
{{ run_assets.asset_styles("entries/run.ts") }}
{% endblock %}

{% block content %}
{% import "components/status-badge/macro.jinja" as sb %}
<div class="run" id="run-root" data-run-id="{{ run.run_id }}">

  <header class="run-head"> … 시스템명 · 상태 배지 · 비교 칩 · 취소/재실행 … </header>

  <section class="run-otp" id="otp-panel" … > … #otp-prompt · #otp-countdown · #otp-form … </section>

  <section class="run-prog"> … #run-progress-bar · #run-progress-label · 경과 … </section>

  <div class="run-split">
    <section class="run-col run-col--modules">
      <ol id="run-module-list">
        {% for module in run.modules | sort(attribute='order') %}
        <li class="run-mod" data-module-id="{{ module.module_id }}"
            data-order="{{ module.order }}" data-status="{{ module.status | lower }}">
          … 이름 · 배지 · 소요시간 · (전개 시) AI 분석 · 아티팩트 …
        </li>
        {% endfor %}
      </ol>
    </section>
    <section class="run-col run-col--log">
      … #log-filter · #log-search · #log-copy · #log-download · #log-console …
    </section>
  </div>
</div>
{% endblock %}

{% block scripts %}
{% import "_assets.html" as run_assets %}
{{ run_assets.asset_script("entries/run.ts") }}
{% endblock %}
```

`is-hidden` 대신 네이티브 `hidden` 속성을 쓴다(Cycle 2 선례). 상태 배지는 `sb.status_badge(...)` 매크로를 그대로 쓴다(FG-003·FG-006).

**비교 패널**은 `#comparison-panel` 섹션을 지우고 헤더에 `data-role="comparison-chip"` 요소를 둔다. 기준 Run 링크는 칩 자체를 `<a>` 로 만든다.

Step 1 의 `test_js_hooks_survive` 목록이 **유지해야 할 훅의 완전한 집합**이다.

- [ ] **Step 4: `run/styles.css` 를 만든다**

설계 §3.1 의 세로 구성을 옮긴다. 색은 전부 토큰(FG-002).

```css
/* 런 상세 — 관제와 조사를 한 화면에서 잇는다(설계 §3.1).
   넌스크롤 셸은 shell.css 가 담당한다. */

.run {
  display: flex;
  flex-direction: column;
  gap: 0.6875rem;
  height: 100%;
  padding: 1rem;
  overflow: hidden;
}

.run-head, .run-otp, .run-prog { flex-shrink: 0; }

/* 설계 D2 — 좌우 열은 각자 하나씩 스크롤한다. 세로로 쌓인 영역은 0. */
.run-split {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(230px, 300px) 1fr;
  gap: 0.6875rem;
}

.run-col { display: flex; flex-direction: column; min-height: 0; }
#run-module-list, #log-console { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }

@media (max-width: 1023px) {
  .run-split { grid-template-columns: 1fr; grid-template-rows: 1fr auto; }
  #log-console { max-height: 40vh; }
}

.run-mod[data-focus="true"] {
  border-color: var(--st-error-border);
  box-shadow: 0 0 0 3px var(--st-error-surface), var(--pl-shadow-sm);
}
.run-mod[data-focus="true"][data-status="running"],
.run-mod[data-focus="true"][data-status="waiting_input"] {
  border-color: var(--st-running-border);
  box-shadow: 0 0 0 3px var(--st-running-surface), var(--pl-shadow-sm);
}

#log-console { background: var(--c-ink-950); color: var(--c-ink-100); }
```

나머지(헤더·OTP·진행·모듈 행·AI 분석·로그 바)도 같은 방식으로 채운다. 400줄을 넘으면 쪼갠다.

`--c-ink-*` 는 `primitives.css` 에 이미 있다(상황판이 쓰던 램프). 로그 콘솔이 그것을 재사용하면 새 hex 가 필요 없다.

- [ ] **Step 5: 엔트리를 만들고 등록한다**

`app/web/frontend/entries/run.ts`:

```typescript
// 런 상세 화면 엔트리. 배선만 한다 — 로직은 run/ 아래 모듈에 있다.
// 최초 렌더는 서버 마크업이 끝낸다. 초점은 로드 시 한 번 계산하고(설계 D4)
// 이후 소켓 이벤트마다 다시 계산한다.
import "../run/styles.css";
import { bindOtpForm, bindRunActions } from "../run/actions";
import { applyFocus } from "../run/modules";
import { bindRunSocket, renderProgress, startRuntimeTicker } from "../run/socket";

document.addEventListener("DOMContentLoaded", () => {
  applyFocus();
  renderProgress();
  bindRunActions();
  bindOtpForm();
  bindRunSocket();
  startRuntimeTicker();
});
```

`vite.config.ts` 의 `rollupOptions.input` 에 추가한다.

```typescript
        run: resolve(__dirname, "app/web/frontend/entries/run.ts"),
```

- [ ] **Step 6: 다리를 없앤다**

- `app/web/frontend/entries/main.ts`: `window.__executeOtpPanel = { updateOtpPanel };` 줄과 관련 import·`declare global` 항목 삭제
- `app/web/frontend/execute/legacy-bridge.ts`: `__executeOtpPanel?: …` 타입 선언 삭제

Run: `grep -rn "__executeOtpPanel" app/web --include=*.ts --include=*.js | grep -v "/dist/"`
Expected: 출력 없음

- [ ] **Step 7: `app.js` 에서 런 상세 몫을 지운다**

- 런 상세 함수 전부(`:853~1384` 중 Run 이력·예약에 속하지 않는 것)
- `DOMContentLoaded` 의 `bindLogControls();` · `startRuntimeTicker();` · `bindRunActions();` · `bindOtpForm();` · `bindRunSocket();` 다섯 줄
- `__executeLegacy` 는 **다섯 키 전부 그대로 둔다** — 점검 실행 화면이 `setInlineFeedback`·`readErrorMessage` 를, 예약이 나머지 셋을 쓴다(설계 D5). 여기서 키를 지우면 execute 화면이 즉시 깨진다

지운 뒤 참조를 확인한다.

Run: `grep -n "updateModuleCard\|renderLogConsole\|updateRunProgress\|bindRunSocket" app/web/static/app.js`
Expected: 출력 없음

- [ ] **Step 8: 테스트와 빌드**

Run: `python3 -m pytest tests/test_run_layout.py -v && npm run build && npm run typecheck && npm run lint && npm run test`
Expected: 전부 PASS

Run: `wc -l app/web/static/app.js`
Expected: 약 853줄

- [ ] **Step 9: 실물로 확인한다**

Run 을 하나 돌려 끝까지 본다.

- 좌측 모듈이 하나씩 넘어가고 우측 로그가 흐른다
- **모듈이 실패하면 좌측 그 행이 전개되고 우측 필터가 그 모듈로 바뀐다 — 클릭 0회**
- 필터를 손으로 「전체 모듈」로 바꾼 뒤에는 다음 실패에도 자동으로 안 바뀐다
- OTP 구간에서 패널이 뜨고 카운트다운이 돈다
- 취소·재실행 버튼이 동작한다
- 로그 복사·다운로드가 **전량**을 담는다(2,000줄 넘는 Run 으로 확인)
- 콘솔에 `ReferenceError` 가 없다

- [ ] **Step 10: 커밋**

```bash
git add app/web/templates/run.html app/web/frontend app/web/static/app.js vite.config.ts tests/test_run_layout.py
git commit -m "feat(run): 2열 관제-조사 화면으로 전환 — app.js 절단, OTP 다리 소멸"
```

---

### Task 8: 회귀 테스트와 문서

**Files:**
- Create: `tests/test_run_viewport.py`
- Modify: `docs/specs/dashboard/03-run-suite-views.md`
- Modify: `docs/superpowers/specs/2026-08-31-run-detail-promotion-design.md` (§7 실측)

**Interfaces:**
- Consumes: Task 7 의 완성된 화면
- Produces: 없음

- [ ] **Step 1: Playwright 회귀를 쓴다**

`tests/test_suite_viewport.py` 의 서버 기동 픽스처를 따른다.

```python
VIEWPORTS = [(1366, 768), (1920, 1080), (2560, 1440)]


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_page_scroll(page_factory, width, height):
    page = page_factory(width, height)
    page.goto(f"{BASE_URL}/runs/{RUN_ID_FAILED}")
    page.wait_for_selector(".run")
    overflow = page.evaluate(
        "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"
    )
    assert overflow <= 1, f"{width}x{height} 에서 세로 스크롤 {overflow}px"


def test_exactly_two_internal_scrollers_one_per_column(page_factory):
    """설계 D2 — 좌우 열에 하나씩. 세로로 쌓인 영역은 0."""
    page = page_factory(1920, 1080)
    page.goto(f"{BASE_URL}/runs/{RUN_ID_FAILED}")
    page.wait_for_selector(".run-split")
    ids = page.evaluate(
        """() => Array.from(document.querySelectorAll('.run *'))
              .filter((el) => {
                  const style = getComputedStyle(el);
                  return /auto|scroll/.test(style.overflowY)
                      && el.scrollHeight > el.clientHeight + 1;
              })
              .map((el) => el.id || el.className)"""
    )
    assert len(ids) == 2, f"내부 스크롤러가 2개가 아니다: {ids}"


def test_focused_module_analysis_is_inside_the_viewport(page_factory):
    """is_visible() 은 뷰포트 밖 요소를 통과시킨다 — 좌표로 단언한다."""
    page = page_factory(1366, 768)
    page.goto(f"{BASE_URL}/runs/{RUN_ID_FAILED}")
    page.wait_for_selector('[data-focus="true"]')
    box = page.locator('[data-focus="true"] [data-role="failure-analysis"]').bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= 768


def test_log_filter_follows_focus_until_user_touches_it(page_factory):
    """설계 D7 — 자동 추종은 사용자가 손대면 꺼진다."""
    page = page_factory(1920, 1080)
    page.goto(f"{BASE_URL}/runs/{RUN_ID_FAILED}")
    page.wait_for_selector('[data-focus="true"]')
    focused = page.locator('[data-focus="true"]').get_attribute("data-module-id")
    assert page.locator("#log-filter").input_value() == focused
    page.select_option("#log-filter", "")
    assert page.locator("#log-filter").input_value() == ""
```

`RUN_ID_FAILED` 는 **실패한 모듈이 있는** Run 픽스처다. 초점·전개·필터 연동이 전부 그 상태에서만 검증된다.

- [ ] **Step 2: 실행한다**

Run: `python3 -m pytest tests/test_run_viewport.py -v`
Expected: PASS. 넘치면 `.run` 의 `gap`·`padding` 을 줄인다.

Chromium 이 없으면 `python3 -m playwright install chromium` 후 재실행.

- [ ] **Step 3: AC Spec 을 갱신한다**

`docs/specs/dashboard/03-run-suite-views.md` §1 에 런 상세의 새 구조를 적고 수용 기준을 추가한다. `AC-001`(OTP 패널)은 규칙이 유지되므로 건드리지 않는다.

```markdown
### AC-005: 런 상세 2열과 초점 전환

```gherkin
Given 모듈이 실패한 run
When 상세 화면을 연다
Then 그 모듈에 data-focus="true" 가 있고 AI 분석이 뷰포트 안에 있다
And 로그 필터가 그 모듈로 맞춰져 있다
And 사용자가 필터를 바꾸면 이후 자동 추종이 멈춘다
```

### AC-006: 런 상세 스크롤 소유권

```gherkin
Given 모듈 10개짜리 run
When 1366x768 에서 렌더한다
Then body 세로 스크롤이 0 이다
And 내부 스크롤러가 좌우 열에 하나씩 정확히 2개다
```
```

- [ ] **Step 4: 설계 문서 §7 에 실측을 반영한다**

`app.js` 최종 줄 수, `frontend/run/` 각 파일 줄 수, 남은 다리를 **실측값으로** 적는다. 추정으로 적지 않는다.

- [ ] **Step 5: 문서 포맷과 전체 게이트**

Run: `python -m ruff format --check .`
Expected: clean. 마크다운 안 Python 코드블록도 검사 대상이다.

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `python3 scripts/ci/run_all_gates.py --gate coverage`
Expected: 통과

- [ ] **Step 6: 커밋**

```bash
git add tests/test_run_viewport.py docs/
git commit -m "test(run): 좌표 계약·스크롤 소유권 회귀 + AC Spec 갱신"
```

---

## 완료 확인

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [ ] `python3 scripts/ci/run_all_gates.py --gate coverage` 통과
- [ ] `npm run test && npm run typecheck && npm run lint && npm run build` 통과
- [ ] **`app/` 파이썬 변경 0줄** — `git diff --stat origin/main..HEAD -- app/**/*.py` 가 비어 있다
- [ ] `app.js` 약 853줄, 런 상세 함수 0개
- [ ] `window.__executeOtpPanel` 0건 — `main.ts`·`legacy-bridge.ts`·`app.js` 모두
- [ ] `__executeLegacy` **5키 그대로** — 점검 실행 화면이 `setInlineFeedback` 20회·`readErrorMessage` 4회를 쓴다(설계 D5). 줄어들지 않는 것이 정상이다
- [ ] `run/` 이 `window.__execute*` 를 참조하지 않는다
- [ ] `frontend/run/` · `entries/run.ts` 전 파일 400줄 미만
- [ ] 1366 · 1920 · 2560 px 넌스크롤, 내부 스크롤러 정확히 2개
- [ ] `run.html` 에 Tailwind 색 유틸리티 0개, `#comparison-panel` 섹션 0건
- [ ] 실물에서 Run 1회 완주 — 초점 이동 · 필터 자동/수동 · OTP 카운트다운 · 로그 전량 내보내기

## 이 계획이 남기는 것

| 항목 | 다음 단계 |
| --- | --- |
| `app.js` 잔여 약 853줄 | Cycle 4(Run 이력, 소멸) · Cycle 6(예약) |
| `__executeLegacy` 5키 | execute 화면이 두 키를, 예약이 세 키를 쓴다. Cycle 4·6 의 몫 |
| `FG004_ALLOWLIST` 의 `app.css` | Cycle 4~6 |
| `run/` 안의 `setInlineFeedback` 등 지역 복제 | Cycle 4 가 `app.js` 원본을 지울 때 정리 판단 |
| 로그 가상 스크롤 | 2,000줄 상한이 부족하다고 **측정으로** 확인되면 |
