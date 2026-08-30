// app.js 의 수트 스텝 행 갱신 묶음을 로직 변경 없이 옮겼다. 바뀐 것은 마크업 훅뿐이다:
//   .suite-step-card[data-step-index] → li.suite-step[data-step-order]
//   status-{status} 클래스            → data-status (색은 Task 7 의 suite/styles.css)
//   moduleProgressClassName           → data-tone (설계 §3.5 — 톤 클래스를 되살리지 않는다)
//   is-hidden 클래스                  → 네이티브 hidden 속성
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import { computeRunModuleProgress, type ModuleProgress } from "./progress";
import { type SuiteLike, type SuiteStepLike, updateSuiteProgressDetailWithModule } from "./render";
import { activeRunProgressRunId, refreshSuiteRunProgress } from "./socket";

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

export function findSuiteStepCardByRunId(runId: string | null | undefined): HTMLElement | null {
  if (!runId) {
    return null;
  }
  return document.querySelector<HTMLElement>(`.suite-step[data-run-id="${runId}"]`);
}

export function updateSuiteStepModuleProgress(run: unknown): void {
  const runId = (run as { run_id?: string } | null | undefined)?.run_id;
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
  const progress = computeRunModuleProgress(run);
  const text = formatStepModuleProgressText(progress, stepStatus);
  progressNode.textContent = text;
  progressNode.dataset.tone = text ? progress.tone : "muted";
  progressNode.hidden = !text;

  if (runId === activeRunProgressRunId()) {
    updateSuiteProgressDetailWithModule(run);
  }
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
      progressNode.textContent = "";
      progressNode.dataset.tone = "muted";
      progressNode.hidden = true;
    }
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
