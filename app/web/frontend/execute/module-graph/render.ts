import { buildModuleGraphLayout, sortModulesByOrder } from "./layout";
import type { ModuleDef } from "./layout";
import { createModuleGraphNode, drawModuleGraph, fitModuleGraphToViewport } from "./draw";
import { toggleModuleSelection, updateModuleSelectorState } from "./selection";

export { applyModuleSelection } from "./selection";

type SystemDefinition = { modules?: ModuleDef[] };

export function parseSystemDefinition(form: HTMLFormElement): SystemDefinition | null {
  const script = form.querySelector<HTMLScriptElement>('[data-role="system-definition"]');
  if (!script) return null;
  try {
    return JSON.parse(script.textContent ?? "") as SystemDefinition;
  } catch (error) {
    console.error("시스템 정의 파싱 실패", error);
    return null;
  }
}

export function renderModuleSelector(form: HTMLFormElement): void {
  const selector = form.querySelector('[data-role="module-selector"]');
  const canvas = form.querySelector<HTMLElement>('[data-role="module-graph-canvas"]');
  const grid = form.querySelector<HTMLElement>('[data-role="module-graph-grid"]');
  const definition = parseSystemDefinition(form);
  if (!selector || !canvas || !grid || !definition?.modules?.length) return;
  const modules = sortModulesByOrder(definition.modules);
  const { layoutByModuleId, maxDepth, maxRow } = buildModuleGraphLayout(modules);
  grid.innerHTML = "";
  for (const [index, module] of modules.entries()) {
    grid.appendChild(createModuleGraphNode(module, layoutByModuleId.get(module.module_id) ?? { depth: 0, row: index }, index));
  }
  canvas.dataset.columnCount = String(Math.max(maxDepth + 1, 1));
  canvas.dataset.rowCount = String(Math.max(maxRow + 1, 1));
  fitModuleGraphToViewport(form);
  grid.addEventListener("click", (event) => {
    const target = event.target;
    const button = target instanceof Element ? target.closest<HTMLButtonElement>('[data-role="module-graph-node"]') : null;
    if (button) toggleModuleSelection(form, button);
  });
  updateModuleSelectorState(form);
}

export function bindModuleSelectors(root: ParentNode = document): void {
  const forms = new Set<HTMLFormElement>();
  for (const selector of root.querySelectorAll('[data-role="module-selector"]')) {
    const form = selector.closest<HTMLFormElement>(".system-form");
    if (form) forms.add(form);
  }
  for (const form of forms) {
    renderModuleSelector(form);
    const details = form.closest<HTMLDetailsElement>("details");
    if (!details) continue;
    details.addEventListener("toggle", () => {
      if (details.open) window.requestAnimationFrame(() => {
        fitModuleGraphToViewport(form);
        drawModuleGraph(form);
      });
    });
  }
  let resizeTimer: number | undefined;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      for (const form of forms) {
        fitModuleGraphToViewport(form);
        drawModuleGraph(form);
      }
    }, 80);
  });
}
