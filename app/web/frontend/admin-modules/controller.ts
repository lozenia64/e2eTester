import { changedModules, currentSystem, initialState, isDirty, resetDraft, validTime } from "./model";
import { getEl, renderRows, renderRowState, renderSummary, renderSystems } from "./render";
import type { BulkResult, SystemSettings } from "./types";

const errorMessage = (error: unknown) => error instanceof Error ? error.message : "연결에 실패했습니다. 다시 시도하세요.";
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item: { msg?: string }) => item.msg ?? "입력값을 확인하세요.").join(", ") : response.status === 401 ? "로그인이 만료되었습니다. 다시 로그인하세요." : "요청에 실패했습니다. 잠시 후 다시 시도하세요.");
  }
  if (data === null) throw new Error("서버 응답을 확인하지 못했습니다. 다시 시도하세요.");
  return data as T;
}

export class ModulesController {
  private state = initialState();
  private events = new AbortController();
  private disposed = false;
  private pending: (() => void) | null = null;

  constructor(private root: HTMLElement) {
    root.addEventListener("click", event => { void this.click(event); }, { signal: this.events.signal });
    root.addEventListener("input", event => this.input(event), { signal: this.events.signal });
    getEl<HTMLSelectElement>(root, "modules-page-size").addEventListener("change", event => {
      if (this.state.busy) return;
      const value = Number((event.target as HTMLSelectElement).value);
      if ([10, 15].includes(value)) { this.state.pageSize = value; this.state.page = 1; this.showRows(); }
    }, { signal: this.events.signal });
    const dialog = getEl<HTMLDialogElement>(root, "modules-discard-dialog");
    dialog.addEventListener("cancel", () => { this.pending = null; }, { signal: this.events.signal });
    window.addEventListener("beforeunload", event => {
      if (changedModules(this.state).length || this.state.busy) { event.preventDefault(); event.returnValue = ""; }
    }, { signal: this.events.signal });
  }

  async init() {
    this.state.loading = true; this.state.loadError = ""; this.render();
    try {
      const systems = await request<SystemSettings[]>("/api/admin/module-settings");
      if (this.disposed) return;
      if (!Array.isArray(systems)) throw new Error("시스템 목록 형식이 올바르지 않습니다.");
      this.state.systems = systems.map(system => ({ ...system, modules: system.modules.map(m => ({ ...m, draft: String(m.estimated_manual_seconds) })) }));
      if (!currentSystem(this.state)) this.state.selected = systems[0]?.system_code ?? null;
      this.state.page = 1; this.state.feedback = ""; this.state.feedbackError = false;
    } catch (error) { if (!this.disposed) this.state.loadError = errorMessage(error); }
    finally { if (!this.disposed) { this.state.loading = false; this.render(); } }
  }

  private render() { renderSystems(this.root, this.state); renderSummary(this.root, this.state); renderRows(this.root, this.state); }
  private showRows(focusPage?: number) {
    renderRows(this.root, this.state); getEl(this.root, "modules-table-scroll").scrollTop = 0;
    if (focusPage !== undefined) [...this.root.querySelectorAll<HTMLButtonElement>("[data-module-page]")].find(button => Number(button.dataset.modulePage) === focusPage)?.focus({ preventScroll: true });
  }
  private guard(action: () => void) {
    if (!changedModules(this.state).length) { action(); return; }
    this.pending = action;
    getEl(this.root, "modules-discard-message").textContent = `${currentSystem(this.state)?.system_name}의 미저장 변경 ${changedModules(this.state).length}개를 버리고 이동할까요?`;
    getEl<HTMLDialogElement>(this.root, "modules-discard-dialog").showModal();
  }

  private input(event: Event) {
    if (this.state.busy || this.state.loading) return;
    const target = event.target as HTMLInputElement;
    if (target.id === "modules-system-search") { this.state.systemQuery = target.value; renderSystems(this.root, this.state); return; }
    if (target.id === "modules-search") { this.state.moduleQuery = target.value; this.state.page = 1; this.showRows(); return; }
    const m = currentSystem(this.state)?.modules.find(m => m.module_id === target.dataset.moduleId);
    if (!m) return;
    m.draft = target.value; this.state.feedback = "";
    renderRowState(target.closest<HTMLTableRowElement>("tr")!, m);
    renderSummary(this.root, this.state);
  }

