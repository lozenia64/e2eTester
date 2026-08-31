// Run 모듈 행 갱신과 초점 반영. 초점 규칙은 focus.ts 한 곳에만 둔다.
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import { computeFocusModuleId, type FocusModule } from "./focus";

type ModuleCardPayload = Record<string, unknown>;

function record(value: unknown): ModuleCardPayload | null {
  return value !== null && typeof value === "object" ? (value as ModuleCardPayload) : null;
}

function setText(root: ParentNode, selector: string, value: unknown): void {
  const node = root.querySelector<HTMLElement>(selector);
  if (node) node.textContent = String(value ?? "");
}

function moduleCards(root: ParentNode): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-module-id]"));
}

export function applyFocus(root: ParentNode = document): string | null {
  const cards = moduleCards(root);
  const modules: FocusModule[] = cards.map((card) => ({
    module_id: card.dataset.moduleId ?? "",
    order: Number(card.dataset.order ?? 0),
    status: card.dataset.status ?? "",
  }));
  const focusedId = computeFocusModuleId(modules);

  for (const card of cards) {
    if (card.dataset.moduleId === focusedId) {
      card.dataset.focus = "true";
    } else {
      delete card.dataset.focus;
    }
  }
  return focusedId;
}

export function updateModuleCard(module: unknown): void {
  const payload = record(module);
  const moduleId = String(payload?.module_id ?? "");
  if (!moduleId) return;

  const card = moduleCards(document).find((candidate) => candidate.dataset.moduleId === moduleId);
  if (!card || !payload) return;

  const status = String(payload.status ?? "").toLowerCase();
  card.dataset.status = status;

  const statusNode = card.querySelector<HTMLElement>('[data-role="module-status"]');
  if (statusNode) {
    statusNode.className = "status-badge";
    statusNode.dataset.tone = normalizeTone(status);
    statusNode.dataset.size = "md";
    statusNode.dataset.status = status;
    statusNode.textContent = statusLabel(status);
  }

  setText(card, '[data-role="module-message"]', payload.message);
  setText(card, '[data-role="module-duration"]', `${payload.duration_ms ?? 0} ms`);
  setText(card, '[data-role="module-artifacts"]', payload.artifact_count);

  const analysis = record(payload.failure_analysis);
  const analysisPanel = card.querySelector<HTMLElement>('[data-role="failure-analysis"]');
  if (analysisPanel) {
    analysisPanel.hidden = !analysis;
    setText(card, '[data-role="analysis-category"]', analysis?.category);
    setText(card, '[data-role="analysis-summary"]', analysis?.user_summary);
    setText(card, '[data-role="analysis-action"]', analysis?.recommended_action);
    setText(card, '[data-role="analysis-details"]', analysis?.developer_details);
  }

  const artifactList = card.querySelector<HTMLElement>('[data-role="module-artifacts-list"]');
  if (artifactList) {
    artifactList.replaceChildren();
    const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
    for (const artifact of artifacts) {
      if (typeof artifact !== "string") continue;
      const link = document.createElement("a");
      link.href = artifact;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.className = "truncate font-medium text-indigo-600 hover:underline";
      link.textContent = artifact.split("/").pop() ?? artifact;
      artifactList.appendChild(link);
    }
  }

  applyFocus();
}
