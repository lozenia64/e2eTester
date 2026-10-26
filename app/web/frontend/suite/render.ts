// app.js 의 수트 상단 렌더 묶음(상태 배지·액션·진행률·스냅샷)을 옮겼다.
// 로직은 그대로고, 새로 얹은 것은 두 가지뿐이다:
//   (가) 경과·ETA 를 진행 블록에 렌더한다(설계 §3.3 — 산술은 suite/eta.ts 가 한다)
//   (나) 서버가 준 expanded_step_order 를 그대로 반영한다(설계 D8 — 규칙 재구현 금지)
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import { updateSuiteOtpPanel } from "./actions";
import { passRateToDegrees } from "../components/status-hero/index";
import { computeSuiteEta } from "./eta";
import { describeNow, summarizeSuiteModules, type NowCard } from "./modules";
import { activeRunPayload, syncSuiteRunProgressSocket } from "./socket";
import { refreshFinishedSuiteStepProgress, suiteRunCache, updateSuiteStepCard } from "./steps";

export type SuiteStepLike = {
  order: number;
  system_code?: string | null;
  system_name?: string | null;
  run_id?: string | null;
  status?: unknown;
  module_total?: number;
};

export type SuiteLike = {
  status?: unknown;
  steps?: SuiteStepLike[];
  current_step_index?: number;
  started_at?: string | null;
  ended_at?: string | null;
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

// 마지막 수트 스냅샷. 하위 run 페이로드나 1초 시계가 요약만 다시 그릴 때 쓴다.
let lastSuite: SuiteLike | null = null;

export function rememberSuite(suite: SuiteLike): void {
  lastSuite = suite;
}

// 같은 문구면 건드리지 않는다 — 1초 시계가 텍스트 노드를 갈아끼우면 스크린리더가 같은 말을 다시 읽는다.
function setText(id: string, text: string): HTMLElement | null {
  const node = document.getElementById(id);
  if (node && node.textContent !== text) {
    node.textContent = text;
  }
  return node;
}

function formatShortClock(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// 직전 값에서 to 로 짧게 카운트업. 값이 같거나 동작 줄이기면 즉시 대입한다 — 1초 시계가 매번 불러도 움직이지 않는다.
export function animateCount(node: HTMLElement, to: number): void {
  const target = String(to);
  if (node.dataset.value === target && !prefersReducedMotion()) {
    return;
  }
  const from = Number(node.textContent ?? 0) || 0;
  node.dataset.value = String(to);
  const generation = String(Number(node.dataset.animationGeneration ?? 0) + 1);
  node.dataset.animationGeneration = generation;
  if (from === to || prefersReducedMotion() || typeof requestAnimationFrame !== "function") {
    node.textContent = String(to);
    return;
  }
  const startedAt = performance.now();
  const tick = (now: number): void => {
    if (node.dataset.animationGeneration !== generation) {
      return;
    }
    const k = Math.min(1, (now - startedAt) / 600);
    node.textContent = String(Math.round(from + (to - from) * (1 - (1 - k) ** 3)));
    if (k < 1) {
      requestAnimationFrame(tick);
    }
  };
  requestAnimationFrame(tick);
}

function renderNowCard(card: NowCard): void {
  const root = document.getElementById("suite-now");
  if (root) {
    root.dataset.kind = card.kind;
  }
  if (card.kind === "finished") {
    setText("suite-now-eyebrow", card.statusLabel);
    setText("suite-now-title", `통과 ${card.passed} · 실패 ${card.failed}`);
    setText("suite-now-meta", "");
    return;
  }
  if (card.kind === "idle") {
    setText("suite-now-eyebrow", "시작 대기 중");
    setText("suite-now-title", "—");
    setText("suite-now-meta", "");
    return;
  }
  const startedMs = card.moduleStartedAt ? Date.parse(card.moduleStartedAt) : Number.NaN;
  const eyebrow = card.kind === "waiting"
    ? "OTP 입력 대기"
    : Number.isNaN(startedMs)
      ? "지금 실행 중"
      : `지금 실행 중 · ${formatShortClock(Date.now() - startedMs)}`;
  setText("suite-now-eyebrow", eyebrow);
  setText("suite-now-title", card.moduleName ? `${card.systemName} › ${card.moduleName}` : card.systemName);
  setText("suite-now-meta", `시스템 ${card.systemIndex}/${card.systemTotal} · 모듈 ${card.moduleIndex}/${card.moduleTotal}`);
}

// 상단 요약(설계 §2.2): 링 · "지금 실행 중" 카드 · 집계 줄. 칩과 같은 suiteRunCache 에서 계산한다.
export function renderSuiteSummary(): void {
  const suite = lastSuite;
  if (!suite) {
    return;
  }
  const steps = suite.steps ?? [];
  const summary = summarizeSuiteModules(steps, suiteRunCache);

  const ring = document.getElementById("suite-ring");
  if (ring) {
    ring.style.setProperty("--ring-deg", `${passRateToDegrees(summary.done, summary.total)}deg`);
    ring.setAttribute("aria-label", `전체 모듈 진행률 ${summary.percent}%`);
  }
  const ringValue = document.getElementById("suite-ring-value");
  if (ringValue) {
    animateCount(ringValue, summary.percent);
  }

  renderNowCard(describeNow(suite, suiteRunCache, summary));

  setText("suite-count-passed", `✓ ${summary.passed} 통과`);
  setText("suite-count-failed", `✕ ${summary.failed} 실패`);
  const blocked = setText("suite-count-blocked", `⊘ ${summary.blocked} 차단`);
  if (blocked) {
    blocked.hidden = summary.blocked === 0;
  }
  setText("suite-count-remaining", `남음 ${summary.remaining}`);

  const currentIndex = suite.current_step_index ?? 0;
  const currentStep = steps.find((step) => step.order === currentIndex) ?? steps[currentIndex];
  updateSuiteEtaBlock(suite, steps, currentStep);
}

// 1초 시계 — 수트 경과 · 현재 모듈 경과 · ETA 를 이벤트가 없어도 흐르게 한다.
export function startSuiteClock(): void {
  window.setInterval(renderSuiteSummary, 1000);
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
  // 끝난 수트는 ended_at 에서 멈춘다 — 1초 시계가 종료 후에도 경과를 올리지 않게.
  const suiteEndedMs = suite.ended_at ? Date.parse(String(suite.ended_at)) : Number.NaN;
  const suiteNowMs = Number.isNaN(suiteEndedMs) ? Date.now() : suiteEndedMs;
  const suiteElapsedMs = Number.isNaN(suiteStartedMs) ? 0 : Math.max(0, suiteNowMs - suiteStartedMs);

  const run = activeRunPayload() as { started_at?: string | null } | null;
  const stepStartedMs = run?.started_at ? Date.parse(run.started_at) : Number.NaN;
  const stepElapsedMs = Number.isNaN(stepStartedMs) ? 0 : Math.max(0, Date.now() - stepStartedMs);

  const elapsedNode = document.getElementById("suite-progress-elapsed");
  if (elapsedNode) {
    elapsedNode.textContent = `${formatClock(suiteElapsedMs)} 경과`;
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
  rememberSuite(data);
  renderSuiteStatusBadge(data.status);
  updateSuiteActions(data.status);
  renderSuiteSummary();
  updateSuiteOtpPanel(data);
  for (const step of data.steps ?? []) {
    updateSuiteStepCard(step);
  }
  applyExpandedStep(data.expanded_step_order ?? null);
  syncSuiteRunProgressSocket(data);
  refreshFinishedSuiteStepProgress(data);
}
