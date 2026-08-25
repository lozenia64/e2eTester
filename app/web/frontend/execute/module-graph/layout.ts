// 모듈 의존성 그래프의 좌표 계산. DOM 을 모른다.
// app.js:23~330 에서 이관(Cycle 1b). 로직은 그대로이고 타입과 테스트가 붙었다.

export type ModuleDef = {
  module_id: string;
  name: string;
  depends_on?: string[];
  order?: number;
};

export type GraphMetrics = { rowHeight: number; rowGap: number; columnGap: number };

export type GraphLayout = {
  layoutByModuleId: Map<string, { depth: number; row: number }>;
  maxDepth: number;
  maxRow: number;
};

const MODULE_GRAPH_MIN_ROW_HEIGHT = 26;
const MODULE_GRAPH_MAX_ROW_HEIGHT = 40;
const MODULE_GRAPH_MIN_GAP = 4;
const MODULE_GRAPH_MAX_GAP = 6;

export function computeModuleGraphMetrics(
  columnCount: number,
  rowCount: number,
  availableWidth: number,
  availableHeight: number,
): GraphMetrics {
  let rowGap = MODULE_GRAPH_MAX_GAP;
  let columnGap = MODULE_GRAPH_MAX_GAP;
  let rowHeight = MODULE_GRAPH_MAX_ROW_HEIGHT;
  const totalHeight = (height: number, gap: number) => (rowCount * height) + (Math.max(rowCount - 1, 0) * gap);

  if (totalHeight(rowHeight, rowGap) > availableHeight) {
    const gapSpace = Math.max(rowCount - 1, 0) * rowGap;
    rowHeight = Math.floor((availableHeight - gapSpace) / rowCount);
    rowHeight = Math.max(MODULE_GRAPH_MIN_ROW_HEIGHT, Math.min(MODULE_GRAPH_MAX_ROW_HEIGHT, rowHeight));
  }
  if (totalHeight(rowHeight, rowGap) > availableHeight && rowCount > 1) {
    rowGap = Math.floor((availableHeight - (rowCount * rowHeight)) / (rowCount - 1));
    rowGap = Math.max(MODULE_GRAPH_MIN_GAP, Math.min(MODULE_GRAPH_MAX_GAP, rowGap));
  }
  if (columnCount >= 8) {
    rowHeight = Math.min(rowHeight, 28);
    columnGap = MODULE_GRAPH_MIN_GAP;
  } else if (columnCount >= 5) {
    rowHeight = Math.min(rowHeight, 32);
    columnGap = Math.min(columnGap, 5);
  }
  if (availableWidth > 0 && columnCount > 1) {
    const minColumnWidth = 44;
    const widthLimitedGap = Math.floor((availableWidth - (columnCount * minColumnWidth)) / (columnCount - 1));
    if (widthLimitedGap < columnGap) columnGap = Math.max(MODULE_GRAPH_MIN_GAP, widthLimitedGap);
  }
  return { rowHeight, rowGap, columnGap };
}

export function sortModulesByOrder(modules: ModuleDef[]): ModuleDef[] {
  return [...modules].sort((left, right) => Number(left.order ?? 0) - Number(right.order ?? 0));
}

export function buildModuleRelations(modules: ModuleDef[]): {
  modulesById: Map<string, ModuleDef>;
  childrenById: Map<string, string[]>;
} {
  const modulesById = new Map(modules.map((module) => [module.module_id, module]));
  const childrenById = new Map<string, string[]>(modules.map((module) => [module.module_id, []]));
  for (const module of modules) {
    const dependencies = Array.isArray(module.depends_on) ? module.depends_on : [];
    for (const dependency of dependencies) {
      if (!childrenById.has(dependency)) childrenById.set(dependency, []);
      childrenById.get(dependency)!.push(module.module_id);
    }
  }
  for (const childIds of childrenById.values()) {
    childIds.sort((left, right) => Number(modulesById.get(left)?.order ?? 0) - Number(modulesById.get(right)?.order ?? 0));
  }
  return { modulesById, childrenById };
}

