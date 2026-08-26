# Cycle 1b: 점검 실행 이관 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 점검 실행 화면을 구동하는 `app.js` 약 1,400줄을 타입과 테스트를 갖춘 `entries/execute.ts` 로 옮기고, `app.css` 의 프리셋·그래프 CSS를 책임 단위 stylesheet로 이사시킨다.

**체크 진행:** 이전 기록 9/36에서 출발했으며, Task 1~4·5의 증거와 사용자 제공 최종 HEAD full-gate를 반영해 현재 **33/36**이다. 미체크 3개는 Task 4 Step 4, `app.js` 약 1,850줄 목표(실측 1,949줄), 실제 Run/SUITE E2E completion이다.

**Architecture:** 기계적 `.js` → `.ts` 변환이 아니라 **책임 분리 + 타입 + Vitest** 로 한다(P3-4 §7 사용자 결정). `app.js` 의 점검 실행 몫은 세 덩어리다 — 모듈 그래프(순수 계산 + DOM 렌더), 프리셋 패널, 폼·실행·OTP 바인딩. 순수 계산부터 옮기면 Vitest 로 바로 잠글 수 있고, DOM 계층은 그 위에 얹는다. 이관 중에도 화면은 계속 동작해야 하므로 **함수 단위가 아니라 덩어리 단위로 옮기고, 옮긴 즉시 `app.js` 에서 지운다** — 두 벌이 동시에 바인딩되면 이벤트가 두 번 걸린다.

**Tech Stack:** TypeScript 5.6, Vite 6(다중 엔트리), Vitest 3 + jsdom, Alpine.js 3, pytest

**Spec:** `docs/superpowers/specs/2026-08-24-execute-promotion-design.md` (§1.2 모놀리스 해체 · §2 프로그램 구조 · §4.2 규격 4·5번 · D4)

**선행:** `docs/superpowers/plans/2026-08-24-cycle1a-execute-layout.md` 완료. 1a 가 `<details>` 를 없앴으므로 `bindSystemCardExpand`(`app.js:530`)는 이미 죽은 코드다.

## Global Constraints

- **화면 전용 코드는 `components/` 로 올리지 않는다**(설계 D4). `app/web/frontend/execute/` 에 둔다. 두 번째 화면이 같은 것을 요구할 때 승격한다. **이 계획이 화면 폴더 관례를 세우고, Cycle 2~6 이 따른다.**
- **FG-004: 파일 400줄 상한.** 한 파일이 넘치면 책임 단위로 쪼갠다.
- **FG-002: 하드코딩 hex 금지.** 옮기는 CSS 의 hex 는 `var(--c-*)` · `var(--st-*)` 로 바꾼다.
- **FG-003: 상태 라벨은 `lib/status.generated.ts` 경유만.** `*.test.ts` 는 예외.
- **`data-role` 속성과 폼 `name` 은 하나도 바꾸지 않는다.** 서버 렌더 마크업이 계약이다.
- **옮긴 즉시 `app.js` 에서 지운다.** 두 벌 동시 바인딩 금지.
- **공용 함수는 마지막까지 `app.js` 에 남긴다** — `readErrorMessage`(:550) · `statusBadgeClassName`(:559) · `setInlineFeedback`(:571) · `showToast`(:595) · `collectFormInput`(:612)는 다른 화면도 쓴다. Cycle 4 가 정리한다.
- **UI 문자열은 한국어**(AGENTS.md).
- **모든 단언은 "이것이 실패할 수 있는 실제 경우는 무엇인가" 에 답해야 한다**(설계 §8.2.1). Cycle 1a 에서 `is_visible()` · `"sticky" in css` · `len(scrollers) <= 1` 세 단언이 **통과하면서 아무것도 지키지 않았고**, 그중 하나는 실제 제품 결함을 은폐했다. 이관 테스트도 같다 — 옮긴 함수가 **틀린 값을 돌려주면 빨간불이 켜지는지** 확인해라. 함수가 존재한다는 단언은 이관을 지키지 못한다.
- **PR 전 필수:** `python3 scripts/ci/run_all_gates.py --profile full`

## 이관 인벤토리 (`app/web/static/app.js`)

| 덩어리 | 함수 | 줄 | 옮길 곳 |
| --- | --- | --- | --- |
| **그래프 순수 계산** | `computeModuleGraphMetrics` `sortModulesByOrder` `buildModuleRelations` `computeModuleDepth` `computeModuleSubtreeHeight` `buildModuleGraphLayout` `collectDescendantModuleIds` | 23·92·96·121·139·159·280 | `execute/module-graph/layout.ts` |
| **그래프 DOM** | `parseSystemDefinition` `ensureModuleGraphResizeObserver` `createModuleGraphNode` `getModuleGraphNodes` `buildModuleNodeMap` `buildModuleChildrenMap` `readNodeDependencyIds` `findMissingDependencyIds` `getSelectedModuleIds` `readSelectedModuleIdSet` `buildModuleSelectionWarnings` `fitModuleGraphToViewport` `drawModuleGraph` `updateModuleSelectorState` `renderModuleSelector` `bindModuleSelectors` | 62·78·219·253·257·261·292·296·300·307·311·332·363·404·437·501 | `execute/module-graph/render.ts` |

