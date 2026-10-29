import { getLegacy } from "./legacy-bridge";
import { getPresetState, subscribePresetState } from "./presets";

const boundForms = new WeakSet<HTMLFormElement>();

function selectedCodes(form: HTMLFormElement): string[] {
  return [...form.querySelectorAll<HTMLInputElement>('[data-role="suite-system-checkbox"]')]
    .filter((box) => box.checked)
    .map((box) => String(box.dataset.systemCode ?? box.value).trim())
    .filter(Boolean);
}

function scopeCodes(form: HTMLFormElement): string[] {
  return [...form.querySelectorAll<HTMLInputElement>('[data-role="suite-system-checkbox"]')]
    .map((box) => String(box.dataset.systemCode ?? box.value).trim())
    .filter(Boolean);
}

function needsAuth(form: HTMLFormElement, code: string): boolean {
  return form.querySelector<HTMLInputElement>(
    `[data-role="suite-system-checkbox"][data-system-code="${code}"]`,
  )?.dataset.authRequired === "true";
}

function missingPresets(form: HTMLFormElement): string[] {
  const state = getPresetState();
  return selectedCodes(form).filter((code) => {
    const chosen = state.suitePresetSelection.get(code);
    const presets = state.presetsBySystem[code] ?? [];
    return needsAuth(form, code) && (!chosen || !presets.some((preset) => preset.preset_id === chosen));
  });
}

export function updateSuiteSystemSelectorState(form: HTMLFormElement): void {
  const boxes = [...form.querySelectorAll<HTMLInputElement>('[data-role="suite-system-checkbox"]')];
  const selected = new Set(selectedCodes(form));
  const summary = form.querySelector('[data-role="suite-system-selection-summary"]');
  if (summary) {
    summary.textContent = `${selected.size} / ${boxes.length} 선택 · ${boxes.length - selected.size}개 제외`;
  }
  const state = getPresetState();
  for (const panel of form.querySelectorAll<HTMLElement>("[data-suite-auth-for]")) {
    const code = panel.dataset.suiteAuthFor ?? "";
    panel.classList.toggle("is-hidden", !selected.has(code));
    const status = panel.querySelector<HTMLElement>('[data-role="suite-preset-status"]');
    if (!status) continue;
    const presets = state.presetsBySystem[code] ?? [];
    const chosen = state.suitePresetSelection.get(code);
    if (!presets.length) {
      status.textContent = "프리셋 없음";
      status.className = "suite-preset-status suite-preset-status--warn";
    } else if (chosen && presets.some((preset) => preset.preset_id === chosen)) {
      status.textContent = "선택됨";
      status.className = "suite-preset-status suite-preset-status--ok";
    } else {
      status.textContent = "미선택";
      status.className = "suite-preset-status suite-preset-status--pending";
    }
  }
}

type SuiteRequest = {
  browser_mode: string;
  systems: Record<string, Record<string, string>>;
  selected_system_codes: string[];
  scope_system_codes: string[];
};

function collectRequest(form: HTMLFormElement): SuiteRequest {
  const state = getPresetState();
  const codes = selectedCodes(form);
  const systems: Record<string, Record<string, string>> = {};
  for (const code of codes) {
    if (!needsAuth(form, code)) {
      systems[code] = {};
      continue;
    }
    const preset = state.presetsBySystem[code]?.find(
      (item) => item.preset_id === state.suitePresetSelection.get(code),
    );
    if (preset) {
      systems[code] = { ...preset.input_data };
      // 브라우저 모드는 Suite 폼의 공통 선택값만 따른다.
      delete systems[code].browser_mode;
    }
  }
  return {
    browser_mode: String(
      form.querySelector<HTMLSelectElement>('[name="browser_mode"]')?.value ?? "headed",
    ).trim(),
    systems,
    selected_system_codes: codes,
    scope_system_codes: scopeCodes(form),
  };
}

export function collectSuiteScheduleRequest(form: HTMLFormElement): SuiteRequest & { preset_ids: Record<string, string> } {
  const preset_ids: Record<string, string> = {};
  for (const code of selectedCodes(form)) {
    const id = getPresetState().suitePresetSelection.get(code);
    if (needsAuth(form, code) && id) preset_ids[code] = id;
  }
  return {
    browser_mode: String(form.querySelector<HTMLSelectElement>('[name="browser_mode"]')?.value ?? "headed"),
    systems: {},
    preset_ids,
    selected_system_codes: selectedCodes(form),
    scope_system_codes: scopeCodes(form),
  };
}

