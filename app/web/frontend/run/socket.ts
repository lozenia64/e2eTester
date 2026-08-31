// Run 상세 소켓·진행률·로그 렌더. 상태 규칙과 OTP 패널은 각 소유 모듈을 직접 쓴다.
import { normalizeTone, statusLabel } from "../components/status-badge/index";
import { updateOtpPanel } from "../components/otp-panel/index";
import {
  exportText,
  isFilterManual,
  pushLog,
  resetLog,
  setModuleFilter,
  setSearch,
  visibleEntries,
  type LogEntry,
} from "./log";
import { applyFocus, moduleRuntimeState, updateModuleCard } from "./modules";
import { formatClock, summarizeModules } from "./progress";
import { updateRunActions } from "./actions";

type RecordValue = Record<string, unknown>;
type SocketMessage = { event_type?: string; payload?: unknown; run_status?: unknown };

let runtimeTicker: number | null = null;
let logControlsBound = false;
let hasLogEntries = false;

function record(value: unknown): RecordValue | null {
  return value !== null && typeof value === "object" ? (value as RecordValue) : null;
}

function currentRunId(): string {
  return document.getElementById("node-grid")?.dataset.runId
    ?? document.getElementById("run-root")?.dataset.runId
    ?? "run";
}

function createLogLineNode(entry: LogEntry): HTMLDivElement {
  const line = document.createElement("div");
  line.className = "log-line";
  line.dataset.moduleId = entry.moduleId;
  line.textContent = entry.moduleId ? `[${entry.moduleId}] ${entry.message}` : entry.message;
  return line;
}

function renderLogConsole(): void {
  const consoleNode = document.getElementById("log-console");
  if (!consoleNode) return;
  const entries = visibleEntries();
  consoleNode.replaceChildren(...entries.map(createLogLineNode));
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "log-empty";
    empty.textContent = hasLogEntries ? "조건에 맞는 로그가 없습니다." : "아직 출력된 로그가 없습니다.";
    consoleNode.appendChild(empty);
  }
  consoleNode.scrollTop = consoleNode.scrollHeight;
}

function appendLogEntry(entry: LogEntry): void {
  pushLog(entry);
  hasLogEntries = true;
  const consoleNode = document.getElementById("log-console");
  if (!consoleNode) return;
  const visible = visibleEntries();
  if (visible.at(-1) !== entry) {
    renderLogConsole();
    return;
  }
  const empty = consoleNode.querySelector(".log-empty");
  if (empty) empty.remove();
  const nearBottom = consoleNode.scrollHeight - consoleNode.scrollTop - consoleNode.clientHeight < 48;
  consoleNode.appendChild(createLogLineNode(entry));
  if (nearBottom) consoleNode.scrollTop = consoleNode.scrollHeight;
}

function resetLogFromRun(runPayload: unknown): void {
  const rawModules = record(runPayload)?.modules;
  const modules = Array.isArray(rawModules) ? [...rawModules] : [];
  modules.sort((left, right) => Number(record(left)?.order ?? 0) - Number(record(right)?.order ?? 0));
  const entries: LogEntry[] = [];
  for (const module of modules) {
    const payload = record(module);
    const logs = Array.isArray(payload?.logs) ? payload.logs : [];
    for (const line of logs) {
      entries.push({ moduleId: String(payload?.module_id ?? ""), message: String(line) });
    }
  }
  resetLog(entries);
  hasLogEntries = entries.length > 0;
  renderLogConsole();
}

function bindLogControls(): void {
  if (logControlsBound) return;
  logControlsBound = true;
  const filter = document.getElementById("log-filter") as HTMLSelectElement | null;
  const search = document.getElementById("log-search") as HTMLInputElement | null;
  const copyButton = document.getElementById("log-copy") as HTMLButtonElement | null;
  const downloadButton = document.getElementById("log-download") as HTMLButtonElement | null;
  if (filter) {
    filter.addEventListener("change", () => {
      setModuleFilter(filter.value, { manual: true });
      renderLogConsole();
    });
  }
  if (search) {
    search.addEventListener("input", () => {
      setSearch(search.value);
      renderLogConsole();
    });
  }
  if (copyButton) {
    copyButton.addEventListener("click", () => void copyLogsToClipboard(copyButton));
  }
  if (downloadButton) downloadButton.addEventListener("click", downloadLogs);
}

async function copyLogsToClipboard(button: HTMLButtonElement): Promise<void> {
  const text = exportText();
  if (!text) return;
  const original = button.textContent;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "복사됨";
  } catch (error) {
    console.error("로그 복사 실패", error);
    button.textContent = "복사 실패";
  }
  window.setTimeout(() => {
    button.textContent = original;
  }, 1500);
}