`findMissingDependencyIds`(:296)와 `buildModuleSelectionWarnings`(:311)는 이름만 계산처럼 보이지만 각각 DOM 노드와 `<form>` 을 받는다 — DOM 쪽이다.
| **프리셋** | `authMethodLabel` `presetSummaryText` `loadPresets` `renderAllPresetUI` `renderIndividualPresetPanels` `buildPresetChip` `applyPresetToForm` `applyModuleSelection` `submitPresetSave` `deletePresetById` `bindPresetPanels` `renderSuitePresetLists` `buildSuitePresetChip` | 636~943 | `execute/presets.ts` |
| **폼·실행·OTP** | `syncConditionalFields` `bindConditionalFields` `updateOtpPanel` `startSystemRun` `bindSystemButtons` `updateSuiteSystemSelectorState` `bindSuiteForm` | 944·965·985·1007·2227·2405·2570 | `execute/run-form.ts` · `execute/suite-form.ts` |
| **죽은 코드** | `bindSystemCardExpand` | 530 | **삭제**(1a 가 `<details>` 를 없앴다) |

`formatRunTimestamp`(:1066) · `createRunListItem`(:1087) 은 **Run 이력**의 것이다 — 이 계획에서 건드리지 않는다(Cycle 4).

## File Structure

| 파일 | 책임 | 상한 |
| --- | --- | --- |
| `app/web/frontend/execute/module-graph/layout.ts` | DAG 좌표 계산. DOM 을 모른다 | ~200줄 |
| `app/web/frontend/execute/module-graph/layout.test.ts` | 위의 Vitest | — |
| `app/web/frontend/execute/module-graph/render.ts` | 노드·엣지 DOM, 선택 상태, 리사이즈 | ~320줄 |
| `app/web/frontend/execute/presets.ts` | 프리셋 조회·적용·저장·삭제 | ~330줄 |
| `app/web/frontend/execute/run-form.ts` | 조건부 필드, OTP 패널, 개별 시스템 실행 | ~250줄 |
| `app/web/frontend/execute/suite-form.ts` | SUITE 시스템 선택, 전체 실행 | ~220줄 |
| `app/web/frontend/styles/execute.css` | 실행 셸·2열 그리드·좌측 목록·우측 패널·sticky 액션 바 | 95줄 |
| `app/web/frontend/styles/execute-graph.css` | Cycle 1a 모듈 그래프 전용 규칙 | 184줄 |
| `app/web/frontend/styles/execute-presets.css` | Cycle 1b 인증 프리셋 전용 규칙 | 240줄 |
| `app/web/frontend/entries/execute.ts` | 배선만. 위 모듈의 bind 를 호출한다 | ~60줄 |

---

### Task 1: 그래프 순수 계산 이관

DOM 을 모르는 계산부터 옮긴다. 여기가 이 화면에서 가장 테스트하기 좋고, 가장 조용히 깨지는 부분이다.

**Files:**
- Create: `app/web/frontend/execute/module-graph/layout.ts`
- Create: `app/web/frontend/execute/module-graph/layout.test.ts`

**Interfaces:**
- Consumes: 없음(순수 함수)
- Produces:
  - `type ModuleDef = { module_id: string; name: string; depends_on?: string[]; order?: number }`
  - `type GraphMetrics = { rowHeight: number; rowGap: number; columnGap: number }`
  - `type GraphLayout = { layoutByModuleId: Map<string, { depth: number; row: number }>; maxDepth: number; maxRow: number }`
  - `computeModuleGraphMetrics(columnCount: number, rowCount: number, availableWidth: number, availableHeight: number): GraphMetrics`
  - `buildModuleRelations(modules: ModuleDef[]): { modulesById: Map<string, ModuleDef>; childrenById: Map<string, string[]> }`
  - `computeModuleDepth(moduleId: string, modulesById: Map<string, ModuleDef>, cache?: Map<string, number>): number`
  - `computeModuleSubtreeHeight(moduleId: string, childrenById: Map<string, string[]>, cache?: Map<string, number>): number`
  - `buildModuleGraphLayout(modules: ModuleDef[]): GraphLayout`
  - `sortModulesByOrder(modules: ModuleDef[]): ModuleDef[]`
  - `collectDescendantModuleIds(moduleId: string, childrenById: Map<string, string[]>, collected?: Set<string>): Set<string>`
  - Task 2 가 전부 소비한다

