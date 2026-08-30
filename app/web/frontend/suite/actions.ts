// app.js 의 수트 액션 묶음(취소 버튼 · OTP 패널/폼)을 옮겼다.
// app.js 의 공용 헬퍼(readErrorMessage · setInlineFeedback · showToast)는 전역 다리로 빌리지 않고
// 여기에 최소판을 복제했다 — 수트는 app.js 와 아무것도 주고받지 않는다(설계 §3.4 "신규 다리 0개").
// Cycle 4 가 app.js 를 지울 때 원본만 사라진다.
import { moduleStartedAtFromRun, startOtpCountdown, stopOtpCountdown } from "../lib/otp-countdown";
import { currentSuiteId, updateSuiteActions, type SuiteLike } from "./render";
import { activeRunPayload } from "./socket";

const FEEDBACK_TONE_CLASSES = {
  error: "text-red-600",
  success: "text-emerald-600",
  info: "text-gray-500",
} as const;

const TOAST_TONE_CLASSES = {
  error: "border-red-200 bg-red-50 text-red-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  info: "border-gray-200 bg-white text-gray-700",
} as const;

type Tone = keyof typeof FEEDBACK_TONE_CLASSES;

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? JSON.stringify(payload);
  } catch {
    return await response.text();
  }
}

// 폼/패널 안에 인라인 메시지를 표시한다. message 가 비어 있으면 숨긴다.
function setInlineFeedback(element: HTMLElement | null, message: string, tone: Tone = "error"): void {
  if (!element) {
    return;
  }
  for (const toneClass of Object.values(FEEDBACK_TONE_CLASSES)) {
    element.classList.remove(toneClass);
  }
  if (!message) {
    element.hidden = true;
    element.textContent = "";
    return;
  }
  element.classList.add(FEEDBACK_TONE_CLASSES[tone]);
  element.hidden = false;
  element.textContent = message;
}

// 자연스러운 인라인 위치가 없는 동작(수트 취소 등)의 결과를 토스트로 알린다.
function showToast(message: string, tone: Tone = "error"): void {
  const container = document.getElementById("toast-container");
  if (!container) {
    window.alert(message);
    return;
  }
  const toast = document.createElement("div");
  toast.className = `pointer-events-auto max-w-md rounded-xl border px-4 py-3 text-sm font-medium shadow-lg transition-opacity duration-300 ${TOAST_TONE_CLASSES[tone]}`;
  toast.setAttribute("role", "alert");
  toast.textContent = message;
  container.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("opacity-0");
    window.setTimeout(() => toast.remove(), 300);
  }, 4000);
}

export function updateSuiteOtpPanel(suite: SuiteLike): void {
  const panel = document.getElementById("suite-otp-panel");
  if (!panel) {
    return;
  }
  const awaitingRunId = suite.awaiting_input_run_id ?? "";
  const prompt = suite.awaiting_input_prompt ?? "현재 시스템 로그인에서 OTP 입력이 필요합니다.";
  panel.dataset.runId = awaitingRunId;
  const promptNode = document.getElementById("suite-otp-prompt");
  if (promptNode) {
    promptNode.textContent = prompt;
  }
  panel.hidden = !awaitingRunId;

  // (다) OTP 카운트다운.
  if (!awaitingRunId) {
    stopOtpCountdown();
    const countdownNode = document.getElementById("suite-otp-countdown");
    if (countdownNode) {
      countdownNode.hidden = true;
    }
    return;
  }
  refreshSuiteOtpCountdown();
}

// 대기 중일 때만, 실제 started_at 을 알게 된 순간 카운트다운을 다시 건다.
// 진행 소켓의 Run 페이로드는 fetch 가 비동기라 첫 스냅샷보다 늦게 도착한다 — 그래서
// socket.ts 의 noteRunPayload 가 페이로드를 캐시할 때마다 이것을 다시 부른다.
// started_at 을 모르는 동안에는 아예 걸지 않는다: Date.now() 폴백으로 시작하면
// OTP 창 중간에 페이지를 연 사용자에게 남은 시간이 실제보다 길게 보인다.
export function refreshSuiteOtpCountdown(): void {
  const panel = document.getElementById("suite-otp-panel");
  if (!panel || panel.hidden) {
    return;
  }
  const run = activeRunPayload() as { awaiting_input_module_id?: string | null } | null;
  const startedAt = moduleStartedAtFromRun(run, run?.awaiting_input_module_id ?? "");
  if (!startedAt) {
    return;
  }
  const countdownNode = document.getElementById("suite-otp-countdown");
  if (countdownNode) {
    // 공유 타이머는 is-hidden 클래스만 다룬다 — 네이티브 hidden 은 여기서 연다.
    countdownNode.hidden = false;
  }
  // 공유 타이머는 대상 노드를 하나만 기억한다 — 새로 걸기 전에 반드시 먼저 멈춘다.
  stopOtpCountdown();
  startOtpCountdown(startedAt, countdownNode);
}

export async function cancelSuite(button: HTMLButtonElement): Promise<void> {
  if (!window.confirm("진행 중인 전체 점검을 취소하시겠습니까? 현재 시스템 Run도 함께 중단됩니다.")) {
    return;
  }
  button.disabled = true;
  button.textContent = "취소 요청됨...";
  try {
    const response = await fetch(`/api/suites/${currentSuiteId()}/cancel`, { method: "POST" });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
  } catch (error) {
    button.disabled = false;
    button.textContent = "전체 점검 취소";
    showToast(`취소에 실패했습니다: ${(error as Error).message}`);
    console.error(error);
  }
}

export function bindSuiteActions(): void {
  const cancelButton = document.getElementById("suite-cancel") as HTMLButtonElement | null;
  if (cancelButton) {
    cancelButton.addEventListener("click", () => void cancelSuite(cancelButton));
  }
  updateSuiteActions(document.getElementById("suite-status")?.dataset.status);
}

export async function submitSuiteOtp(suiteId: string, otpCode: string, form: HTMLFormElement): Promise<void> {
  const button = form.querySelector<HTMLButtonElement>("button[type='submit']");
  const feedback = document.querySelector<HTMLElement>('[data-role="suite-otp-feedback"]');
  setInlineFeedback(feedback, "");
  if (button) {
    button.disabled = true;
    button.textContent = "제출 중...";
  }

  try {
    const response = await fetch(`/api/suites/${suiteId}/otp`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ otp_code: otpCode }),
    });

    if (!response.ok) {
      const errorBody = await readErrorMessage(response);
      throw new Error(errorBody || `OTP 제출에 실패했습니다. (${response.status})`);
    }

    form.reset();
    setInlineFeedback(feedback, "OTP가 제출되었습니다. 인증 완료까지 잠시 기다려 주세요.", "success");
  } catch (error) {
    setInlineFeedback(feedback, `OTP 제출에 실패했습니다: ${(error as Error).message.replace(/^Error:\s*/, "")}`);
    console.error(error);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "OTP 제출";
    }
  }
}

export function bindSuiteOtpForm(): void {
  const form = document.getElementById("suite-otp-form") as HTMLFormElement | null;
  const panel = document.getElementById("suite-otp-panel");
  if (!form || !panel) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const suiteId = currentSuiteId();
    const otpCode = String(new FormData(form).get("otp_code") || "").trim();
    if (!otpCode) {
      setInlineFeedback(document.querySelector<HTMLElement>('[data-role="suite-otp-feedback"]'), "OTP 코드를 입력하세요.");
      return;
    }
    void submitSuiteOtp(suiteId, otpCode, form);
  });
}
