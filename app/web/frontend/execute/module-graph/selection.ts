import { collectDescendantModuleIds } from "./layout";
import { buildModuleChildrenMap, buildModuleNodeMap, drawModuleGraph, getModuleGraphNodes } from "./draw";

export function readNodeDependencyIds(node: HTMLButtonElement): string[] {
  return JSON.parse(node.dataset.dependsOn || "[]") as string[];
}

export function findMissingDependencyIds(node: HTMLButtonElement, nodeMap: Map<string, HTMLButtonElement>): string[] {
  return readNodeDependencyIds(node).filter((dependencyId) => nodeMap.get(dependencyId)?.dataset.selected !== "true");
}

export function getSelectedModuleIds(form: HTMLFormElement): string[] {
  return getModuleGraphNodes(form)
    .filter((node) => node.dataset.selected === "true")
    .sort((left, right) => Number(left.dataset.order) - Number(right.dataset.order))
    .map((node) => node.dataset.moduleId ?? "");
}

export function readSelectedModuleIdSet(form: HTMLFormElement): Set<string> {
  return new Set(getSelectedModuleIds(form));
}

export function buildModuleSelectionWarnings(form: HTMLFormElement, selectedModuleIds: Set<string>): string[] {
  const nodeMap = buildModuleNodeMap(form);
  const warnings: string[] = [];
  for (const moduleId of selectedModuleIds) {
    const node = nodeMap.get(moduleId);
    if (!node) continue;
    const missingDependencies = readNodeDependencyIds(node)
      .filter((dependency) => !selectedModuleIds.has(dependency))
      .map((dependency) => nodeMap.get(dependency)?.dataset.moduleName ?? dependency);
    if (missingDependencies.length > 0) warnings.push(`${node.dataset.moduleName}: ${missingDependencies.join(", ")} 선택 필요`);
  }
  return warnings;
}

export function updateModuleSelectorState(form: HTMLFormElement, feedbackMessage = ""): void {
  const summary = form.querySelector<HTMLElement>('[data-role="module-selection-summary"]');
  const warning = form.querySelector<HTMLElement>('[data-role="module-selection-warning"]');
  const nodes = getModuleGraphNodes(form);
  const nodeMap = buildModuleNodeMap(form);
  const selectedIds = readSelectedModuleIdSet(form);
  for (const node of nodes) {
    const selected = node.dataset.selected === "true";
    const locked = !selected && findMissingDependencyIds(node, nodeMap).length > 0;
    node.classList.toggle("is-selected", selected);
    node.classList.toggle("is-unselected", !selected);
    node.classList.toggle("is-locked", locked);
    node.setAttribute("aria-pressed", selected ? "true" : "false");
    node.setAttribute("aria-disabled", locked ? "true" : "false");
  }
  if (summary) summary.textContent = `${selectedIds.size} / ${nodes.length} 선택 · ${nodes.length - selectedIds.size}개 제외`;
  if (warning) {
    const warnings = buildModuleSelectionWarnings(form, selectedIds);
    const message = feedbackMessage || (warnings.length === 0 ? "" : `선행 모듈 누락 가능: ${warnings.join(" / ")}`);
    warning.classList.toggle("is-hidden", message.length === 0);
    warning.textContent = message;
  }
  drawModuleGraph(form);
}

export function applyModuleSelection(form: HTMLFormElement, moduleIds: string[] | null): void {
  const nodes = getModuleGraphNodes(form);
  if (nodes.length === 0) return;
  const selected = moduleIds === null ? null : new Set(moduleIds);
  for (const node of nodes) node.dataset.selected = selected === null || selected.has(node.dataset.moduleId ?? "") ? "true" : "false";
  updateModuleSelectorState(form);
}

export function toggleModuleSelection(form: HTMLFormElement, button: HTMLButtonElement): void {
  const nodes = getModuleGraphNodes(form);
  const nodeMap = buildModuleNodeMap(form);
  if (button.dataset.selected === "true") {
    button.dataset.selected = "false";
    for (const descendantId of collectDescendantModuleIds(button.dataset.moduleId ?? "", buildModuleChildrenMap(nodes))) {
      const descendantNode = nodeMap.get(descendantId);
      if (descendantNode) descendantNode.dataset.selected = "false";
    }
    updateModuleSelectorState(form);
    return;
  }
  const missingDependencyIds = findMissingDependencyIds(button, nodeMap);
  if (missingDependencyIds.length > 0) {
    const names = missingDependencyIds.map((dependencyId) => nodeMap.get(dependencyId)?.dataset.moduleName ?? dependencyId).join(", ");
    updateModuleSelectorState(form, `${button.dataset.moduleName}: ${names} 선택 필요`);
    return;
  }
  button.dataset.selected = "true";
  updateModuleSelectorState(form);
}