- [x] **Step 1: 원본을 읽고 상수를 확인한다**

`app/web/static/app.js` 상단의 `MODULE_GRAPH_MAX_GAP` · `MODULE_GRAPH_MIN_GAP` · `MODULE_GRAPH_MAX_ROW_HEIGHT` · `MODULE_GRAPH_MIN_ROW_HEIGHT` 실제 값을 확인한다. 이 값들이 바뀌면 아래 테스트의 기대값이 달라진다 — **추측하지 말고 파일에서 읽는다.**

Run: `grep -n "MODULE_GRAPH_" app/web/static/app.js | head`

- [x] **Step 2: 실패하는 테스트를 쓴다**

`app/web/frontend/execute/module-graph/layout.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  buildModuleGraphLayout,
  buildModuleRelations,
  collectDescendantModuleIds,
  computeModuleDepth,
  computeModuleGraphMetrics,
  computeModuleSubtreeHeight,
  sortModulesByOrder,
} from "./layout";
import type { ModuleDef } from "./layout";

// 로그인 → (조회 → 상세), 로그인 → 결제. HOM 계열의 실제 모양이다.
const MODULES: ModuleDef[] = [
  { module_id: "login", name: "로그인", depends_on: [], order: 1 },
  { module_id: "list", name: "조회", depends_on: ["login"], order: 2 },
  { module_id: "detail", name: "상세", depends_on: ["list"], order: 3 },
  { module_id: "pay", name: "결제", depends_on: ["login"], order: 4 },
];

describe("buildModuleRelations", () => {
  it("부모를 자식 목록으로 뒤집는다", () => {
    const { modulesById, childrenById } = buildModuleRelations(MODULES);
    expect(modulesById.get("list")!.name).toBe("조회");
    expect(childrenById.get("login")).toEqual(["list", "pay"]);
    expect(childrenById.get("detail") ?? []).toEqual([]);
  });
});

describe("computeModuleDepth", () => {
  it("의존 사슬의 길이가 깊이다", () => {
    const { modulesById } = buildModuleRelations(MODULES);
    expect(computeModuleDepth("login", modulesById)).toBe(0);
    expect(computeModuleDepth("list", modulesById)).toBe(1);
    expect(computeModuleDepth("detail", modulesById)).toBe(2);
  });

  it("순환 의존이 있어도 무한 재귀하지 않는다", () => {
    const cyclic: ModuleDef[] = [
      { module_id: "a", name: "A", depends_on: ["b"] },
      { module_id: "b", name: "B", depends_on: ["a"] },
    ];
    const { modulesById } = buildModuleRelations(cyclic);
    expect(() => computeModuleDepth("a", modulesById)).not.toThrow();
  });
});

describe("computeModuleSubtreeHeight", () => {
  it("잎은 1행, 가지는 자식 높이의 합이다", () => {
    const { childrenById } = buildModuleRelations(MODULES);
    expect(computeModuleSubtreeHeight("detail", childrenById)).toBe(1);
    expect(computeModuleSubtreeHeight("login", childrenById)).toBe(2);
  });
});

describe("buildModuleGraphLayout", () => {
  it("깊이는 열, 형제는 다른 행에 놓인다", () => {
    const { layoutByModuleId, maxDepth, maxRow } = buildModuleGraphLayout(MODULES);
    expect(layoutByModuleId.get("login")).toEqual({ depth: 0, row: 0 });
    expect(layoutByModuleId.get("list")!.depth).toBe(1);
    expect(layoutByModuleId.get("pay")!.depth).toBe(1);
    expect(layoutByModuleId.get("list")!.row).not.toBe(layoutByModuleId.get("pay")!.row);
    expect(maxDepth).toBe(2);
    expect(maxRow).toBe(1);
  });

  it("의존이 끊긴 모듈도 자리를 받는다 — 화면에서 사라지면 안 된다", () => {
    const orphaned: ModuleDef[] = [
      ...MODULES,
      { module_id: "ghost", name: "유령", depends_on: ["없는모듈"], order: 5 },
    ];
    const { layoutByModuleId } = buildModuleGraphLayout(orphaned);
    expect(layoutByModuleId.has("ghost")).toBe(true);
  });

  it("모듈이 하나뿐이어도 성립한다", () => {
    const solo: ModuleDef[] = [{ module_id: "only", name: "단독", depends_on: [] }];
    const { layoutByModuleId, maxDepth, maxRow } = buildModuleGraphLayout(solo);
    expect(layoutByModuleId.get("only")).toEqual({ depth: 0, row: 0 });
    expect(maxDepth).toBe(0);
    expect(maxRow).toBe(0);
  });
});

describe("computeModuleGraphMetrics", () => {
  it("공간이 넉넉하면 최대 크기를 쓴다", () => {
    const metrics = computeModuleGraphMetrics(3, 2, 1200, 800);
    expect(metrics.rowHeight).toBeGreaterThan(0);
    expect(metrics.rowGap).toBeGreaterThan(0);
  });

  it("세로가 좁으면 행 높이를 줄인다", () => {
    const roomy = computeModuleGraphMetrics(3, 6, 1200, 800);
    const tight = computeModuleGraphMetrics(3, 6, 1200, 200);
    expect(tight.rowHeight).toBeLessThan(roomy.rowHeight);
  });

  it("열이 많으면 간격을 좁힌다", () => {
    const few = computeModuleGraphMetrics(3, 4, 1200, 600);
    const many = computeModuleGraphMetrics(9, 4, 1200, 600);
    expect(many.columnGap).toBeLessThanOrEqual(few.columnGap);
  });

  it("가로가 좁아도 간격이 음수가 되지 않는다", () => {
    const metrics = computeModuleGraphMetrics(10, 4, 200, 600);
    expect(metrics.columnGap).toBeGreaterThanOrEqual(0);
  });
});

describe("collectDescendantModuleIds", () => {
  it("후손을 전부 모은다 — 모듈 제외 시 연쇄 해제에 쓰인다", () => {
    const { childrenById } = buildModuleRelations(MODULES);
    expect(collectDescendantModuleIds("login", childrenById)).toEqual(
      new Set(["list", "detail", "pay"]),
    );
  });
});

describe("sortModulesByOrder", () => {
  it("order 오름차순이고 원본을 바꾸지 않는다", () => {
    const shuffled = [MODULES[2], MODULES[0], MODULES[3], MODULES[1]];
    const sorted = sortModulesByOrder(shuffled);
    expect(sorted.map((m) => m.module_id)).toEqual(["login", "list", "detail", "pay"]);
    expect(shuffled[0].module_id).toBe("detail");
  });
});
```

