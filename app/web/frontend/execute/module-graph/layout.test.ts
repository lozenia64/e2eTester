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
    const shuffled = [MODULES[2]!, MODULES[0]!, MODULES[3]!, MODULES[1]!];
    const sorted = sortModulesByOrder(shuffled);
    expect(sorted.map((m) => m.module_id)).toEqual(["login", "list", "detail", "pay"]);
    expect(shuffled[0]!.module_id).toBe("detail");
  });
});
