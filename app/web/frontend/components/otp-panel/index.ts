import { getLegacy } from "../../execute/legacy-bridge";

type OtpRunPayload = {
  awaiting_input_module_id?: string;
  awaiting_input_prompt?: string;
  modules?: unknown[];
  payload?: OtpRunPayload;
};

// 실행 화면과 Run 상세 WebSocket이 함께 쓰는 WAITING_INPUT 패널 갱신 경계.
export function updateOtpPanel(runOrMessage: unknown): void {
  const panel = document.getElementById("otp-panel");
  if (!panel) return;

  const run = runOrMessage as OtpRunPayload;
  const moduleId = run.awaiting_input_module_id ?? run.payload?.awaiting_input_module_id ?? "";
  const prompt = run.awaiting_input_prompt
    ?? run.payload?.awaiting_input_prompt
    ?? "인증문자 발송 후 OTP 입력이 필요하면 이 영역이 활성화됩니다.";

  panel.dataset.awaitingModuleId = moduleId;
  const promptNode = document.getElementById("otp-prompt");
  if (promptNode) promptNode.textContent = prompt;
  panel.classList.toggle("is-hidden", !moduleId);

  const legacy = getLegacy();
  if (moduleId) {
    const startedAt = legacy.moduleStartedAtFromRun(run, moduleId)
      ?? legacy.moduleStartedAtFromRun(run.payload, moduleId);
    legacy.startOtpCountdown(startedAt);
  } else {
    legacy.stopOtpCountdown();
  }
}