- [x] **Step 3: 실패를 확인한다**

Run: `npm run test -- layout`
Expected: FAIL — `Cannot find module './layout'`

- [x] **Step 4: layout.ts 를 만든다**

`app/web/static/app.js` 의 해당 함수 본문을 **로직 변경 없이** 옮기고 타입만 얹는다. 기대값을 맞추려고 계산을 바꾸지 않는다 — 테스트가 현행 동작을 기록한 것이므로, 어긋나면 **테스트의 기대값이 틀린 것**이니 원본을 다시 읽고 고친다.

파일 상단 주석:

```typescript
// 모듈 의존성 그래프의 좌표 계산. DOM 을 모른다.
// app.js:23~330 에서 이관(Cycle 1b). 로직은 그대로이고 타입과 테스트가 붙었다.
```

`parseSystemDefinition` 은 DOM(`<script type="application/json">`)을 읽으므로 여기가 아니라 Task 2 의 `render.ts` 로 간다.

- [x] **Step 5: 테스트가 통과하는지 확인한다**

Run: `npm run test -- layout && npm run typecheck && npm run lint`
Expected: PASS

- [x] **Step 6: 커밋**

```bash
git add app/web/frontend/execute/module-graph/
git commit -m "refactor(execute): 모듈 그래프 좌표 계산을 타입·테스트와 함께 이관"
```

---

### Task 2: 그래프 DOM 렌더 이관과 app.js 절단

`layout.ts` 위에 DOM 계층을 얹고, **같은 커밋에서** `app.js` 의 원본을 지운다.

**Files:**
- Create: `app/web/frontend/execute/module-graph/render.ts`
- Create: `app/web/frontend/entries/execute.ts`
- Modify: `vite.config.ts`
- Modify: `app/web/templates/execute.html`
- Modify: `app/web/static/app.js` (삭제)

**Interfaces:**
- Consumes: Task 1 의 `layout.ts` 전부
- Produces: `bindModuleSelectors(root?: ParentNode): void` — `[data-role="module-selector"]` 를 가진 폼을 찾아 그래프를 렌더하고 클릭·리사이즈를 건다. `entries/execute.ts` 가 호출한다

- [x] **Step 1: render.ts 를 만든다**

인벤토리의 **그래프 DOM** 13개 함수와 `parseSystemDefinition`(:78)을 옮긴다. 내부 계산은 `./layout` 에서 임포트한다.

400줄을 넘으면(FG-004) `selection.ts`(선택 상태 · 경고)와 `draw.ts`(노드 · 엣지 · 리사이즈)로 쪼갠다.

