// app.js 의 수트 스텝 행 갱신 묶음을 로직 변경 없이 옮겼다. 바뀐 것은 마크업 훅뿐이다:
//   .suite-step-card[data-step-index] → li.suite-step[data-step-order]
//   status-{status} 클래스            → data-status (색은 Task 7 의 suite/styles.css)
//   moduleProgressClassName           → data-tone (설계 §3.5 — 톤 클래스를 되살리지 않는다)
//   is-hidden 클래스                  → 네이티브 hidden 속성
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import { buildModuleChips, type ModuleChip } from "./modules";
import { computeRunModuleProgress, type ModuleProgress } from "./progress";
import { renderSuiteSummary, type SuiteLike, type SuiteStepLike } from "./render";
import { refreshSuiteRunProgress } from "./socket";

export function formatStepModuleProgressText(progress: ModuleProgress, stepStatus: unknown): string {
  if (!progress.label) {
    return "";
  }
  const status = String(stepStatus ?? "").toLowerCase();
  if (status === "pending") {
    return "";
  }
  if (progress.tone === "error") {
    return `모듈 ${progress.label} 점검실패${progress.moduleName ? ` · ${progress.moduleName}` : ""}`;
  }
  if (progress.tone === "anomaly" || progress.tone === "failed") {
    return `모듈 ${progress.label} 이상징후${progress.moduleName ? ` · ${progress.moduleName}` : ""}`;
  }
  if (progress.tone === "passed" || status === "passed") {
    return `모듈 ${progress.label} 완료`;
  }
  if (progress.tone === "waiting") {
    return `모듈 ${progress.label} · OTP 대기${progress.moduleName ? ` (${progress.moduleName})` : ""}`;
  }
  return `모듈 ${progress.label} 실행 중${progress.moduleName ? ` · ${progress.moduleName}` : ""}`;
}

// run_id → 최신 run 페이로드. 칩과 상단 요약이 같은 데이터에서 계산하도록 모든 run 페이로드를 여기 모은다.
export const suiteRunCache = new Map<string, unknown>();

const CHIP_ICONS: Partial<Record<string, string>> = {
  passed: "✓",
  error: "✕",
  anomaly: "!",
  blocked: "⊘",
  waiting_input: "OTP",
};

// 같은 모듈의 노드를 유지해 포커스와 실행 중 애니메이션을 보존한다.
export function renderModuleChips(list: HTMLElement, chips: ModuleChip[], runId: string): void {
  const previous = new Map(
    [...list.querySelectorAll<HTMLElement>("li[data-module-id]")].map((li) => [li.dataset.moduleId, li]),
  );
  chips.forEach((chip, index) => {
    let li = previous.get(chip.moduleId);
    const before = li?.dataset.tone;
    if (!li) {
      li = document.createElement("li");
      li.className = "suite-chip";
      li.dataset.moduleId = chip.moduleId;
      const link = document.createElement("a");
      const icon = document.createElement("span");
      icon.setAttribute("aria-hidden", "true");
      link.append(icon, document.createElement("span"));
      li.append(link);
      li.addEventListener("animationend", (event) => {
        if ((event as AnimationEvent).animationName === "suite-pop") delete li!.dataset.pop;
      });
    }
    if (before !== undefined && before !== chip.tone) {
      li.dataset.pop = "";
    }
    li.dataset.tone = chip.tone;
    const link = li.querySelector("a")!;
    link.href = `/runs/${runId}`;
    link.setAttribute("aria-label", `${chip.name} · ${statusLabel(chip.tone)}`);
    const icon = link.children[0] as HTMLElement;
    icon.className = chip.tone === "running" ? "suite-chip__spin" : "suite-chip__icon";
    const iconText = CHIP_ICONS[chip.tone] ?? "";
    if (icon.textContent !== iconText) icon.textContent = iconText;
    const name = link.children[1]!;
    const nameText = chip.tone === "blocked" ? `${chip.name} 차단` : chip.name;
    if (name.textContent !== nameText) name.textContent = nameText;
    if (list.children[index] !== li) list.insertBefore(li, list.children[index] ?? null);
    previous.delete(chip.moduleId);
  });
  for (const li of previous.values()) li.remove();
}

