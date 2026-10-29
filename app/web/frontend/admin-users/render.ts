import type { AdminUser, UsersState } from "./types";

export const selectedUser = (state: UsersState) => state.users.find(u => u.user_id === state.selectedId);
export const escapeHtml = (value: string) => value.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
export const icon = (name: string) => `<svg aria-hidden="true" viewBox="0 0 24 24"><use href="#users-icon-${name}"></use></svg>`;
export function getEl<T extends HTMLElement = HTMLElement>(root: HTMLElement, id: string): T {
  return root.querySelector<T>(`#${id}`)!;
}
export function availableSystems(state: UsersState) {
  const systems = [...state.systems];
  const known = new Set(systems.map(s => s.system_code));
  for (const code of selectedUser(state)?.allowed_system_codes ?? []) {
    if (!known.has(code)) { systems.push({ system_code: code, system_name: "미등록 시스템" }); known.add(code); }
  }
  return systems;
}
export function dirty(state: UsersState) {
  const user = selectedUser(state);
  if (!user || user.role === "admin") return false;
  return [...new Set(user.allowed_system_codes)].sort().join("\0") !== [...new Set(state.draft)].sort().join("\0");
}

export function renderList(root: HTMLElement, state: UsersState) {
  const active = state.users.filter(u => u.is_active).length;
  const set = (id: string, text: string | number) => { getEl(root, id).textContent = String(text); };
  set("users-total", state.users.length); set("users-active-total", active);
  set("users-admin-total", state.users.filter(u => u.role === "admin").length);
  set("users-count-all", state.users.length); set("users-count-active", active);
  set("users-count-inactive", state.users.length - active);
  const visible = state.users.filter(u => (state.filter === "all" || u.is_active === (state.filter === "active")) && `${u.name} ${u.email}`.toLocaleLowerCase().includes(state.query.toLocaleLowerCase()));
  set("users-list-count", visible.length);
  set("users-result-count", `총 ${visible.length}명의 사용자`);
  for (const tab of root.querySelectorAll<HTMLButtonElement>("[data-users-filter]")) {
    const active = tab.dataset.usersFilter === state.filter;
    tab.classList.toggle("is-active", active); tab.setAttribute("aria-pressed", String(active));
  }
  const rows = getEl(root, "users-rows");
  rows.setAttribute("aria-busy", String(state.loading));
  rows.innerHTML = visible.map(u => `<button type="button" class="usr-row ${u.user_id === state.selectedId ? "is-selected" : ""}" data-user-id="${escapeHtml(u.user_id)}" aria-pressed="${u.user_id === state.selectedId}" ${state.busy ? "disabled" : ""}>
    <span class="usr-person"><span class="usr-avatar ${u.role === "admin" ? "is-admin" : ""}">${escapeHtml(Array.from(u.name)[0] || "?")}</span><span class="usr-person-info"><strong>${escapeHtml(u.name)}</strong><small>${escapeHtml(u.email)}</small></span></span>
    <span class="usr-role">${u.role === "admin" ? "관리자" : "일반 사용자"}</span><span class="usr-status ${u.is_active ? "" : "is-off"}">${u.is_active ? "활성" : "비활성"}</span>
  </button>`).join("");
  if (!visible.length) {
    rows.innerHTML = `<div class="usr-empty">${state.loading ? "사용자를 불러오고 있습니다…" : state.error && !state.users.length ? "사용자 목록을 불러오지 못했습니다." : !state.users.length ? "등록된 사용자가 없습니다. 새 사용자를 추가하세요." : "조건에 맞는 사용자가 없습니다."}</div>`;
  }
  getEl(root, "users-error").hidden = !state.error;
  set("users-error-message", state.error);
  getEl<HTMLButtonElement>(root, "users-retry").disabled = state.loading || state.busy;
  getEl<HTMLInputElement>(root, "users-search").disabled = state.loading;
  getEl<HTMLButtonElement>(root, "users-add").disabled = state.loading || state.busy;
}

function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" });
}

export function loadIdentity(root: HTMLElement, user: AdminUser) {
  const set = (id: string, value: string) => { getEl(root, id).textContent = value; };
  set("user-name", user.name); set("user-email", user.email);
  set("user-avatar", Array.from(user.name)[0] || "?");
  getEl(root, "user-avatar").classList.toggle("is-admin", user.role === "admin");
  set("user-role", user.role === "admin" ? "관리자" : "일반 사용자");
  set("user-status", user.is_active ? "활성" : "비활성");
  getEl(root, "user-status").classList.toggle("is-off", !user.is_active);
  set("user-created", dateLabel(user.created_at));
  set("users-toggle-active", user.is_active ? "비활성화" : "활성화");
  getEl<HTMLButtonElement>(root, "users-more").setAttribute("aria-label", `${user.name} 사용자 작업 더보기`);
}

export function renderDetail(root: HTMLElement, state: UsersState) {
  const user = selectedUser(state);
  getEl(root, "users-detail").hidden = !user;
  if (!user) return;
  loadIdentity(root, user);
  const admin = user.role === "admin";
  const locked = admin || state.busy || !state.systemsReady;
  const systems = availableSystems(state);
  const set = (id: string, value: string) => { getEl(root, id).textContent = value; };
  set("user-scope", admin || state.all ? "전체 시스템" : state.draft.length ? "선택한 시스템" : "접근 없음");
  set("users-permission-count", admin || state.all ? "전체 접근" : `${state.draft.length}개 선택됨`);
  set("users-permission-help", !state.systemsReady ? "시스템 목록을 다시 불러온 후 권한을 변경할 수 있습니다." : admin ? "관리자는 항상 모든 시스템에 접근할 수 있습니다." : state.all ? "현재 등록된 시스템을 모두 허용합니다. 새 시스템은 별도 설정이 필요합니다." : "선택한 시스템만 접근할 수 있습니다. 0개 선택 시 접근할 수 없습니다.");
  for (const [id, active] of [["users-mode-all", admin || state.all], ["users-mode-selected", !admin && !state.all]] as const) {
    const button = getEl<HTMLButtonElement>(root, id);
    button.disabled = locked; button.classList.toggle("is-active", active); button.setAttribute("aria-pressed", String(active));
  }
  getEl(root, "users-checks").innerHTML = systems.map(s => `<label class="usr-permission"><input type="checkbox" value="${escapeHtml(s.system_code)}" ${admin || state.draft.includes(s.system_code) ? "checked" : ""} ${locked || state.all ? "disabled" : ""}><span class="usr-system-icon">${icon("system")}</span><span class="usr-system-name">${escapeHtml(s.system_name)}</span><span class="usr-system-code">${escapeHtml(s.system_code)}</span></label>`).join("") || '<p class="usr-help">등록된 시스템이 없습니다.</p>';
  getEl<HTMLButtonElement>(root, "users-save").disabled = locked || !dirty(state);
  set("users-save-state", state.busy ? "변경사항을 처리하고 있습니다…" : dirty(state) ? "저장하지 않은 변경사항" : "저장된 권한입니다");
  getEl(root, "users-detail-error").hidden = !state.detailError;
  set("users-detail-error", state.detailError);
  for (const id of ["users-more", "users-toggle-active", "users-delete"]) getEl<HTMLButtonElement>(root, id).disabled = state.busy;
}
