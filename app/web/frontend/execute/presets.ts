import { applyModuleSelection } from "./module-graph/render";
import { getSelectedModuleIds } from "./module-graph/selection";
import { syncConditionalFields } from "./run-form";

export type Preset = {
  preset_id: string;
  system_code: string;
  system_name: string;
  name: string;
  auth_method: string;
  input_data: Record<string, string>;
  selected_module_ids: string[] | null;
  created_at: string;
  updated_at: string;
};

export type PresetState = {
  presetsBySystem: Record<string, Preset[]>;
  suitePresetSelection: Map<string, string>;
};

const presetState: PresetState = {
  presetsBySystem: {},
  suitePresetSelection: new Map(),
};
const boundPanels = new WeakSet<Element>();
let presetStateListener: (() => void) | null = null;

export function getPresetState(): PresetState {
  return presetState;
}

export function subscribePresetState(listener: () => void): void {
  presetStateListener = listener;
}

const AUTH_METHOD_LABELS: Record<string, string> = {
  phone: "휴대폰인증",
  kakao: "카카오인증",
  finance_certificate: "금융인증서",
  public_certificate: "공동인증서",
};

function authMethodLabel(method: string): string {
  return AUTH_METHOD_LABELS[method] ?? (method || "인증");
}

export function presetSummaryText(preset: Preset): string {
  const parts = [authMethodLabel(preset.auth_method)];
  if (preset.input_data.name) parts.push(preset.input_data.name);
  if (preset.input_data.phone_number) parts.push(preset.input_data.phone_number);
  return parts.join(" · ");
}

function setInlineFeedback(element: Element | null, message: string, tone = "error"): void {
  if (!(element instanceof HTMLElement)) return;
  for (const toneClass of ["text-red-600", "text-emerald-600", "text-gray-500"]) element.classList.remove(toneClass);
  if (!message) {
    element.classList.add("is-hidden");
    element.textContent = "";
    return;
  }
  element.classList.add(tone === "success" ? "text-emerald-600" : tone === "info" ? "text-gray-500" : "text-red-600");
  element.classList.remove("is-hidden");
  element.textContent = message;
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string };
    return payload.detail ?? JSON.stringify(payload);
  } catch {
    return response.text();
  }
}

function collectFormInput(form: HTMLFormElement): Record<string, string> {
  const inputData: Record<string, string> = {};
  for (const [key, value] of new FormData(form).entries()) inputData[key] = String(value).trim();
  return inputData;
}

export function applyPresetToForm(form: HTMLFormElement, preset: Preset): void {
  const keys = Object.keys(preset.input_data).sort((left, right) => Number(right === "auth_method") - Number(left === "auth_method"));
  for (const key of keys) {
    if (key === "browser_mode") continue;
    const field = form.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(`[name="${key}"]`);
    if (field) field.value = preset.input_data[key] ?? "";
  }
  syncConditionalFields(form);
  applyModuleSelection(form, preset.selected_module_ids);
}

export async function loadPresets(): Promise<void> {
  if (!document.querySelector('[data-role="preset-panel"], [data-role="suite-preset-list"]')) return;
  try {
    const response = await fetch("/api/presets");
    if (!response.ok) throw new Error(`프리셋 조회 실패 (${response.status})`);
    presetState.presetsBySystem = {};
    for (const preset of await response.json() as Preset[]) (presetState.presetsBySystem[preset.system_code] ??= []).push(preset);
  } catch (error) {
    console.error(error);
    presetState.presetsBySystem = {};
  }
  renderAllPresetUI();
}

function renderAllPresetUI(): void {
  renderIndividualPresetPanels();
  renderSuitePresetLists();
  presetStateListener?.();
}

function renderIndividualPresetPanels(): void {
  for (const panel of document.querySelectorAll<HTMLElement>('[data-role="preset-panel"]')) {
    const list = panel.querySelector<HTMLElement>('[data-role="preset-list"]');
    const form = panel.closest<HTMLFormElement>("form");
    if (!list || !form) continue;
    list.dataset.loading = "false";
    list.innerHTML = "";
    const presets = presetState.presetsBySystem[panel.dataset.systemCode ?? ""] ?? [];
    if (!presets.length) {
      const empty = document.createElement("span");
      empty.className = "preset-empty";
      empty.textContent = "저장된 프리셋이 없습니다. 아래에 정보를 입력한 뒤 저장하면 다음부터 원클릭으로 불러옵니다.";
      list.appendChild(empty);
      continue;
    }
    for (const preset of presets) list.appendChild(buildPresetChip(preset, form));
  }
}