- [x] **Step 2: 엔트리를 만든다**

`app/web/frontend/entries/execute.ts`:

```typescript
// 점검 실행 화면 엔트리. 배선만 한다 — 로직은 execute/ 아래 모듈에 있다.
import { bindModuleSelectors } from "../execute/module-graph/render";
import { loadSystemBadges } from "./execute-badges";

document.addEventListener("DOMContentLoaded", () => {
  bindModuleSelectors();
  void loadSystemBadges();
});
```

**스타일시트를 새로 만들지 마라.** 1a 가 `app/web/frontend/styles/execute.css` 를 만들었고 `base.css:11` 이 이미 임포트한다. Task 5 의 프리셋 절은 그 파일에 덧붙인다. 엔트리에서 CSS 를 임포트하면 같은 스타일이 두 경로로 들어온다.


Cycle 1a 가 만든 `entries/execute-badges.ts` 는 이제 `execute.ts` 가 흡수하므로, `vite.config.ts` 에서 `execute-badges` 입력을 지우고 `execute` 를 넣는다.

```typescript
        execute: resolve(__dirname, "app/web/frontend/entries/execute.ts"),
```

`execute.html` 의 스크립트 블록도 바꾼다.

```jinja
{% block scripts %}
{% import "_assets.html" as exec_assets %}
{{ exec_assets.asset_script("entries/execute.ts") }}
{% endblock %}
```

`execute-badges.ts` 하단의 `DOMContentLoaded` 기동 줄은 지운다 — 이제 `execute.ts` 가 부른다. 두 번 걸리면 배지가 두 번 렌더된다.

- [x] **Step 3: app.js 에서 원본을 지운다**

`app/web/static/app.js` 에서 다음을 삭제한다:
- 인벤토리의 **그래프 순수 계산** 10개 + **그래프 DOM** 13개
- `MODULE_GRAPH_*` 상수 4개
- 죽은 `bindSystemCardExpand`(:530)
- 파일 끝 `DOMContentLoaded`(:3245) 의 `bindModuleSelectors();` · `bindSystemCardExpand();` 두 줄

`app.js` 의 다른 곳이 지운 함수를 부르는지 확인한다:

Run: `grep -n "applyModuleSelection\|readSelectedModuleIdSet\|renderModuleSelector\|updateModuleSelectorState" app/web/static/app.js`

프리셋 코드(Task 3 대상)가 `applyModuleSelection` 을 부른다면, Task 3 까지는 그 함수만 `app.js` 에 남기고 주석으로 이유를 적는다.

- [x] **Step 4: 빌드하고 눈으로 확인한다**

Run: `npm run build && npm run typecheck && npm run lint`

`/runs/execute` 에서 시스템을 선택해 확인한다:
- 그래프가 그려진다
- 노드를 클릭하면 선택 해제되고 엣지 색이 바뀐다
- 후손 모듈이 함께 해제된다
- 창 크기를 바꾸면 그래프가 다시 맞춰진다
- 의존성 경고 배너가 뜬다(모듈을 잘못 조합했을 때)

콘솔에 `ReferenceError` 가 없어야 한다 — 있으면 Step 3 에서 아직 참조 중인 함수를 지운 것이다.

- [x] **Step 5: 회귀 테스트**

Run: `python3 -m pytest tests/test_execute_layout.py tests/test_execute_viewport.py -v`
Expected: PASS

- [x] **Step 6: 커밋**

```bash
git add app/web/frontend app/web/static/app.js app/web/templates/execute.html vite.config.ts
git commit -m "refactor(execute): 그래프 DOM 렌더 이관 — app.js 에서 절단"
```

---

### Task 3: 프리셋 패널 이관

**Files:**
- Create: `app/web/frontend/execute/presets.ts`
- Create: `app/web/frontend/execute/presets.test.ts`
- Modify: `app/web/frontend/entries/execute.ts`
- Modify: `app/web/static/app.js` (삭제)

**Interfaces:**
- Consumes: `execute/module-graph/render.ts` 의 선택 적용 함수(`applyModuleSelection` 이 그래프 선택을 바꾼다 — Task 2 에서 어디에 뒀는지 확인하고 그것을 임포트한다)
- Produces: `bindPresetPanels(root?: ParentNode): void`, `loadPresets(): Promise<void>`

- [x] **Step 1: API 계약을 실측한다**

Run: `python3 -m pytest tests/test_presets_http.py -v`

`app/api/routes_presets.py` 를 열어 프리셋 조회·저장·삭제의 **경로와 응답 필드**를 확인한다. `app.js:652` 의 `loadPresets` 가 쓰는 것과 대조한다.

- [x] **Step 2: 실패하는 테스트를 쓴다**

