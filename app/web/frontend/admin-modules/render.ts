import { changedModules, currentSystem, duration, isDirty, validTime, visibleModules } from "./model";
import { escapeHtml } from "../lib/html";
import type { EditableModule, ModulesState } from "./types";

export const icon = (name: string) => `<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#modules-icon-${name}"></use></svg>`;
export const getEl = <T extends HTMLElement = HTMLElement>(root: HTMLElement, id: string) => root.querySelector<T>(`#${id}`)!;
const text = (root: HTMLElement, id: string, value: string | number) => { getEl(root, id).textContent = String(value); };

export function renderSystems(root: HTMLElement, s: ModulesState) {
  const query = s.systemQuery.trim().toLocaleLowerCase();
  const systems = s.systems.filter(system => `${system.system_name} ${system.system_code}`.toLocaleLowerCase().includes(query));
  text(root, "modules-system-count", systems.length);
  getEl(root, "modules-systems").innerHTML = systems.map(system => `<button type="button" class="mdl-system ${s.selected === system.system_code ? "is-active" : ""}" data-system-code="${escapeHtml(system.system_code)}" aria-pressed="${s.selected === system.system_code}" ${s.busy || s.loading ? "disabled" : ""}><span class="mdl-system-icon">${icon("system")}</span><span class="mdl-system-text"><strong>${escapeHtml(system.system_name)}</strong><small>${escapeHtml(system.system_code)}</small></span><span class="mdl-system-count">${system.modules.length}</span></button>`).join("") || `<p class="mdl-empty">${s.loading ? "불러오는 중…" : s.loadError && !s.systems.length ? "시스템을 불러오지 못했습니다." : !s.systems.length ? "등록된 시스템이 없습니다." : "일치하는 시스템이 없습니다."}</p>`;
}

function badge(m: EditableModule) {
  const [label, tone] = !validTime(m) ? ["값 확인", "invalid"] : isDirty(m) ? ["변경됨", "changed"] : m.is_overridden ? ["별도 설정", "custom"] : ["기본값", "default"];
  return `<span class="mdl-badge is-${tone}">${label}</span>`;
}

export function renderRowState(row: HTMLTableRowElement, m: EditableModule) {
  row.classList.toggle("is-dirty", isDirty(m));
  row.querySelector<HTMLElement>(".mdl-dirty-dot")!.hidden = !isDirty(m);
  row.querySelector<HTMLElement>(".mdl-row-state")!.innerHTML = badge(m);
  row.querySelector<HTMLElement>(".mdl-friendly")!.textContent = validTime(m) ? duration(Number(m.draft)) : "0 이상의 정수";
  const input = row.querySelector<HTMLInputElement>("input")!;
  input.classList.toggle("is-invalid", !validTime(m)); input.setAttribute("aria-invalid", String(!validTime(m)));
}

export function renderRows(root: HTMLElement, s: ModulesState) {
  const modules = visibleModules(s), pages = Math.max(1, Math.ceil(modules.length / s.pageSize));
  s.page = Math.max(1, Math.min(s.page, pages));
  const start = (s.page - 1) * s.pageSize;
  getEl(root, "modules-rows").innerHTML = modules.slice(start, start + s.pageSize).map(m => `<tr class="${isDirty(m) ? "is-dirty" : ""}"><td><span class="mdl-module-name"><span class="mdl-dirty-dot" ${isDirty(m) ? "" : "hidden"}></span>${escapeHtml(m.name)}</span><small class="mdl-module-id">${escapeHtml(m.module_id)}</small></td><td><span class="mdl-default-time">${m.manifest_default.toLocaleString()}초</span></td><td><label class="mdl-time-input"><span class="mdl-sr-only">${escapeHtml(m.name)} 적용 시간</span><input type="number" min="0" step="1" inputmode="numeric" value="${escapeHtml(m.draft)}" data-module-id="${escapeHtml(m.module_id)}" aria-invalid="${!validTime(m)}" ${s.busy ? "disabled" : ""} class="${validTime(m) ? "" : "is-invalid"}"><span>초</span></label><span class="mdl-friendly">${validTime(m) ? duration(Number(m.draft)) : "0 이상의 정수"}</span></td><td class="mdl-row-state">${badge(m)}</td></tr>`).join("");
  getEl(root, "modules-empty").hidden = modules.length > 0;
  text(root, "modules-empty", currentSystem(s)?.modules.length ? "조건에 맞는 모듈이 없습니다." : "등록된 모듈이 없습니다.");
  text(root, "modules-range", modules.length ? `전체 ${modules.length}개 중 ${start + 1}–${Math.min(start + s.pageSize, modules.length)}` : "모듈 0개");
  getEl<HTMLButtonElement>(root, "modules-prev").disabled = s.busy || s.page === 1;
  getEl<HTMLButtonElement>(root, "modules-next").disabled = s.busy || s.page === pages;
  const numbers = Array.from({ length: pages }, (_, i) => i + 1).filter(n => pages <= 5 || n === 1 || n === pages || Math.abs(n - s.page) <= 1);
  getEl(root, "modules-pages").innerHTML = numbers.map((n, i) => (i && n - numbers[i - 1]! > 1 ? '<span aria-hidden="true">…</span>' : "") + `<button type="button" data-module-page="${n}" ${n === s.page ? 'aria-current="page"' : ""} ${s.busy ? "disabled" : ""}>${n}</button>`).join("");
}

