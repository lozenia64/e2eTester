import { computeModuleGraphMetrics } from "./layout";
import type { ModuleDef } from "./layout";

const MODULE_GRAPH_MAX_VIEWPORT_HEIGHT = 200;
const moduleGraphResizeObservers = new WeakMap<Element, ResizeObserver>();

export function createModuleGraphNode(module: ModuleDef, position: { depth: number; row: number }, index: number): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "module-graph-node is-selected";
  button.dataset.role = "module-graph-node";
  button.dataset.moduleId = module.module_id;
  button.dataset.moduleName = module.name;
  button.dataset.order = String(module.order ?? index + 1);
  button.dataset.dependsOn = JSON.stringify(module.depends_on ?? []);
  button.dataset.depth = String(position.depth);
  button.dataset.row = String(position.row);
  button.dataset.selected = "true";
  button.style.gridColumn = String(position.depth + 1);
  button.style.gridRow = String(position.row + 1);
  button.setAttribute("aria-pressed", "true");

  const header = document.createElement("div");
  header.className = "module-graph-node__header";
  const order = document.createElement("span");
  order.className = "module-graph-order";
  order.textContent = String(index + 1);
  const title = document.createElement("strong");
  title.className = "module-graph-title";
  title.textContent = module.name;
  header.append(order, title);
  button.appendChild(header);
  button.title = `${index + 1}. ${module.name}`;
  return button;
}

export function getModuleGraphNodes(form: ParentNode): HTMLButtonElement[] {
  return Array.from(form.querySelectorAll<HTMLButtonElement>('[data-role="module-graph-node"]'));
}

export function buildModuleNodeMap(form: ParentNode): Map<string, HTMLButtonElement> {
  return new Map(getModuleGraphNodes(form).map((node) => [node.dataset.moduleId ?? "", node]));
}

export function buildModuleChildrenMap(nodes: HTMLButtonElement[]): Map<string, string[]> {
  const childrenById = new Map(nodes.map((node) => [node.dataset.moduleId ?? "", [] as string[]]));
  for (const node of nodes) {
    for (const dependency of JSON.parse(node.dataset.dependsOn || "[]") as string[]) {
      if (!childrenById.has(dependency)) childrenById.set(dependency, []);
      childrenById.get(dependency)!.push(node.dataset.moduleId ?? "");
    }
  }
  for (const childIds of childrenById.values()) {
    childIds.sort((left, right) => Number(nodes.find((node) => node.dataset.moduleId === left)?.dataset.order ?? 0) - Number(nodes.find((node) => node.dataset.moduleId === right)?.dataset.order ?? 0));
  }
  return childrenById;
}

export function fitModuleGraphToViewport(form: HTMLFormElement): void {
  const viewport = form.querySelector<HTMLElement>(".module-graph-viewport");
  const canvas = form.querySelector<HTMLElement>('[data-role="module-graph-canvas"]');
  const grid = form.querySelector<HTMLElement>('[data-role="module-graph-grid"]');
  if (!viewport || !canvas || !grid) return;
  const columnCount = Math.max(Number(canvas.dataset.columnCount) || 1, 1);
  const rowCount = Math.max(Number(canvas.dataset.rowCount) || 1, 1);
  const availableWidth = viewport.clientWidth || viewport.getBoundingClientRect().width;
  const { rowHeight, rowGap, columnGap } = computeModuleGraphMetrics(columnCount, rowCount, availableWidth, MODULE_GRAPH_MAX_VIEWPORT_HEIGHT);
  const canvasHeight = (rowCount * rowHeight) + (Math.max(rowCount - 1, 0) * rowGap);
  canvas.style.width = "100%";
  canvas.style.height = `${canvasHeight}px`;
  grid.style.gridTemplateColumns = `repeat(${columnCount}, minmax(0, 1fr))`;
  grid.style.gridTemplateRows = `repeat(${rowCount}, ${rowHeight}px)`;
  grid.style.rowGap = `${rowGap}px`;
  grid.style.columnGap = `${columnGap}px`;
  viewport.dataset.graphCompact = columnCount >= 8 ? "dense" : columnCount >= 5 ? "compact" : "";
  ensureModuleGraphResizeObserver(form);
}

export function drawModuleGraph(form: HTMLFormElement): void {
  const canvas = form.querySelector<HTMLElement>('[data-role="module-graph-canvas"]');
  const svg = form.querySelector<SVGSVGElement>('[data-role="module-graph-edges"]');
  const nodes = getModuleGraphNodes(form);
  if (!canvas || !svg || nodes.length === 0) return;
  const canvasRect = canvas.getBoundingClientRect();
  svg.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 ${Math.ceil(canvasRect.width)} ${Math.ceil(canvasRect.height)}`);
  const nodeMap = new Map(nodes.map((node) => [node.dataset.moduleId, node]));
  for (const node of nodes) {
    for (const dependency of JSON.parse(node.dataset.dependsOn || "[]") as string[]) {
      const sourceNode = nodeMap.get(dependency);
      if (!sourceNode) continue;
      const sourceRect = sourceNode.getBoundingClientRect();
      const targetRect = node.getBoundingClientRect();
      const startX = sourceRect.right - canvasRect.left;
      const startY = sourceRect.top - canvasRect.top + (sourceRect.height / 2);
      const endX = targetRect.left - canvasRect.left;
      const endY = targetRect.top - canvasRect.top + (targetRect.height / 2);
      const controlX = startX + ((endX - startX) / 2);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
      path.setAttribute("class", "module-graph-edge");
      path.classList.add(sourceNode.dataset.selected === "true" && node.dataset.selected === "true" ? "is-active" : "is-muted");
      svg.appendChild(path);
    }
  }
}

export function ensureModuleGraphResizeObserver(form: HTMLFormElement): void {
  const viewport = form.querySelector<HTMLElement>(".module-graph-viewport");
  if (!viewport || moduleGraphResizeObservers.has(viewport)) return;
  const observer = new ResizeObserver(() => {
    window.requestAnimationFrame(() => {
      fitModuleGraphToViewport(form);
      drawModuleGraph(form);
    });
  });
  observer.observe(viewport);
  moduleGraphResizeObservers.set(viewport, observer);
}