function buildPresetChip(preset: Preset, form: HTMLFormElement): HTMLElement {
  const chip = document.createElement("div");
  chip.className = "preset-chip";
  chip.dataset.presetId = preset.preset_id;
  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "preset-chip__apply";
  apply.title = "이 프리셋으로 폼을 채웁니다";
  apply.innerHTML = '<span class="preset-chip__name"></span><span class="preset-chip__meta"></span>';
  apply.querySelector(".preset-chip__name")!.textContent = preset.name;
  apply.querySelector(".preset-chip__meta")!.textContent = presetSummaryText(preset);
  apply.addEventListener("click", () => {
    applyPresetToForm(form, preset);
    chip.classList.add("preset-chip--just-applied");
    window.setTimeout(() => chip.classList.remove("preset-chip--just-applied"), 900);
    setInlineFeedback(form.querySelector('[data-role="preset-feedback"]'), `‘${preset.name}’ 프리셋을 적용했습니다.`, "success");
  });
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "preset-chip__delete";
  remove.title = "프리셋 삭제";
  remove.setAttribute("aria-label", `${preset.name} 프리셋 삭제`);
  remove.textContent = "×";
  remove.addEventListener("click", async (event) => {
    event.stopPropagation();
    if (window.confirm(`‘${preset.name}’ 프리셋을 삭제할까요?`)) await deletePresetById(preset.preset_id, form);
  });
  chip.append(apply, remove);
  return chip;
}