`app/web/frontend/execute/presets.test.ts`. 순수한 부분만 단언한다 — 네트워크는 모킹하지 않고, 요약 문자열 생성과 폼 적용처럼 DOM/데이터만 쓰는 함수를 본다.

```typescript
import { describe, expect, it } from "vitest";
import { applyPresetToForm, presetSummaryText } from "./presets";

describe("presetSummaryText", () => {
  it("인증 수단과 계정을 한 줄로 요약한다", () => {
    const text = presetSummaryText({
      preset_id: "p1",
      name: "홍길동 휴대폰인증",
      system_code: "hom",
      inputs: { auth_method: "mobile", login_id: "hong" },
      module_ids: ["login", "list"],
    });
    expect(text).toContain("hong");
  });

  it("입력이 비어도 예외를 던지지 않는다", () => {
    expect(() =>
      presetSummaryText({
        preset_id: "p2",
        name: "빈 프리셋",
        system_code: "hom",
        inputs: {},
        module_ids: [],
      }),
    ).not.toThrow();
  });
});

describe("applyPresetToForm", () => {
  it("폼 필드를 프리셋 값으로 채운다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<input name="login_id"><select name="auth_method"><option value="mobile"></option></select>';
    applyPresetToForm(form, {
      preset_id: "p1",
      name: "n",
      system_code: "hom",
      inputs: { login_id: "hong", auth_method: "mobile" },
      module_ids: [],
    });
    expect(form.querySelector<HTMLInputElement>('[name="login_id"]')!.value).toBe("hong");
  });

  it("프리셋에 없는 필드는 건드리지 않는다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<input name="login_id" value="기존"><input name="etc" value="유지">';
    applyPresetToForm(form, {
      preset_id: "p1",
      name: "n",
      system_code: "hom",
      inputs: { login_id: "새값" },
      module_ids: [],
    });
    expect(form.querySelector<HTMLInputElement>('[name="etc"]')!.value).toBe("유지");
  });
});
```

`Preset` 타입의 실제 필드명은 Step 1 에서 실측한 API 응답에 맞춘다. 위 필드명은 예시이므로 **반드시 확인 후 고친다.**

- [x] **Step 3: 실패를 확인한다**

Run: `npm run test -- presets`
Expected: FAIL — 모듈 없음

- [x] **Step 4: presets.ts 를 만들고 app.js 에서 지운다**

인벤토리의 **프리셋** 13개 함수(`app.js:636~943`)를 옮긴다. `authMethodLabel`(:636)이 인증 수단 라벨을 하드코딩하고 있다면 그대로 옮긴다 — FG-003 은 **상태** 라벨만 본다. 인증 수단은 상태가 아니다.

`app.js` 에서 원본과 `DOMContentLoaded` 의 `bindPresetPanels();` · `loadPresets();` 두 줄을 지운다.

`entries/execute.ts` 에 배선을 추가한다:

```typescript
import { bindPresetPanels, loadPresets } from "../execute/presets";
// ...
  bindPresetPanels();
  void loadPresets();
```

- [x] **Step 5: 확인한다**

Run: `npm run test && npm run typecheck && npm run lint && npm run build`

`/runs/execute` 에서:
- 프리셋 칩이 뜬다
- 칩을 누르면 폼이 채워지고 모듈 선택이 그래프에 반영된다
- 저장·삭제가 동작한다
- SUITE 패널의 시스템별 프리셋 목록도 동작한다

- [x] **Step 6: 커밋**

```bash
git add app/web/frontend app/web/static/app.js
git commit -m "refactor(execute): 프리셋 패널 이관 — app.js 에서 절단"
```

---

### Task 4: 폼·실행·OTP 바인딩 이관

**Files:**
- Create: `app/web/frontend/execute/run-form.ts`
- Create: `app/web/frontend/execute/run-form.test.ts`
- Create: `app/web/frontend/execute/suite-form.ts`
- Modify: `app/web/frontend/entries/execute.ts`
- Modify: `app/web/static/app.js` (삭제)

**Interfaces:**
- Consumes: `app.js` 에 남아 있는 공용 함수 — Cycle 4 까지 살아 있으므로 `window` 전역이 아니라 **작은 다리 모듈**로 임포트한다. `app/web/frontend/execute/legacy-bridge.ts` 를 만들어 `declare global` 로 타입만 붙이고, 다리 파일에 소멸 조건을 적는다(`main.ts:32` 의 `window.__statusBadge` 와 같은 방식)
- Produces: `bindRunForms(root?: ParentNode): void`, `bindSuiteForm(root?: ParentNode): void`

- [x] **Step 1: 실패하는 테스트를 쓴다**