  private async click(event: MouseEvent) {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button");
    if (!button || button.disabled || this.state.busy || this.state.loading) return;
    if (button.dataset.systemCode) {
      const code = button.dataset.systemCode;
      if (code !== this.state.selected) this.guard(() => {
        this.state.selected = code; this.state.page = 1; this.state.filter = "all"; this.state.moduleQuery = "";
        getEl<HTMLInputElement>(this.root, "modules-search").value = "";
        this.state.feedback = ""; this.state.feedbackError = false; this.render();
        getEl(this.root, "modules-title").focus({ preventScroll: true });
        if (window.matchMedia?.("(max-width: 760px)").matches) getEl(this.root, "modules-editor").scrollIntoView({ behavior: "auto", block: "start" });
      });
      return;
    }
    if (button.dataset.modulesFilter) {
      this.state.filter = button.dataset.modulesFilter as typeof this.state.filter; this.state.page = 1;
      renderSummary(this.root, this.state); this.showRows(); return;
    }
    if (button.dataset.modulePage) { this.state.page = Number(button.dataset.modulePage); this.showRows(this.state.page); return; }
    switch (button.id) {
      case "modules-prev": this.state.page--; this.showRows(); break;
      case "modules-next": this.state.page++; this.showRows(); break;
      case "modules-reset": resetDraft(this.state); this.render(); break;
      case "modules-save": await this.save(); break;
      case "modules-retry": this.guard(() => { void this.init(); }); break;
      case "modules-keep": this.pending = null; getEl<HTMLDialogElement>(this.root, "modules-discard-dialog").close(); break;
      case "modules-discard": {
        resetDraft(this.state); const action = this.pending; this.pending = null;
        getEl<HTMLDialogElement>(this.root, "modules-discard-dialog").close(); action?.(); break;
      }
    }
  }

  private async save() {
    const system = currentSystem(this.state), changes = changedModules(this.state);
    if (!system || !changes.length || changes.some(m => !validTime(m))) return;
    const modules = changes.map(m => ({ module_id: m.module_id, estimated_manual_seconds: Number(m.draft) }));
    this.state.busy = true; this.state.feedback = "";
    const scroll = getEl(this.root, "modules-table-scroll").scrollTop;
    this.render(); getEl(this.root, "modules-table-scroll").scrollTop = scroll;
    try {
      const result = await request<BulkResult>(`/api/admin/module-settings/systems/${encodeURIComponent(system.system_code)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modules }) });
      if (this.disposed) return;
      if (!Array.isArray(result.saved) || typeof result.ok !== "boolean") throw new Error("저장 결과를 확인하지 못했습니다. 입력값을 유지했습니다.");
      const submitted = new Set(changes.map(m => m.module_id));
      for (const saved of result.saved) {
        const m = system.modules.find(m => m.module_id === saved.module_id);
        if (m && submitted.has(m.module_id) && Number.isSafeInteger(saved.estimated_manual_seconds) && saved.estimated_manual_seconds >= 0) {
          m.estimated_manual_seconds = saved.estimated_manual_seconds; m.draft = String(saved.estimated_manual_seconds); m.is_overridden = true;
        }
      }
      const remaining = system.modules.filter(isDirty);
      const reasons = new Map(Array.isArray(result.failed) ? result.failed.map(f => [f.module_id, f.detail]) : []);
      const label = (m: (typeof remaining)[number]) => reasons.get(m.module_id) ? `${m.name}: ${reasons.get(m.module_id)}` : m.name;
      this.state.feedbackError = !result.ok || remaining.length > 0;
      this.state.feedback = this.state.feedbackError ? `일부 항목을 저장하지 못했습니다. ${remaining.length}개 모듈을 확인하고 다시 저장하세요.${remaining.length ? ` (${remaining.map(label).join(", ")})` : ""}` : `${changes.length}개 모듈의 시간을 저장했습니다.`;
    } catch (error) { if (!this.disposed) { this.state.feedback = errorMessage(error); this.state.feedbackError = true; } }
    finally {
      if (!this.disposed) { this.state.busy = false; this.render(); getEl(this.root, "modules-table-scroll").scrollTop = scroll; }
    }
  }

  destroy() { this.disposed = true; this.events.abort(); }
}