export function renderSummary(root: HTMLElement, s: ModulesState) {
  text(root, "modules-total-systems", s.systems.length);
  text(root, "modules-total-count", s.systems.reduce((n, system) => n + system.modules.length, 0));
  text(root, "modules-total-custom", s.systems.reduce((n, system) => n + system.modules.filter(m => m.is_overridden).length, 0));
  getEl(root, "modules-load-error").hidden = !s.loadError;
  text(root, "modules-load-message", s.loadError);
  getEl<HTMLButtonElement>(root, "modules-retry").disabled = s.busy || s.loading;
  getEl<HTMLInputElement>(root, "modules-system-search").disabled = s.busy || s.loading;
  const system = currentSystem(s);
  getEl(root, "modules-editor").hidden = !system;
  if (!system) return;
  const changes = changedModules(s), invalid = changes.some(m => !validTime(m));
  text(root, "modules-title", system.system_name);
  text(root, "modules-system-subtitle", `${system.system_code.toUpperCase()} · ${system.modules.length}개 모듈`);
  text(root, "modules-time-total", system.modules.some(m => !validTime(m)) ? "값 확인 필요" : duration(system.modules.reduce((n, m) => n + Number(m.draft), 0)));
  text(root, "modules-all-count", system.modules.length);
  text(root, "modules-custom-count", system.modules.filter(m => m.is_overridden).length);
  text(root, "modules-dirty-count", changes.length);
  for (const button of root.querySelectorAll<HTMLButtonElement>("[data-modules-filter]")) {
    button.classList.toggle("is-active", button.dataset.modulesFilter === s.filter);
    button.setAttribute("aria-pressed", String(button.dataset.modulesFilter === s.filter)); button.disabled = s.busy;
  }
  text(root, "modules-save-title", s.busy ? "변경사항을 저장하고 있습니다…" : invalid ? "입력한 시간을 확인하세요" : changes.length ? `변경한 모듈 ${changes.length}개` : "모든 변경사항이 저장되었습니다");
  text(root, "modules-save-description", changes.length ? "다른 페이지의 변경사항도 함께 저장됩니다" : "적용 시간은 절감 시간 계산에 사용됩니다");
  getEl(root, "modules-save-state").classList.toggle("has-changes", changes.length > 0);
  getEl<HTMLButtonElement>(root, "modules-save").disabled = s.loading || s.busy || !changes.length || invalid;
  getEl(root, "modules-save").setAttribute("aria-busy", String(s.busy));
  text(root, "modules-save-label", s.busy ? "저장 중…" : "변경사항 저장");
  getEl<HTMLButtonElement>(root, "modules-reset").disabled = s.busy || !changes.length;
  getEl<HTMLInputElement>(root, "modules-search").disabled = s.busy;
  getEl<HTMLSelectElement>(root, "modules-page-size").disabled = s.busy;
  const feedback = getEl(root, "modules-feedback"); feedback.hidden = !s.feedback;
  feedback.textContent = s.feedback; feedback.classList.toggle("is-error", s.feedbackError);
}