`syncConditionalFields`(:944)가 이 덩어리에서 가장 순수하고 가장 잘 깨지는 부분이다 — 인증 수단에 따라 필드를 보였다 감추는 로직이며, `data-show-when-key` / `data-show-when-value` 계약을 읽는다(`execute.html:333~340`).

```typescript
import { describe, expect, it } from "vitest";
import { syncConditionalFields } from "./run-form";

function formWith(authMethod: string): HTMLFormElement {
  const form = document.createElement("form");
  form.innerHTML = `
    <select name="auth_method">
      <option value="mobile" ${authMethod === "mobile" ? "selected" : ""}></option>
      <option value="id" ${authMethod === "id" ? "selected" : ""}></option>
    </select>
    <label class="conditional-field" data-show-when-key="auth_method"
           data-show-when-value="mobile" data-required="true">
      <input name="phone">
    </label>`;
  return form;
}

describe("syncConditionalFields", () => {
  it("조건이 맞으면 필드를 보인다", () => {
    const form = formWith("mobile");
    syncConditionalFields(form);
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(false);
  });

  it("조건이 어긋나면 감춘다", () => {
    const form = formWith("id");
    syncConditionalFields(form);
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(true);
  });

  it("감춰진 필수 필드는 required 를 벗는다 — 안 그러면 폼이 제출되지 않는다", () => {
    const form = formWith("id");
    syncConditionalFields(form);
    expect(form.querySelector<HTMLInputElement>('[name="phone"]')!.required).toBe(false);
  });

  it("값이 콤마 목록이면 그중 하나만 맞아도 보인다", () => {
    const form = formWith("mobile");
    form.querySelector(".conditional-field")!.setAttribute("data-show-when-value", "id,mobile");
    syncConditionalFields(form);
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(false);
  });
});
```

`is-hidden` 클래스명과 `required` 처리 방식은 `app.js:944~984` 의 실제 구현을 읽고 맞춘다.

- [x] **Step 2: 실패를 확인한다**

Run: `npm run test -- run-form`
Expected: FAIL — 모듈 없음

- [x] **Step 3: 두 파일로 나눠 옮긴다**

`run-form.ts` — `syncConditionalFields`(:944) · `bindConditionalFields`(:965) · `updateOtpPanel`(:985) · `startSystemRun`(:1007) · `bindSystemButtons`(:2227)
`suite-form.ts` — `updateSuiteSystemSelectorState`(:2405) · `bindSuiteForm`(:2570)

`app.js` 에서 원본과 `DOMContentLoaded` 의 `bindSystemButtons();` · `bindSuiteForm();` · `bindConditionalFields` 관련 줄을 지운다.

`entries/execute.ts` 최종형:

```typescript
// 점검 실행 화면 엔트리. 배선만 한다 — 로직은 execute/ 아래 모듈에 있다.
import { bindModuleSelectors } from "../execute/module-graph/render";
import { bindPresetPanels, loadPresets } from "../execute/presets";
import { bindRunForms } from "../execute/run-form";
import { bindSuiteForm } from "../execute/suite-form";
import { loadSystemBadges } from "./execute-badges";

document.addEventListener("DOMContentLoaded", () => {
  bindModuleSelectors();
  bindPresetPanels();
  bindRunForms();
  bindSuiteForm();
  void loadPresets();
  void loadSystemBadges();
});
```

- [ ] **Step 4: 실행 경로를 끝까지 확인한다**

Run: `npm run test && npm run typecheck && npm run lint && npm run build`

`/runs/execute` 에서 **실제로 Run 을 하나 돌린다**:
- 개별 시스템 실행 → Run 상세로 이동한다
- 인증 수단을 바꾸면 조건부 필드가 보였다 감춰진다
- SUITE 실행 → 시스템 선택 검증(AC-001)이 동작한다
- OTP 구간이 있으면 `WAITING_INPUT` 패널이 뜬다

- [x] **Step 5: 커밋**

```bash
git add app/web/frontend app/web/static/app.js
git commit -m "refactor(execute): 폼·실행·OTP 바인딩 이관 — app.js 에서 절단"
```

---

### Task 5: CSS 이사와 마무리

**Files:**
- Modify: `app/web/frontend/styles/app.css:846-1086` (잘라내기)
- Modify: `app/web/frontend/styles/execute.css` (끝에 붙여넣기)
- Modify: `docs/superpowers/specs/2026-08-24-execute-promotion-design.md` (§8 갱신)

**Interfaces:**
- Consumes: Task 1~4 의 결과
- Produces: 없음

- [x] **Step 1: 프리셋 CSS 를 이사시킨다**

`app/web/frontend/styles/app.css` 의 프리셋 절을 잘라 `execute-presets.css`의 명시적 시작 주석 아래로 옮기고, Cycle 1a 그래프 규칙은 `execute-graph.css`로 분리했다. 실행 셸은 `execute.css`에 남겼다. 세 stylesheet는 `base.css:11~13`에서 각각 한 번씩 임포트한다.