async function submitPresetSave(systemCode: string, form: HTMLFormElement, nameInput: HTMLInputElement, saveForm: HTMLElement, feedback: Element | null, confirmButton: HTMLButtonElement): Promise<void> {
  const name = nameInput.value.trim();
  if (!name) {
    setInlineFeedback(feedback, "프리셋 이름을 입력하세요.");
    nameInput.focus();
    return;
  }
  confirmButton.disabled = true;
  try {
    const response = await fetch("/api/presets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ system_code: systemCode, name, input_data: collectFormInput(form), selected_module_ids: getSelectedModuleIds(form) }) });
    if (!response.ok) throw new Error(await readErrorMessage(response) || `프리셋 저장에 실패했습니다. (${response.status})`);
    const preset = await response.json() as Preset;
    (presetState.presetsBySystem[systemCode] ??= []).push(preset);
    renderAllPresetUI();
    saveForm.classList.add("is-hidden");
    nameInput.value = "";
    setInlineFeedback(feedback, `‘${preset.name}’ 프리셋을 저장했습니다.`, "success");
  } catch (error) {
    setInlineFeedback(feedback, error instanceof Error ? error.message : "프리셋 저장에 실패했습니다.");
    console.error(error);
  } finally {
    confirmButton.disabled = false;
  }
}

async function deletePresetById(presetId: string, form: HTMLFormElement): Promise<void> {
  try {
    const response = await fetch(`/api/presets/${presetId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await readErrorMessage(response) || `프리셋 삭제에 실패했습니다. (${response.status})`);
    for (const code of Object.keys(presetState.presetsBySystem)) {
      presetState.presetsBySystem[code] = (presetState.presetsBySystem[code] ?? []).filter((preset) => preset.preset_id !== presetId);
    }
    for (const [code, selected] of presetState.suitePresetSelection) if (selected === presetId) presetState.suitePresetSelection.delete(code);
    renderAllPresetUI();
    setInlineFeedback(form.querySelector('[data-role="preset-feedback"]'), "프리셋을 삭제했습니다.", "success");
  } catch (error) {
    setInlineFeedback(form.querySelector('[data-role="preset-feedback"]'), error instanceof Error ? error.message : "프리셋 삭제에 실패했습니다.");
    console.error(error);
  }
}

export function bindPresetPanels(root: ParentNode = document): void {
  for (const panel of root.querySelectorAll<HTMLElement>('[data-role="preset-panel"]')) {
    if (boundPanels.has(panel)) continue;
    const form = panel.closest<HTMLFormElement>("form");
    const saveOpen = panel.querySelector<HTMLButtonElement>('[data-role="preset-save-open"]');
    const saveForm = panel.querySelector<HTMLElement>('[data-role="preset-save-form"]');
    const nameInput = panel.querySelector<HTMLInputElement>('[data-role="preset-name-input"]');
    const saveConfirm = panel.querySelector<HTMLButtonElement>('[data-role="preset-save-confirm"]');
    const saveCancel = panel.querySelector<HTMLButtonElement>('[data-role="preset-save-cancel"]');
    const feedback = panel.querySelector('[data-role="preset-feedback"]');
    const systemCode = panel.dataset.systemCode;
    if (!form || !saveOpen || !saveForm || !nameInput || !saveConfirm || !saveCancel || !systemCode) continue;
    boundPanels.add(panel);
    saveOpen.addEventListener("click", () => { saveForm.classList.toggle("is-hidden"); setInlineFeedback(feedback, ""); if (!saveForm.classList.contains("is-hidden")) { nameInput.value = ""; nameInput.focus(); } });
    saveCancel.addEventListener("click", () => { saveForm.classList.add("is-hidden"); setInlineFeedback(feedback, ""); });
    saveConfirm.addEventListener("click", () => { void submitPresetSave(systemCode, form, nameInput, saveForm, feedback, saveConfirm); });
    nameInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); void submitPresetSave(systemCode, form, nameInput, saveForm, feedback, saveConfirm); } });
  }
}

function renderSuitePresetLists(): void {
  const suiteForm = document.getElementById("suite-form");
  if (!(suiteForm instanceof HTMLFormElement)) return;
  for (const list of suiteForm.querySelectorAll<HTMLElement>('[data-role="suite-preset-list"]')) {
    const systemCode = list.dataset.systemCode ?? "";
    const presets = presetState.presetsBySystem[systemCode] ?? [];
    list.dataset.loading = "false";
    list.innerHTML = "";
    const selected = presetState.suitePresetSelection.get(systemCode);
    if (!presets.some((preset) => preset.preset_id === selected)) presetState.suitePresetSelection.delete(systemCode);
    if (!presetState.suitePresetSelection.has(systemCode) && presets.length === 1) presetState.suitePresetSelection.set(systemCode, presets[0]!.preset_id);
    if (!presets.length) {
      const empty = document.createElement("span");
      empty.className = "preset-empty preset-empty--warn";
      empty.textContent = "저장된 프리셋이 없습니다. 개별 점검 화면에서 먼저 저장하세요.";
      list.appendChild(empty);
      continue;
    }
    for (const preset of presets) list.appendChild(buildSuitePresetChip(suiteForm, systemCode, preset));
  }
}

function buildSuitePresetChip(suiteForm: HTMLFormElement, systemCode: string, preset: Preset): HTMLButtonElement {
  const active = presetState.suitePresetSelection.get(systemCode) === preset.preset_id;
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = `preset-chip preset-chip--radio${active ? " is-active" : ""}`;
  chip.dataset.presetId = preset.preset_id;
  chip.setAttribute("aria-pressed", String(active));
  chip.innerHTML = '<span class="preset-chip__check" aria-hidden="true">✓</span><span class="preset-chip__body"><span class="preset-chip__name"></span><span class="preset-chip__meta"></span></span>';
  chip.querySelector(".preset-chip__name")!.textContent = preset.name;
  chip.querySelector(".preset-chip__meta")!.textContent = presetSummaryText(preset);
  chip.addEventListener("click", () => {
    if (presetState.suitePresetSelection.get(systemCode) === preset.preset_id) presetState.suitePresetSelection.delete(systemCode);
    else presetState.suitePresetSelection.set(systemCode, preset.preset_id);
    renderSuitePresetLists();
    presetStateListener?.();
    setInlineFeedback(suiteForm.querySelector('[data-role="suite-feedback"]'), "");
  });
  return chip;
}
