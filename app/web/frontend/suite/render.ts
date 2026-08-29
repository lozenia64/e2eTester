// app.js 의 수트 상단 렌더 묶음(상태 배지·액션·진행률·스냅샷)을 옮겼다.
// 로직은 그대로고, 새로 얹은 것은 두 가지뿐이다:
//   (가) 경과·ETA 를 진행 블록에 렌더한다(설계 §3.3 — 산술은 suite/eta.ts 가 한다)
//   (나) 서버가 준 expanded_step_order 를 그대로 반영한다(설계 D8 — 규칙 재구현 금지)
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import { updateSuiteOtpPanel } from "./actions";
import { computeSuiteEta } from "./eta";
import { computeRunModuleProgress } from "./progress";
import { activeRunPayload, syncSuiteRunProgressSocket } from "./socket";
import { refreshFinishedSuiteStepProgress, updateSuiteStepCard } from "./steps";

export type SuiteStepLike = {
  order: number;
  system_code?: string | null;
  system_name?: string | null;
  run_id?: string | null;
  status?: unknown;
};

export type SuiteLike = {
  status?: unknown;
  steps?: SuiteStepLike[];
  current_step_index?: number;
  started_at?: string | null;
  active_run_id?: string | null;
  awaiting_input_run_id?: string | null;
  awaiting_input_prompt?: string | null;
  expanded_step_order?: number | null;
};

const SUITE_ACTIVE_STATUSES = new Set(["pending", "running", "waiting_input"]);

const ETA_HELD_TEXT = "입력 대기 중 · 계산 보류";
const ETA_PARTIAL_TEXT = "일부 제외";

// 서버가 #suite-root 에 심어 둔 시스템별 baseline(ms). 페이지당 한 번만 읽는다.
let stepBaselines: Record<string, number> | null = null;

function suiteStepBaselines(): Record<string, number> {
  if (stepBaselines === null) {
    const raw = document.getElementById("suite-root")?.dataset.stepBaselines;
    try {
      stepBaselines = raw ? (JSON.parse(raw) as Record<string, number>) : {};
    } catch {
      stepBaselines = {};
    }
  }
  return stepBaselines;
}