function moduleDepth(moduleId: string, modulesById: Map<string, ModuleDef>, cache: Map<string, number>, active: Set<string>): number {
  if (cache.has(moduleId)) return cache.get(moduleId)!;
  if (active.has(moduleId)) return 0;
  const module = modulesById.get(moduleId);
  if (!module) return 0;
  active.add(moduleId);
  const dependencies = Array.isArray(module.depends_on) ? module.depends_on : [];
  const depth = dependencies.length === 0
    ? 0
    : Math.max(...dependencies.map((dependency) => moduleDepth(dependency, modulesById, cache, active))) + 1;
  active.delete(moduleId);
  cache.set(moduleId, depth);
  return depth;
}

export function computeModuleDepth(moduleId: string, modulesById: Map<string, ModuleDef>, cache = new Map<string, number>()): number {
  return moduleDepth(moduleId, modulesById, cache, new Set());
}

export function computeModuleSubtreeHeight(moduleId: string, childrenById: Map<string, string[]>, cache = new Map<string, number>()): number {
  if (cache.has(moduleId)) return cache.get(moduleId)!;
  const childIds = childrenById.get(moduleId) ?? [];
  let height = 1;
  if (childIds.length === 1) height = computeModuleSubtreeHeight(childIds[0]!, childrenById, cache);
  else if (childIds.length > 1) height = childIds.reduce((total, childId) => total + computeModuleSubtreeHeight(childId, childrenById, cache), 0);
  cache.set(moduleId, height);
  return height;
}

export function buildModuleGraphLayout(modules: ModuleDef[]): GraphLayout {
  const { modulesById, childrenById } = buildModuleRelations(modules);
  const depthCache = new Map<string, number>();
  const subtreeHeightCache = new Map<string, number>();
  const layoutByModuleId = new Map<string, { depth: number; row: number }>();
  const visited = new Set<string>();
  function assignModuleRows(moduleId: string, row: number, depth: number): void {
    if (visited.has(moduleId)) return;
    visited.add(moduleId); layoutByModuleId.set(moduleId, { depth, row });
    const childIds = childrenById.get(moduleId) ?? [];
    if (childIds.length === 0) return;
    if (childIds.length === 1) { assignModuleRows(childIds[0]!, row, depth + 1); return; }
    let nextRow = row;
    for (const childId of childIds) {
      assignModuleRows(childId, nextRow, depth + 1);
      nextRow += computeModuleSubtreeHeight(childId, childrenById, subtreeHeightCache);
    }
  }
  const rootModules = modules.filter((module) => (Array.isArray(module.depends_on) ? module.depends_on : []).length === 0);
  let nextRootRow = 0;
  for (const module of rootModules) { assignModuleRows(module.module_id, nextRootRow, 0); nextRootRow += computeModuleSubtreeHeight(module.module_id, childrenById, subtreeHeightCache); }
  for (const [index, module] of modules.entries()) {
    if (!layoutByModuleId.has(module.module_id)) assignModuleRows(module.module_id, nextRootRow + index, computeModuleDepth(module.module_id, modulesById, depthCache));
  }
  let maxDepth = 0; let maxRow = 0;
  for (const [moduleId, position] of layoutByModuleId.entries()) {
    maxDepth = Math.max(maxDepth, position.depth, computeModuleDepth(moduleId, modulesById, depthCache));
    maxRow = Math.max(maxRow, position.row);
  }
  return { layoutByModuleId, maxDepth, maxRow };
}

export function collectDescendantModuleIds(moduleId: string, childrenById: Map<string, string[]>, collectedIds = new Set<string>()): Set<string> {
  const childIds = childrenById.get(moduleId) ?? [];
  for (const childId of childIds) {
    if (collectedIds.has(childId)) continue;
    collectedIds.add(childId);
    collectDescendantModuleIds(childId, childrenById, collectedIds);
  }
  return collectedIds;
}
