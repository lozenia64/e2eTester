// app.js 의 수트 소켓 묶음(수트 WS + 현재 하위 Run 진행 WS)을 로직 변경 없이 옮겼다.
// 한 번에 하나의 하위 Run 만 구독한다 — 활성 Run 이 바뀌면 이전 소켓을 닫고 새로 연다.
import { refreshSuiteOtpCountdown } from "./actions";
import { resolveActiveSuiteRunId } from "./modules";
import { renderSuiteSnapshot, renderSuiteStatusBadge, updateSuiteActions, type SuiteLike } from "./render";
import { updateSuiteStepModuleProgress } from "./steps";

const SUITE_RUN_PROGRESS_REFRESH_EVENTS = new Set([
  "snapshot",
  "module_queued",
  "module_started",
  "module_finished",
  "module_waiting_input",
  "run_waiting_input",
  "run_resumed",
  "run_finished",
  "run_started",
]);

let suiteRunProgressSocket: WebSocket | null = null;
let suiteRunProgressRunId: string | null = null;
// 현재 구독 중인 하위 Run 의 마지막 페이로드. render.ts 가 경과(started_at)를,
// actions.ts 가 OTP 카운트다운(awaiting_input_module_id)을 여기서 읽는다.
let suiteRunProgressPayload: unknown = null;

export function activeRunProgressRunId(): string | null {
  return suiteRunProgressRunId;
}

export function activeRunPayload(): unknown {
  return suiteRunProgressPayload;
}

function noteRunPayload(run: unknown): void {
  const runId = (run as { run_id?: string } | null | undefined)?.run_id;
  if (runId && runId === suiteRunProgressRunId) {
    suiteRunProgressPayload = run;
    // 페이로드가 이제야 도착했다 — 대기 중이면 카운트다운을 실제 started_at 으로 교정한다.
    // 수트 WS 는 OTP 대기 중 아무 이벤트도 내지 않으므로 여기서 몰지 않으면 영영 못 고친다.
    refreshSuiteOtpCountdown();
  }
}

export async function refreshSuiteRunProgress(runId: string | null | undefined): Promise<void> {
  if (!runId) {
    return;
  }
  try {
    const response = await fetch(`/api/runs/${runId}`);
    if (!response.ok) {
      return;
    }
    const run: unknown = await response.json();
    noteRunPayload(run);
    updateSuiteStepModuleProgress(run);
  } catch (error) {
    console.error(error);
  }
}

export function closeSuiteRunProgressSocket(): void {
  if (suiteRunProgressSocket) {
    suiteRunProgressSocket.close();
    suiteRunProgressSocket = null;
  }
  suiteRunProgressRunId = null;
  suiteRunProgressPayload = null;
}

export function syncSuiteRunProgressSocket(suite: SuiteLike): void {
  const runId = resolveActiveSuiteRunId(suite);
  if (!runId) {
    closeSuiteRunProgressSocket();
    return;
  }
  if (runId === suiteRunProgressRunId && suiteRunProgressSocket) {
    void refreshSuiteRunProgress(runId);
    return;
  }

  closeSuiteRunProgressSocket();
  suiteRunProgressRunId = runId;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  suiteRunProgressSocket = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${runId}`);

  suiteRunProgressSocket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data as string) as { event_type?: string; payload?: unknown };
    if (message.event_type === "snapshot") {
      noteRunPayload(message.payload);
      updateSuiteStepModuleProgress(message.payload);
      return;
    }
    if (message.event_type && SUITE_RUN_PROGRESS_REFRESH_EVENTS.has(message.event_type)) {
      void refreshSuiteRunProgress(runId);
    }
  });

  suiteRunProgressSocket.addEventListener("close", () => {
    if (suiteRunProgressRunId === runId) {
      suiteRunProgressRunId = null;
      suiteRunProgressSocket = null;
    }
  });

  void refreshSuiteRunProgress(runId);
}

export function bindSuiteSocket(): void {
  const root = document.getElementById("suite-root");
  if (!root) {
    return;
  }

  const suiteId = root.dataset.suiteId;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/suites/${suiteId}`);

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data as string) as { event_type?: string; payload?: unknown };
    const suite = (message.payload ?? message) as SuiteLike;

    if (message.event_type === "snapshot") {
      renderSuiteSnapshot(suite);
      return;
    }

    if (suite.status) {
      renderSuiteStatusBadge(suite.status);
      updateSuiteActions(suite.status);
    }

    renderSuiteSnapshot(suite);
  });
}