function formatClock(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function currentSuiteId(): string {
  return document.getElementById("suite-root")?.dataset.suiteId ?? "";
}

// 수트 배지는 스냅샷 렌더와 소켓 메시지 양쪽에서 같은 방식으로 갱신된다.
export function renderSuiteStatusBadge(status: unknown): void {
  const statusNode = document.getElementById("suite-status");
  if (!statusNode) {
    return;
  }
  statusNode.textContent = statusLabel(String(status ?? ""));
  statusNode.className = "status-badge";
  statusNode.dataset.size = "md";
  statusNode.dataset.tone = normalizeTone(String(status ?? ""));
  statusNode.dataset.status = String(status ?? "");
}

export function updateSuiteActions(status: unknown): void {
  const normalized = String(status ?? "").toLowerCase();
  const isActive = SUITE_ACTIVE_STATUSES.has(normalized);
  const cancelButton = document.getElementById("suite-cancel") as HTMLButtonElement | null;
  if (cancelButton) {
    cancelButton.hidden = !isActive;
    if (!isActive) {
      cancelButton.disabled = false;
      cancelButton.textContent = "전체 점검 취소";
    }
  }
}

export function updateSuiteProgressDetailWithModule(run: unknown): void {
  const detail = document.getElementById("suite-progress-detail");
  const data = run as { system_name?: string; system_code?: string } | null | undefined;
  if (!detail || !data) {
    return;
  }
  const progress = computeRunModuleProgress(run);
  const systemLabel = `${data.system_name} (${String(data.system_code ?? "").toUpperCase()})`;
  if (!progress.label) {
    detail.textContent = `현재: ${systemLabel}`;
    return;
  }
  if (progress.tone === "waiting") {
    detail.textContent = `현재: ${systemLabel} · 모듈 ${progress.label} · OTP 대기`;
    return;
  }
  detail.textContent = `현재: ${systemLabel} · 모듈 ${progress.label}`;
}

export function updateSuiteProgress(suite: SuiteLike): void {
  const steps = suite.steps ?? [];
  const skipped = steps.filter((step) => String(step.status).toLowerCase() === "skipped").length;
  const selectedTotal = steps.length - skipped;
  const passed = steps.filter((step) => String(step.status).toLowerCase() === "passed").length;
  const label = document.getElementById("suite-progress-label");
  const bar = document.getElementById("suite-progress-bar");
  const detail = document.getElementById("suite-progress-detail");
  const currentIndex = suite.current_step_index ?? 0;
  const currentStep = steps.find((step) => step.order === currentIndex) ?? steps[currentIndex];
  if (label) {
    const skippedSuffix = skipped > 0 ? ` (${skipped}개 제외)` : "";
    label.textContent = `통과 ${passed}/${selectedTotal || steps.length}${skippedSuffix}`;
  }
  if (bar) {
    const denominator = selectedTotal || steps.length;
    bar.style.width = denominator > 0 ? `${Math.round((passed / denominator) * 100)}%` : "0%";
  }
  if (detail) {
    if (String(suite.status).toLowerCase() === "waiting_input") {
      const waitingStep = steps.find((step) => step.run_id && step.run_id === suite.awaiting_input_run_id);
      if (waitingStep) {
        detail.textContent = `현재: ${waitingStep.system_name} (${waitingStep.system_code?.toUpperCase() ?? ""}) · OTP 대기`;
      } else {
        detail.textContent = "OTP 입력 대기 중입니다.";
      }
    } else if (
      currentStep
      && String(currentStep.status).toLowerCase() !== "skipped"
      && SUITE_ACTIVE_STATUSES.has(String(suite.status).toLowerCase())
    ) {
      detail.textContent = `현재: ${currentStep.system_name} (${currentStep.system_code?.toUpperCase() ?? ""})`;
    } else {
      detail.textContent = skipped > 0 ? `${skipped}개 시스템이 선택에서 제외되었습니다.` : "";
    }
  }

  updateSuiteEtaBlock(suite, steps, currentStep);
}

// (가) 경과·ETA.
// 화면에 보이는 "경과" 는 수트 전체 경과다 — suite.started_at 에서 잰다(스냅샷 페이로드에
// 바로 있으므로 첫 페인트부터 정확하다). ETA 계산에 들어가는 "현재 스텝 경과" 는 별개로,
// 진행 소켓이 들고 있는 현재 하위 Run 의 started_at 에서 잰다(설계 §3.3). 없으면 0 으로 본다.
function updateSuiteEtaBlock(
  suite: SuiteLike,
  steps: SuiteStepLike[],
  currentStep: SuiteStepLike | undefined,
): void {
  const suiteStartedMs = suite.started_at ? Date.parse(String(suite.started_at)) : Number.NaN;
  const suiteElapsedMs = Number.isNaN(suiteStartedMs) ? 0 : Math.max(0, Date.now() - suiteStartedMs);

  const run = activeRunPayload() as { started_at?: string | null } | null;
  const stepStartedMs = run?.started_at ? Date.parse(run.started_at) : Number.NaN;
  const stepElapsedMs = Number.isNaN(stepStartedMs) ? 0 : Math.max(0, Date.now() - stepStartedMs);

  const elapsedNode = document.getElementById("suite-progress-elapsed");
  if (elapsedNode) {
    elapsedNode.textContent = formatClock(suiteElapsedMs);
  }

  const etaNode = document.getElementById("suite-progress-eta");
  if (!etaNode) {
    return;
  }
  const eta = computeSuiteEta({
    steps: steps.map((step) => ({
      order: step.order,
      system_code: String(step.system_code ?? ""),
      status: String(step.status ?? ""),
    })),
    baselines: suiteStepBaselines(),
    currentStepOrder: currentStep?.order ?? null,
    currentStepElapsedMs: stepElapsedMs,
    suiteStatus: String(suite.status ?? ""),
  });
  const parts: string[] = [];
  if (eta.held) {
    parts.push(ETA_HELD_TEXT);
  } else if (eta.remainingMs !== null) {
    parts.push(`남은 약 ${Math.floor(eta.remainingMs / 60000)}분`);
  }
  if (eta.partial) {
    parts.push(ETA_PARTIAL_TEXT);
  }
  etaNode.textContent = parts.join(" · ");
}

// (나) 자동 펼침. 서버가 준 order 를 그대로 반영만 한다 — 클라이언트는 규칙을 다시 세지 않는다.
// null 이거나(펼칠 것 없음) 비관리자 시야에서 걸러진 order 면 아무 행도 펼치지 않는다.
function applyExpandedStep(order: number | null): void {
  for (const row of document.querySelectorAll<HTMLElement>("#suite-step-list .suite-step")) {
    if (order !== null && Number(row.dataset.stepOrder) === order) {
      row.dataset.expanded = "true";
    } else {
      delete row.dataset.expanded;
    }
  }
}

export function renderSuiteSnapshot(suite: unknown): void {
  const data = suite as SuiteLike;
  renderSuiteStatusBadge(data.status);
  updateSuiteActions(data.status);
  updateSuiteProgress(data);
  updateSuiteOtpPanel(data);
  for (const step of data.steps ?? []) {
    updateSuiteStepCard(step);
  }
  applyExpandedStep(data.expanded_step_order ?? null);
  syncSuiteRunProgressSocket(data);
  refreshFinishedSuiteStepProgress(data);
}