function downloadLogs(): void {
  const text = exportText();
  if (!text) return;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const filterId = (document.getElementById("log-filter") as HTMLSelectElement | null)?.value ?? "";
  anchor.download = `${currentRunId()}${filterId ? `_${filterId}` : ""}.log`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function renderRunStatus(status: unknown): void {
  const statusNode = document.getElementById("run-status");
  if (!statusNode) return;
  const value = String(status ?? "");
  statusNode.textContent = statusLabel(value);
  statusNode.className = "status-badge";
  statusNode.dataset.size = "md";
  statusNode.dataset.tone = normalizeTone(value);
  statusNode.dataset.status = value;
  updateRunActions(value);
}

function refreshFocusFilterAndProgress(): void {
  const focusedModuleId = applyFocus();
  if (focusedModuleId) {
    setModuleFilter(focusedModuleId);
    if (!isFilterManual()) {
      const filter = document.getElementById("log-filter") as HTMLSelectElement | null;
      if (filter) filter.value = focusedModuleId;
    }
  }
  renderProgress();
  renderLogConsole();
}

export function renderProgress(): void {
  const modules = Array.from(document.querySelectorAll<HTMLElement>("[data-module-id]")).map((card) => ({
    status: card.dataset.status ?? "",
  }));
  const summary = summarizeModules(modules);
  const bar = document.getElementById("run-progress-bar");
  const label = document.getElementById("run-progress-label");
  if (bar) {
    bar.style.width = `${summary.percent}%`;
    bar.classList.toggle("bg-red-500", summary.failed > 0);
    bar.classList.toggle("bg-emerald-500", summary.failed === 0);
  }
  if (label) label.textContent = `통과 ${summary.passed}/${summary.total}`;
  const detail = document.getElementById("run-progress-detail");
  if (detail) detail.textContent = `완료 ${summary.passed + summary.failed}/${summary.total}`;
}

function tickRunningElapsed(): void {
  const now = Date.now();
  for (const [moduleId, state] of moduleRuntimeState.entries()) {
    const card = Array.from(document.querySelectorAll<HTMLElement>("[data-module-id]")).find(
      (candidate) => candidate.dataset.moduleId === moduleId,
    );
    const elapsedNode = card?.querySelector<HTMLElement>('[data-role="module-elapsed"]');
    if (!elapsedNode) continue;
    const isLive = state.status === "running" || state.status === "waiting_input";
    const startedMs = state.startedAt ? new Date(state.startedAt).getTime() : Number.NaN;
    if (isLive && !Number.isNaN(startedMs)) {
      elapsedNode.textContent = `⏱ ${formatClock(now - startedMs)}`;
      elapsedNode.classList.remove("hidden");
      elapsedNode.hidden = false;
    } else {
      elapsedNode.classList.add("hidden");
      elapsedNode.hidden = true;
      elapsedNode.textContent = "";
    }
  }
}

export function startRuntimeTicker(): void {
  if (!document.querySelector("[data-module-id]") || runtimeTicker !== null) return;
  runtimeTicker = window.setInterval(tickRunningElapsed, 1000);
}

function updateComparisonPanel(runPayload: unknown): void {
  const panel = document.getElementById("comparison-panel");
  if (!panel) return;
  const comparison = record(runPayload)?.comparison;
  const data = record(comparison);
  const hasBaseline = Boolean(data?.has_baseline);
  panel.classList.toggle("is-hidden", !hasBaseline);
  panel.hidden = !hasBaseline;
  if (!hasBaseline || !data) return;
  const link = document.getElementById("comparison-baseline-link") as HTMLAnchorElement | null;
  if (link && data.baseline_run_id) {
    link.href = `/runs/${data.baseline_run_id}`;
    link.textContent = `기준 Run: ${data.baseline_run_id}`;
  }
  const body = document.getElementById("comparison-body");
  if (!body) return;
  const groups = [
    { label: "새 이상징후", names: data.newly_failed, cls: "bg-amber-100 text-amber-800" },
    { label: "복구됨", names: data.recovered, cls: "bg-emerald-100 text-emerald-700" },
    { label: "지속 이상징후", names: data.still_failing, cls: "bg-orange-100 text-orange-700" },
  ];
  const chips: HTMLElement[] = [];
  for (const group of groups) {
    for (const name of Array.isArray(group.names) ? group.names : []) {
      const chip = document.createElement("span");
      chip.className = `inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium ${group.cls}`;
      chip.textContent = `${group.label}: ${String(name)}`;
      chips.push(chip);
    }
  }
  if (!chips.length) {
    const note = document.createElement("span");
    note.className = "text-gray-500";
    note.textContent = "직전 실행과 비교해 모듈 상태 변화가 없습니다.";
    chips.push(note);
  }
  body.replaceChildren(...chips);
}

export function bindRunSocket(): void {
  const grid = document.getElementById("node-grid") ?? document.getElementById("run-module-list");
  if (!grid) return;
  bindLogControls();
  const runId = grid.dataset.runId ?? document.getElementById("run-root")?.dataset.runId;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${runId}`);

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data as string) as SocketMessage;
    const payload = record(message.payload);
    if (message.event_type === "snapshot") {
      renderRunStatus(payload?.status);
      updateOtpPanel(message.payload);
      updateComparisonPanel(message.payload);
      resetLogFromRun(message.payload);
      for (const module of Array.isArray(payload?.modules) ? payload.modules : []) updateModuleCard(module);
      refreshFocusFilterAndProgress();
      return;
    }
    if (payload?.module) {
      updateModuleCard(payload.module);
      refreshFocusFilterAndProgress();
    }
    if (message.event_type === "module_log") {
      appendLogEntry({ moduleId: String(payload?.module_id ?? ""), message: String(payload?.message ?? "") });
    }
    if (message.run_status) renderRunStatus(message.run_status);
    if (message.event_type === "module_waiting_input" && payload?.module) {
      updateOtpPanel({
        awaiting_input_module_id: record(payload.module)?.module_id,
        awaiting_input_prompt: "휴대폰으로 받은 OTP를 입력하세요.",
      });
    }
    if (["run_waiting_input", "run_resumed", "run_finished"].includes(message.event_type ?? "")) {
      updateOtpPanel(message.payload);
    }
    if (message.event_type === "run_finished") updateComparisonPanel(message.payload);
  });
}
