import { getSelectedModuleIds } from "./module-graph/selection";
import { getLegacy } from "./legacy-bridge";

export { updateOtpPanel } from "../components/otp-panel";

const boundForms = new WeakSet<HTMLFormElement>();

export function syncConditionalFields(form: HTMLFormElement): void {
  for (const field of form.querySelectorAll<HTMLElement>(".conditional-field")) {
    const key = field.dataset.showWhenKey;
    const expected = (field.dataset.showWhenValue ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const input = field.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
      "input, select, textarea",
    );
    const controller = key
      ? form.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(`[name="${key}"]`)
      : null;
    const visible = Boolean(controller && input && expected.includes(controller.value));
    field.classList.toggle("is-hidden", !visible);
    if (input) {
      input.disabled = !visible;
      input.required = visible && field.dataset.required === "true";
    }
  }
}

function bindConditionalFields(form: HTMLFormElement): void {
  const keys = new Set(
    [...form.querySelectorAll<HTMLElement>(".conditional-field")]
      .map((field) => field.dataset.showWhenKey)
      .filter(Boolean),
  );
  for (const key of keys) {
    const input = form.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
      `[name="${key}"]`,
    );
    if (!input) continue;
    const sync = () => syncConditionalFields(form);
    input.addEventListener("change", sync);
    input.addEventListener("input", sync);
  }
  syncConditionalFields(form);
}

function collectFormInput(form: HTMLFormElement): Record<string, string> {
  const inputData: Record<string, string> = {};
  for (const [key, value] of new FormData(form).entries()) {
    inputData[key] = String(value).trim();
  }
  return inputData;
}

async function startSystemRun(
  systemCode: string,
  button: HTMLButtonElement,
  form: HTMLFormElement,
): Promise<void> {
  const legacy = getLegacy();
  const feedback = form.querySelector('[data-role="form-feedback"]');
  legacy.setInlineFeedback(feedback, "");
  const authMethod = form.querySelector<HTMLSelectElement>('[name="auth_method"]')?.value;
  if (
    (systemCode === "hom" || systemCode === "mhm")
    && authMethod
    && authMethod !== "phone"
    && authMethod !== "kakao"
  ) {
    legacy.setInlineFeedback(
      feedback,
      `${systemCode.toUpperCase()}에서는 휴대폰인증·카카오인증만 실행할 수 있습니다. 선택한 인증수단은 아직 준비 중입니다.`,
    );
    return;
  }
  const selectedModuleIds = getSelectedModuleIds(form);
  if (!selectedModuleIds.length) {
    legacy.setInlineFeedback(feedback, "최소 1개 이상의 모듈을 선택해야 합니다.");
    return;
  }
  button.disabled = true;
  button.textContent = "시작 중...";
  try {
    const response = await fetch(`/api/runs/systems/${systemCode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input_data: collectFormInput(form),
        selected_module_ids: selectedModuleIds,
      }),
    });
    if (!response.ok) {
      const message = await legacy.readErrorMessage(response);
      throw new Error(message || `Run 생성에 실패했습니다. (${response.status})`);
    }
    const run = await response.json() as { run_id: string };
    window.location.href = `/runs/${run.run_id}`;
  } catch (error) {
    button.disabled = false;
    button.textContent = "점검 시작";
    const message = error instanceof Error ? error.message.replace(/^Error:\s*/, "") : "";
    legacy.setInlineFeedback(feedback, message || "Run 생성에 실패했습니다.");
    console.error(error);
  }
}

async function registerSchedule(
  systemCode: string,
  form: HTMLFormElement,
  button: HTMLButtonElement,
): Promise<void> {
  const legacy = getLegacy();
  const feedback = form.querySelector('[data-role="schedule-feedback"]');
  legacy.setInlineFeedback(feedback, "");
  const nameInput = form.querySelector<HTMLInputElement>('[data-role="schedule-name"]');
  const built = legacy.buildScheduleCron(form);
  if (built.error) {
    legacy.setInlineFeedback(feedback, built.error);
    return;
  }
  const authMethod = form.querySelector<HTMLSelectElement>('[name="auth_method"]')?.value;
  if (
    (systemCode === "hom" || systemCode === "mhm")
    && authMethod
    && authMethod !== "phone"
    && authMethod !== "kakao"
  ) {
    legacy.setInlineFeedback(
      feedback,
      `${systemCode.toUpperCase()}에서는 휴대폰인증·카카오인증만 예약할 수 있습니다.`,
    );
    return;
  }
  const selectedModuleIds = getSelectedModuleIds(form);
  if (!selectedModuleIds.length) {
    legacy.setInlineFeedback(feedback, "최소 1개 이상의 모듈을 선택해야 합니다.");
    return;
  }
  button.disabled = true;
  button.textContent = "등록 중...";
  try {
    const response = await fetch(`/api/schedules/systems/${systemCode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cron: built.cron,
        name: nameInput?.value.trim() ?? "",
        input_data: collectFormInput(form),
        selected_module_ids: selectedModuleIds,
      }),
    });
    if (!response.ok) {
      const message = await legacy.readErrorMessage(response);
      throw new Error(message || `예약 등록에 실패했습니다. (${response.status})`);
    }
    legacy.setInlineFeedback(feedback, "예약이 등록되었습니다.", "success");
    if (nameInput) nameInput.value = "";
    await legacy.refreshScheduleList();
  } catch (error) {
    const message = error instanceof Error ? error.message.replace(/^Error:\s*/, "") : "";
    legacy.setInlineFeedback(feedback, message || "예약 등록에 실패했습니다.");
    console.error(error);
  } finally {
    button.disabled = false;
    button.textContent = "예약 등록";
  }
}

export function bindRunForms(root: ParentNode = document): void {
  for (const form of root.querySelectorAll<HTMLFormElement>(".system-form")) {
    if (boundForms.has(form)) continue;
    boundForms.add(form);
    bindConditionalFields(form);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const button = form.querySelector<HTMLButtonElement>("button[type='submit']");
      if (button && form.dataset.systemCode) {
        void startSystemRun(form.dataset.systemCode, button, form);
      }
    });
    const scheduleButton = form.querySelector<HTMLButtonElement>('[data-role="schedule-register"]');
    if (scheduleButton && form.dataset.systemCode) {
      const legacy = getLegacy();
      legacy.bindScheduleBuilder(form);
      scheduleButton.addEventListener("click", () => {
        void registerSchedule(form.dataset.systemCode!, form, scheduleButton);
      });
    }
  }
}