경계는 줄 번호가 아니라 **선택자와 주석으로 잡는다.** 시작은 `/* ===== 인증 프리셋 (내 점검 세트) ===== */`(현재 `:426`), 끝은 다음 섹션 주석(`진행 중 / 최근 Run`) 직전(현재 `:666`)이다. 약 241줄이다.

> **주의:** 이 계획의 초안은 `846~1086` 이라고 적었는데 그것은 **Cycle 1a 이전 좌표**다. 1a 가 `app.css` 에서 420줄을 덜어내 전부 앞으로 당겨졌다. 지금 `846~1086` 을 자르면 프리셋이 아니라 모바일 내비게이션 등 **살아 있는 CSS** 를 지운다. 자르기 전에 시작·끝 줄을 눈으로 확인해라.

옮긴 뒤 남은 hex 가 있으면 `var(--c-*)` 로 바꾼다 — `styles/execute.css` 는 FG-002 allowlist 에 없다.

Run: `python3 scripts/check_frontend_gates.py`
Expected: 통과. 세 stylesheet는 각각 400줄 미만이다.

- [x] **Step 2: app.js 잔여를 확인한다**

Run: `wc -l app/web/static/app.js`
Expected: 약 1,850줄(3,263 − 약 1,400). 남은 것은 Run 이력 · Run 상세 · Suite 상세 · 예약 오버뷰 · 공용이며 Cycle 2~4 의 몫이다.

Run: `grep -c "function " app/web/static/app.js`

실측: `app.js` 1,949줄, `function ` 86개. 계획의 약 1,850줄과 달라 잔여 목표는 미충족으로 기록한다.

- [x] **Step 3: 전체 검증**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
최종 검증 증거: 커밋 `b514fdb`에서 사용자 제공 결과 `passed=true`, `profile=full`, `gate_count=16`, `ruff_format` 548개 파일 통과. 이후 문서 커밋은 code rerun이 아니다.
Run: `npm run test && npm run typecheck && npm run lint && npm run build`
Run: `python3 -m pytest tests/test_execute_layout.py tests/test_execute_viewport.py -v`
Expected: 전부 통과

- [x] **Step 4: 설계 문서의 §8 을 갱신한다**

`docs/superpowers/specs/2026-08-24-execute-promotion-design.md` §8에 Cycle 1b 구현 실측과 사용자 제공 최종 gate 통과를 기록하고, `app.css` 잔여 줄 수를 실측값으로 고친다.

- [x] **Step 5: 커밋**

```bash
git add app/web/frontend docs/superpowers/specs/2026-08-24-execute-promotion-design.md
git commit -m "refactor(execute): 프리셋 CSS 이사 — app.css 축소"
```

---

## 완료 확인

- [x] `python3 scripts/ci/run_all_gates.py --profile full` 통과 (사용자 제공 최종 검증 커밋 `b514fdb`: `passed=true`, `profile=full`, `gate_count=16`, `ruff_format` 548개 파일)
- [x] `npm run test && npm run typecheck && npm run lint && npm run build` 통과
- [x] `app/web/frontend/entries/execute.ts` 존재, 15줄
- [x] `app.js` 에 모듈 그래프 · 프리셋 · 실행 폼 함수 0개
- [ ] `app.js` 약 1,850줄로 축소
- [x] `app.css` 750줄로 축소(991 − 프리셋 절 241). 모듈그래프 167줄은 **1a 가 이미 이사시켰다**
- [x] Vitest 가 그래프 좌표 계산 · 조건부 필드 · 프리셋 적용을 단언
- [ ] `/runs/execute` 에서 실제 Run 과 SUITE 가 끝까지 동작

미검증 항목: Task 4 Step 4의 실제 Run/SUITE·OTP 종단 동작, `app.js` 약 1,850줄 목표(실측 1,949줄), 실제 Run/SUITE 종단 동작 completion은 증거가 없어 체크하지 않았다.

## 이 계획이 남기는 것

| 항목 | 다음 단계 |
| --- | --- |
| `app.js` 잔여 1,949줄 | Cycle 2(수트) → 3(런) → 4(Run 이력, 여기서 소멸) |
| `FG005_ALLOWLIST` 의 `/static/app.js` | Cycle 4 |
| `FG004_ALLOWLIST` 의 `app.css` | Cycle 2~6 이 절씩 이사 |
| `execute/legacy-bridge.ts` | Cycle 4 에서 `app.js` 와 함께 소멸 |
| 화면 폴더 관례(`frontend/execute/`) | Cycle 2~6 이 같은 모양으로 따른다 |