export function findSuiteStepCardByRunId(runId: string | null | undefined): HTMLElement | null {
  if (!runId) {
    return null;
  }
  return document.querySelector<HTMLElement>(`.suite-step[data-run-id="${runId}"]`);
}

export function updateSuiteStepModuleProgress(run: unknown): void {
  const runId = (run as { run_id?: string } | null | undefined)?.run_id;
  if (runId) {
    suiteRunCache.set(runId, run);
  }
  const card = findSuiteStepCardByRunId(runId);
  if (!card) {
    return;
  }
  const progressNode = card.querySelector<HTMLElement>('[data-role="step-module-progress"]');
  if (!progressNode) {
    return;
  }
  // 원본은 배지의 textContent 를 읽었다. 새 계약에서 배지는 한국어 라벨을 담으므로
  // 상태 자체를 들고 있는 행의 data-status 를 읽는다 — 넘어가는 값은 원본과 같다.
  const stepStatus = card.dataset.status ?? "";
  const chips = buildModuleChips(run, stepStatus);
  renderModuleChips(progressNode, chips, runId ?? "");
  // 칩이 시각 정보를 대신하고, 기존 한 줄 요약은 스크린리더용 라벨로 남긴다.
  progressNode.setAttribute("aria-label", formatStepModuleProgressText(computeRunModuleProgress(run), stepStatus));
  progressNode.hidden = chips.length === 0 || stepStatus === "pending";

  renderSuiteSummary();
}

export function updateSuiteStepCard(step: SuiteStepLike): void {
  const card = document.querySelector<HTMLElement>(`.suite-step[data-step-order="${step.order}"]`);
  if (!card) {
    return;
  }
  const status = String(step.status ?? "").toLowerCase();
  card.dataset.runId = step.run_id ?? "";
  card.dataset.status = status;
  const statusNode = card.querySelector<HTMLElement>('[data-role="step-status"]');
  if (statusNode) {
    statusNode.className = "status-badge";
    statusNode.dataset.size = "sm";
    statusNode.dataset.tone = normalizeTone(String(step.status ?? ""));
    statusNode.dataset.status = String(step.status ?? "");
    statusNode.textContent = statusLabel(String(step.status ?? ""));
  }
  const linkNode = card.querySelector<HTMLElement>('[data-role="step-run-link"]');
  if (linkNode) {
    if (status === "skipped") {
      linkNode.innerHTML = '<span class="text-gray-400">건너뜀 (선택 제외)</span>';
    } else if (step.run_id) {
      linkNode.innerHTML = `<a href="/runs/${step.run_id}" class="font-medium text-indigo-600 hover:underline">${step.run_id}</a>`;
    } else {
      linkNode.innerHTML = '<span class="text-gray-400">대기 중</span>';
    }
  }
  // 원본의 ring-2/ring-indigo-200 토글은 status-{status} 클래스와 같은 "상태에서 파생된 표현"이라
  // data-status 로 넘겼다 — Task 7 의 styles.css 가 [data-status="running"] 등으로 준다.

  if (!step.run_id) {
    const progressNode = card.querySelector<HTMLElement>('[data-role="step-module-progress"]');
    if (progressNode) {
      progressNode.replaceChildren();
      progressNode.hidden = true;
    }
  } else {
    const cached = suiteRunCache.get(step.run_id);
    if (cached) updateSuiteStepModuleProgress(cached);
  }
}

export function refreshFinishedSuiteStepProgress(suite: SuiteLike): void {
  for (const step of suite?.steps ?? []) {
    const status = String(step.status).toLowerCase();
    if (!step.run_id) {
      continue;
    }
    if (status === "passed" || status === "anomaly" || status === "error" || status === "failed" || status === "cancelled") {
      void refreshSuiteRunProgress(step.run_id);
    }
  }
}
