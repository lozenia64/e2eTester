// Run 상세의 OTP·취소·재실행 액션. app.js 전역 다리 없이 이 화면 안에서 끝낸다.
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

const RUN_ACTIVE_STATUSES = new Set(["pending", "running", "waiting_input"]);

type Tone = keyof typeof FEEDBACK_TONE_CLASSES;

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? JSON.stringify(payload);
  } catch {
    return await response.text();
  }
}

function setInlineFeedback(element: HTMLElement | null, message: string, tone: Tone = "error"): void {
  if (!element) return;
  for (const toneClass of Object.values(FEEDBACK_TONE_CLASSES)) {
    element.classList.remove(toneClass);
  }
  if (!message) {
    element.classList.add("is-hidden");
    element.hidden = true;
    element.textContent = "";
    return;
  }
  element.classList.add(FEEDBACK_TONE_CLASSES[tone]);
  element.classList.remove("is-hidden");
  element.hidden = false;
  element.textContent = message;
}

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

function currentRunId(): string {
  return document.getElementById("node-grid")?.dataset.runId
    ?? document.getElementById("run-root")?.dataset.runId
    ?? "run";
}

function otpFeedbackNode(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[data-role="otp-feedback"]');
}

async function submitOtp(runId: string, otpCode: string, form: HTMLFormElement): Promise<void> {
  const button = form.querySelector<HTMLButtonElement>("button[type='submit']");
  const feedback = otpFeedbackNode();
  setInlineFeedback(feedback, "");
  if (button) {
    button.disabled = true;
    button.textContent = "제출 중...";
  }

  try {
    const response = await fetch(`/api/runs/${runId}/otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ otp_code: otpCode }),
    });
    if (!response.ok) {
      const errorBody = await readErrorMessage(response);
      throw new Error(errorBody || `OTP 제출에 실패했습니다. (${response.status})`);
    }
    form.reset();
    setInlineFeedback(feedback, "OTP가 제출되었습니다. 인증 완료까지 잠시 기다려 주세요.", "success");
  } catch (error) {
    const message = error instanceof Error ? error.message.replace(/^Error:\s*/, "") : "";
    setInlineFeedback(feedback, `OTP 제출에 실패했습니다: ${message}`);
    console.error(error);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "OTP 제출";
    }
  }
}

export function bindOtpForm(): void {
  const form = document.getElementById("otp-form") as HTMLFormElement | null;
  const panel = document.getElementById("otp-panel");
  if (!form || !panel) return;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const runId = panel.dataset.runId ?? currentRunId();
    const otpCode = String(new FormData(form).get("otp_code") ?? "").trim();
    if (!otpCode) {
      setInlineFeedback(otpFeedbackNode(), "OTP 코드를 입력하세요.");
      return;
    }
    void submitOtp(runId, otpCode, form);
  });
}

// 소켓의 상태 이벤트도 같은 규칙으로 액션을 동기화한다.
export function updateRunActions(status: unknown): void {
  const isActive = RUN_ACTIVE_STATUSES.has(String(status ?? "").toLowerCase());
  const cancelButton = document.getElementById("run-cancel") as HTMLButtonElement | null;
  const rerunButton = document.getElementById("run-rerun") as HTMLButtonElement | null;
  if (cancelButton) {
    cancelButton.classList.toggle("hidden", !isActive);
    cancelButton.hidden = !isActive;
    if (!isActive) {
      cancelButton.disabled = false;
      cancelButton.textContent = "실행 취소";
    }
  }
  if (rerunButton) {
    rerunButton.classList.toggle("hidden", isActive);
    rerunButton.hidden = isActive;
  }
}

async function cancelRun(button: HTMLButtonElement): Promise<void> {
  if (!window.confirm("진행 중인 Run을 취소하시겠습니까? 실행 중인 단계가 끝난 뒤 중단됩니다.")) return;
  button.disabled = true;
  button.textContent = "취소 요청됨...";
  try {
    const response = await fetch(`/api/runs/${currentRunId()}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error(await readErrorMessage(response));
  } catch (error) {
    button.disabled = false;
    button.textContent = "실행 취소";
    showToast(`취소에 실패했습니다: ${error instanceof Error ? error.message : ""}`);
    console.error(error);
  }
}

async function rerunRun(button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  button.textContent = "재실행 중...";
  try {
    const response = await fetch(`/api/runs/${currentRunId()}/rerun`, { method: "POST" });
    if (!response.ok) throw new Error(await readErrorMessage(response));
    const run = (await response.json()) as { run_id: string };
    window.location.href = `/runs/${run.run_id}`;
  } catch (error) {
    button.disabled = false;
    button.textContent = "동일 조건으로 재실행";
    showToast(`재실행에 실패했습니다: ${error instanceof Error ? error.message : ""}`);
    console.error(error);
  }
}

export function bindRunActions(): void {
  const cancelButton = document.getElementById("run-cancel") as HTMLButtonElement | null;
  const rerunButton = document.getElementById("run-rerun") as HTMLButtonElement | null;
  if (cancelButton) cancelButton.addEventListener("click", () => void cancelRun(cancelButton));
  if (rerunButton) rerunButton.addEventListener("click", () => void rerunRun(rerunButton));
  updateRunActions(document.getElementById("run-status")?.dataset.status);
}
