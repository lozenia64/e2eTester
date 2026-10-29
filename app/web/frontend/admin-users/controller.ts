import type { AccessSystem, AdminUser, UserFilter, UsersState } from "./types";
import { dirty, getEl, renderDetail, renderList, selectedUser } from "./render";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = response.status === 401 ? "로그인이 만료되었습니다. 다시 로그인하세요." : "요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((item: { msg?: string }) => item.msg ?? "입력값을 확인하세요.").join(", ");
    } catch { /* JSON이 아닌 서버 오류에도 재시도 가능한 안내를 표시한다. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
const jsonOptions = (method: string, body?: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
const message = (error: unknown) => error instanceof Error ? error.message : "연결에 실패했습니다. 다시 시도하세요.";

export class UsersController {
  private state: UsersState = { users: [], systems: [], selectedId: null, filter: "all", query: "", draft: [], all: false, loading: true, busy: false, systemsReady: false, error: "", detailError: "" };
  private events = new AbortController();
  private timer?: ReturnType<typeof setTimeout>;
  private disposed = false;

  constructor(private root: HTMLElement) {
    root.addEventListener("click", event => { void this.click(event); }, { signal: this.events.signal });
    root.addEventListener("input", event => {
      if ((event.target as HTMLElement).id === "users-search") { this.state.query = (event.target as HTMLInputElement).value; renderList(root, this.state); }
    }, { signal: this.events.signal });
    root.addEventListener("change", event => {
      const target = event.target as HTMLInputElement;
      if (target.closest("#users-checks") && !this.state.busy && this.state.systemsReady && selectedUser(this.state)?.role !== "admin") {
        this.state.draft = [...root.querySelectorAll<HTMLInputElement>("#users-checks input:checked")].map(input => input.value);
        // 체크박스 DOM을 재생성하지 않아 키보드 포커스를 유지한다.
        const code = target.value;
        renderDetail(root, this.state);
        [...root.querySelectorAll<HTMLInputElement>("#users-checks input")].find(input => input.value === code)?.focus();
      }
    }, { signal: this.events.signal });
    getEl<HTMLFormElement>(root, "users-add-form").addEventListener("submit", event => { event.preventDefault(); void this.create(); }, { signal: this.events.signal });
    const dialog = getEl<HTMLDialogElement>(root, "users-add-dialog");
    dialog.addEventListener("cancel", event => { if (this.state.busy) event.preventDefault(); }, { signal: this.events.signal });
    dialog.addEventListener("close", () => getEl(root, "users-add").focus(), { signal: this.events.signal });
    document.addEventListener("click", event => { if (!(event.target as HTMLElement).closest(".usr-more-wrap")) this.closeMenu(); }, { signal: this.events.signal });
    document.addEventListener("keydown", event => {
      if (event.key === "/" && !dialog.open && !(event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) { event.preventDefault(); getEl(root, "users-search").focus(); }
      if (event.key === "Escape") { const open = !getEl(root, "users-actions").hidden; this.closeMenu(); if (open) getEl(root, "users-more").focus(); }
    }, { signal: this.events.signal });
    window.addEventListener("beforeunload", event => { if (dirty(this.state) || this.state.busy) { event.preventDefault(); event.returnValue = ""; } }, { signal: this.events.signal });
  }

  async init() {
    this.state.loading = true; this.state.error = ""; this.render();
    const [users, systems] = await Promise.allSettled([request<AdminUser[]>("/api/admin/users"), request<AccessSystem[]>("/api/admin/systems")]);
    if (this.disposed) return;
    const errors: string[] = [];
    if (users.status === "fulfilled") this.state.users = users.value;
    else errors.push(`사용자 목록: ${message(users.reason)}`);
    this.state.systemsReady = systems.status === "fulfilled";
    if (systems.status === "fulfilled") this.state.systems = systems.value;
    else errors.push(`시스템 목록: ${message(systems.reason)}`);
    this.state.error = errors.join(" "); this.state.loading = false;
    if (!selectedUser(this.state)) this.state.selectedId = this.state.users.find(u => u.role !== "admin")?.user_id ?? this.state.users[0]?.user_id ?? null;
    this.resetDraft(); this.render();
  }

  private render() { renderList(this.root, this.state); renderDetail(this.root, this.state); }
  private resetDraft() {
    this.state.draft = [...(selectedUser(this.state)?.allowed_system_codes ?? [])];
    this.state.all = selectedUser(this.state)?.role === "admin" || (this.state.systemsReady && this.state.systems.length > 0 && this.state.systems.every(s => this.state.draft.includes(s.system_code)));
    this.state.detailError = ""; this.closeMenu();
  }
  private discard() { return !dirty(this.state) || window.confirm("저장하지 않은 권한 변경을 버리고 이동할까요?"); }
  private closeMenu() { getEl(this.root, "users-actions").hidden = true; getEl(this.root, "users-more").setAttribute("aria-expanded", "false"); }
  private notify(text: string) {
    const toast = getEl(this.root, "users-toast"); toast.textContent = text; toast.hidden = false;
    clearTimeout(this.timer); this.timer = setTimeout(() => { toast.hidden = true; }, 3500);
  }

  private async click(event: MouseEvent) {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button");
    if (!button || button.disabled) return;
    if (button.dataset.usersFilter) { this.state.filter = button.dataset.usersFilter as UserFilter; renderList(this.root, this.state); return; }
    if (this.state.busy) return;
    if (button.dataset.userId) {
      if (button.dataset.userId === this.state.selectedId || !this.discard()) return;
      this.state.selectedId = button.dataset.userId; this.resetDraft(); this.render();
      getEl(this.root, "user-name").focus({ preventScroll: true });
      if (window.matchMedia?.("(max-width: 760px)").matches) getEl(this.root, "users-detail").scrollIntoView({ behavior: "auto", block: "start" });
      return;
    }
    switch (button.id) {
      case "users-mode-all":
      case "users-mode-selected":
        if (!this.state.systemsReady || selectedUser(this.state)?.role === "admin") return;
        this.state.all = button.id === "users-mode-all";
        if (this.state.all) this.state.draft = [...new Set([...this.state.systems.map(s => s.system_code), ...this.state.draft])];
        renderDetail(this.root, this.state); break;
      case "users-save": await this.save(); break;
      case "users-more": {
        const menu = getEl(this.root, "users-actions"); menu.hidden = !menu.hidden;
        button.setAttribute("aria-expanded", String(!menu.hidden));
        if (!menu.hidden) getEl(this.root, "users-toggle-active").focus();
        break;
      }
      case "users-toggle-active": await this.changeAccount("active"); break;
      case "users-delete": await this.changeAccount("delete"); break;
      case "users-retry": if (this.discard()) await this.init(); break;
      case "users-add":
        if (!this.discard()) return;
        this.resetDraft(); renderDetail(this.root, this.state);
        getEl<HTMLFormElement>(this.root, "users-add-form").reset();
        getEl(this.root, "users-form-error").hidden = true;
        getEl<HTMLDialogElement>(this.root, "users-add-dialog").showModal(); break;
      case "users-cancel-add": getEl<HTMLDialogElement>(this.root, "users-add-dialog").close(); break;
    }
  }

  private async mutate(action: () => Promise<void>) {
    if (this.state.busy) return;
    this.state.busy = true; this.state.detailError = ""; this.closeMenu(); this.render();
    try { await action(); }
    catch (error) { this.state.detailError = message(error); }
    finally { if (!this.disposed) { this.state.busy = false; this.render(); } }
  }

  private updateUser(user: AdminUser) {
    this.state.users = this.state.users.map(u => u.user_id === user.user_id ? user : u);
    this.resetDraft();
  }
  private async save() {
    const user = selectedUser(this.state);
    if (!user || user.role === "admin" || !this.state.systemsReady || !dirty(this.state)) return;
    const codes = [...this.state.draft];
    await this.mutate(async () => {
      const updated = await request<AdminUser>(`/api/admin/users/${encodeURIComponent(user.user_id)}/systems`, jsonOptions("PUT", { allowed_system_codes: codes }));
      this.updateUser(updated); this.notify("시스템 접근 권한을 저장했습니다.");
    });
  }
  private async changeAccount(action: "active" | "delete") {
    const user = selectedUser(this.state);
    if (!user || !this.discard()) return;
    const question = action === "delete" ? `'${user.name}' 사용자를 삭제할까요? 이 작업은 되돌릴 수 없습니다.` : `'${user.name}' 사용자를 ${user.is_active ? "비활성화" : "활성화"}할까요?`;
    if (!window.confirm(question)) return;
    await this.mutate(async () => {
      const url = `/api/admin/users/${encodeURIComponent(user.user_id)}`;
      if (action === "delete") {
        await request(url, jsonOptions("DELETE"));
        this.state.users = this.state.users.filter(u => u.user_id !== user.user_id);
        this.state.selectedId = this.state.users[0]?.user_id ?? null; this.resetDraft();
        this.notify("사용자를 삭제했습니다.");
      } else {
        const updated = await request<AdminUser>(`${url}/active`, jsonOptions("PATCH", { is_active: !user.is_active }));
        this.updateUser(updated); this.notify("계정 상태를 변경했습니다.");
      }
    });
  }

  private async create() {
    if (this.state.busy) return;
    const form = getEl<HTMLFormElement>(this.root, "users-add-form");
    const fields = new FormData(form);
    const error = getEl(this.root, "users-form-error"); error.hidden = true;
    this.state.busy = true; this.render();
    const controls = [...form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLButtonElement>("input,select,button")];
    controls.forEach(control => { control.disabled = true; });
    try {
      const user = await request<AdminUser>("/api/admin/users", jsonOptions("POST", Object.fromEntries(fields)));
      this.state.users.push(user); this.state.selectedId = user.user_id;
      this.state.query = ""; this.state.filter = "all"; getEl<HTMLInputElement>(this.root, "users-search").value = "";
      this.resetDraft(); getEl<HTMLDialogElement>(this.root, "users-add-dialog").close(); form.reset();
      this.notify(user.role === "admin" ? "관리자 계정을 추가했습니다." : "사용자를 추가했습니다. 접근할 시스템을 설정하세요.");
    } catch (reason) { error.textContent = message(reason); error.hidden = false; }
    finally {
      if (!this.disposed) {
        this.state.busy = false; controls.forEach(control => { control.disabled = false; }); this.render();
        if (!getEl<HTMLDialogElement>(this.root, "users-add-dialog").open) getEl(this.root, "users-add").focus();
      }
    }
  }

  destroy() { this.disposed = true; this.events.abort(); clearTimeout(this.timer); }
}