async function startSuiteRun(button: HTMLButtonElement, form: HTMLFormElement): Promise<void> {
  const legacy = getLegacy();
  const feedback = form.querySelector('[data-role="suite-feedback"]');
  legacy.setInlineFeedback(feedback, "");
  if (!selectedCodes(form).length) {
    legacy.setInlineFeedback(feedback, "최소 1개 시스템을 선택해야 합니다.");
    return;
  }
  const missing = missingPresets(form);
  if (missing.length) {
    legacy.setInlineFeedback(
      feedback,
      `프리셋을 선택해야 하는 시스템: ${missing.map((code) => code.toUpperCase()).join(", ")}. `
      + "프리셋이 없으면 개별 점검 화면에서 먼저 저장하거나, 해당 시스템의 선택을 해제하세요.",
    );
    return;
  }
  button.disabled = true;
  button.textContent = "시작 중...";
  try {
    const response = await fetch("/api/suites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectRequest(form)),
    });
    if (!response.ok) {
      const message = await legacy.readErrorMessage(response);
      throw new Error(message || `전체 점검 생성에 실패했습니다. (${response.status})`);
    }
    const suite = await response.json() as { suite_id: string };
    window.location.href = `/suites/${suite.suite_id}`;
  } catch (error) {
    button.disabled = false;
    button.textContent = "전체 점검 시작";
    const message = error instanceof Error ? error.message.replace(/^Error:\s*/, "") : "";
    legacy.setInlineFeedback(feedback, message || "전체 점검 생성에 실패했습니다.");
    console.error(error);
  }
}

async function registerSuiteSchedule(form: HTMLFormElement, button: HTMLButtonElement): Promise<void> {
  const legacy = getLegacy();
  const feedback = form.querySelector('[data-role="suite-schedule-feedback"]');
  legacy.setInlineFeedback(feedback, "");
  if (!selectedCodes(form).length) {
    legacy.setInlineFeedback(feedback, "최소 1개 시스템을 선택해야 합니다.");
    return;
  }
  const built = legacy.buildScheduleCron(form);
  if (built.error) {
    legacy.setInlineFeedback(feedback, built.error);
    return;
  }
  const missing = missingPresets(form);
  if (missing.length) {
    legacy.setInlineFeedback(
      feedback,
      `프리셋을 선택해야 하는 시스템: ${missing.map((code) => code.toUpperCase()).join(", ")}.`,
    );
    return;
  }
  button.disabled = true;
  button.textContent = "등록 중...";
  try {
    const response = await fetch("/api/schedules/suites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cron: built.cron,
        name: form.querySelector<HTMLInputElement>('[data-role="schedule-name"]')?.value.trim() ?? "",
        ...collectSuiteScheduleRequest(form),
      }),
    });
    if (!response.ok) {
      const message = await legacy.readErrorMessage(response);
      throw new Error(message || `예약 등록에 실패했습니다. (${response.status})`);
    }
    legacy.setInlineFeedback(feedback, "전체 점검 예약이 등록되었습니다.", "success");
    const name = form.querySelector<HTMLInputElement>('[data-role="schedule-name"]');
    if (name) name.value = "";
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

export function bindSuiteForm(root: ParentNode = document): void {
  const form = root.querySelector<HTMLFormElement>("#suite-form");
  if (!form || boundForms.has(form)) return;
  boundForms.add(form);

  for (const box of form.querySelectorAll<HTMLInputElement>('[data-role="suite-system-checkbox"]')) {
    box.addEventListener("change", () => updateSuiteSystemSelectorState(form));
  }
  const selectAll = form.querySelector<HTMLButtonElement>('[data-role="suite-system-select-all"]');
  if (selectAll) {
    selectAll.addEventListener("click", () => {
      for (const box of form.querySelectorAll<HTMLInputElement>('[data-role="suite-system-checkbox"]')) {
        box.checked = true;
      }
      updateSuiteSystemSelectorState(form);
    });
  }
  const deselectAll = form.querySelector<HTMLButtonElement>('[data-role="suite-system-deselect-all"]');
  if (deselectAll) {
    deselectAll.addEventListener("click", () => {
      for (const box of form.querySelectorAll<HTMLInputElement>('[data-role="suite-system-checkbox"]')) {
        box.checked = false;
      }
      updateSuiteSystemSelectorState(form);
    });
  }

  subscribePresetState(() => updateSuiteSystemSelectorState(form));
  updateSuiteSystemSelectorState(form);
  getLegacy().bindScheduleBuilder(form);
  const schedule = form.querySelector<HTMLButtonElement>('[data-role="suite-schedule-register"]');
  if (schedule) {
    schedule.addEventListener("click", () => {
      void registerSuiteSchedule(form, schedule);
    });
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const button = form.querySelector<HTMLButtonElement>("#suite-start-button");
    if (button) void startSuiteRun(button, form);
  });
}
