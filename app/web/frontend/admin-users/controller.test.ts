import { afterEach, beforeEach, expect, it, vi } from "vitest";
import template from "../../templates/admin/users.html?raw";
import { UsersController } from "./controller";
import type { AdminUser } from "./types";

const initial: AdminUser[] = [
  { user_id: "admin", name: "관리자", email: "admin@example.com", role: "admin", is_active: true, created_at: "2026-06-22T00:00:00Z", allowed_system_codes: [] },
  { user_id: "user", name: "이준용", email: "jun@example.com", role: "user", is_active: true, created_at: "2026-06-22T00:00:00Z", allowed_system_codes: ["hom"] },
];
const systems = [{ system_code: "hom", system_name: "대표홈페이지(PC)" }, { system_code: "mhm", system_name: "대표홈페이지(모바일)" }];
let users: AdminUser[];
let controller: UsersController;
let api: ReturnType<typeof vi.fn<(url: string, options?: RequestInit) => Promise<ReturnType<typeof response>>>>;
const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const click = (id: string) => el(id).click();
const input = (id: string, value: string) => { el<HTMLInputElement>(id).value = value; el(id).dispatchEvent(new Event("input", { bubbles: true })); };
const select = (id: string) => document.querySelector<HTMLButtonElement>(`[data-user-id="${id}"]`)!.click();
const response = (data: unknown, ok = true) => ({ ok, status: ok ? 200 : 500, json: async () => data });

beforeEach(() => {
  users = structuredClone(initial);
  document.body.innerHTML = template.replace(/{% macro[\s\S]*?{% endmacro %}/g, "").replace(/{%[\s\S]*?%}|{{[\s\S]*?}}/g, "");
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
  vi.spyOn(window, "confirm").mockReturnValue(true);
  api = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === "/api/admin/systems") return response(systems);
    if (!options?.method) return response(users);
    const body = options.body ? JSON.parse(String(options.body)) : {};
    if (options.method === "POST") {
      const created: AdminUser = { ...initial[1]!, ...body, user_id: "new", allowed_system_codes: [] };
      users.push(created);
      return response(created);
    }
    const id = url.split("/")[4];
    const user = users.find(u => u.user_id === id)!;
    if (options.method === "DELETE") { users = users.filter(u => u.user_id !== id); return response({ ok: true }); }
    Object.assign(user, body);
    return response(user);
  });
  vi.stubGlobal("fetch", api);
  controller = new UsersController(el("admin-users-root"));
});

afterEach(() => { controller.destroy(); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ""; });

it("이름·이메일 검색과 상태 필터가 목록과 건수를 동기화한다", async () => {
  users[0]!.is_active = false;
  await controller.init();
  input("users-search", "JUN@");
  expect(document.querySelectorAll("[data-user-id]")).toHaveLength(1);
  click("users-filter-inactive");
  expect(el("users-rows").textContent).toContain("조건에 맞는 사용자가 없습니다");
});

it("빈 권한은 접근 없음이며 전체 선택은 빈 배열 대신 등록된 코드를 저장한다", async () => {
  users[1]!.allowed_system_codes = [];
  await controller.init();
  expect(el("user-scope").textContent).toBe("접근 없음");
  click("users-mode-all"); click("users-save");
  await vi.waitFor(() => expect(api).toHaveBeenCalledWith("/api/admin/users/user/systems", expect.objectContaining({ body: JSON.stringify({ allowed_system_codes: ["hom", "mhm"] }) })));
});

it("선택 모드에서 마지막 시스템을 해제하면 접근 없음으로 저장한다", async () => {
  await controller.init();
  document.querySelector<HTMLInputElement>("#users-checks input")!.click();
  click("users-save");
  await vi.waitFor(() => expect(users[1]!.allowed_system_codes).toEqual([]));
});

it("관리자의 시스템 권한은 읽기 전용이며 기존 계정 작업은 유지한다", async () => {
  await controller.init(); select("admin");
  expect(el<HTMLButtonElement>("users-mode-selected").disabled).toBe(true);
  expect(el("user-scope").textContent).toBe("전체 시스템");
  expect(el<HTMLButtonElement>("users-toggle-active").disabled).toBe(false);
});

it("미저장 변경 전환을 취소하면 현재 사용자와 초안을 유지한다", async () => {
  await controller.init(); click("users-mode-all");
  vi.mocked(window.confirm).mockReturnValue(false); select("admin");
  expect(el("user-name").textContent).toBe("이준용");
  expect(el<HTMLButtonElement>("users-save").disabled).toBe(false);
});

it("저장 실패는 초안을 유지하고 저장 중 중복 요청과 사용자 전환을 막는다", async () => {
  await controller.init(); click("users-mode-all");
  let finish!: (value: ReturnType<typeof response>) => void;
  api.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  click("users-save"); click("users-save"); select("admin");
  expect(el("user-name").textContent).toBe("이준용");
  finish(response({ detail: "저장 실패" }, false));
  await vi.waitFor(() => expect(el("users-detail-error").textContent).toBe("저장 실패"));
  expect(el<HTMLButtonElement>("users-save").disabled).toBe(false);
});

it("시스템 조회 실패는 권한 편집만 잠그고 재시도할 수 있다", async () => {
  const normal = api.getMockImplementation()!;
  api.mockImplementation(async (url: string, options?: RequestInit) => url.endsWith("/systems") ? response({}, false) : normal(url, options));
  await controller.init();
  expect(el("user-name").textContent).toBe("이준용");
  expect(el<HTMLButtonElement>("users-mode-all").disabled).toBe(true);
  api.mockImplementation(normal); click("users-retry");
  await vi.waitFor(() => expect(el<HTMLButtonElement>("users-mode-all").disabled).toBe(false));
});

it("미등록 코드와 HTML 문자가 있는 사용자 정보를 안전하게 보존한다", async () => {
  users[1]!.name = '<img src=x onerror="alert(1)">'; users[1]!.allowed_system_codes = ["hom", "legacy"];
  await controller.init();
  expect(document.querySelector("#users-rows img")).toBeNull();
  expect(el("user-name").textContent).toBe(users[1]!.name);
  expect(el("users-checks").textContent).toContain("미등록 시스템");
  document.querySelector<HTMLInputElement>('#users-checks input[value="mhm"]')!.click(); click("users-save");
  await vi.waitFor(() => expect(users[1]!.allowed_system_codes).toContain("legacy"));
});

it("추가 성공 시 새 계정을 선택하고 접근 권한 설정으로 이어진다", async () => {
  await controller.init(); click("users-add");
  const form = el<HTMLFormElement>("users-add-form");
  for (const [name, value] of Object.entries({ name: "신규 사용자", email: "new@example.com", password: "password123", role: "user" })) (form.elements.namedItem(name) as HTMLInputElement).value = value;
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await vi.waitFor(() => expect(el("user-name").textContent).toBe("신규 사용자"));
  expect(el("user-scope").textContent).toBe("접근 없음");
  expect(el<HTMLDialogElement>("users-add-dialog").open).toBe(false);
});

it("상태 변경과 삭제는 대상 계정 API를 호출하고 목록을 갱신한다", async () => {
  await controller.init(); click("users-toggle-active");
  await vi.waitFor(() => expect(el("user-status").textContent).toBe("비활성"));
  click("users-delete");
  await vi.waitFor(() => expect(document.querySelectorAll("[data-user-id]")).toHaveLength(1));
  expect(api).toHaveBeenCalledWith("/api/admin/users/user", expect.objectContaining({ method: "DELETE" }));
});

it("빈 목록과 조회 실패를 구분한다", async () => {
  users = []; await controller.init();
  expect(el("users-rows").textContent).toContain("등록된 사용자가 없습니다");
  expect(el("users-detail").hidden).toBe(true);
});

it("명시적으로 해제한 미등록 권한은 전체 시스템 전환으로 다시 부여하지 않는다", async () => {
  users[1]!.allowed_system_codes = ["hom", "legacy"];
  await controller.init();
  document.querySelector<HTMLInputElement>('#users-checks input[value="legacy"]')!.click();
  click("users-mode-all"); click("users-save");
  await vi.waitFor(() => expect(users[1]!.allowed_system_codes).toEqual(["hom", "mhm"]));
});

it("추가 성공 후 추가 버튼으로 키보드 포커스를 복귀한다", async () => {
  await controller.init(); click("users-add");
  const form = el<HTMLFormElement>("users-add-form");
  for (const [name, value] of Object.entries({ name: "신규", email: "new@example.com", password: "password123" })) (form.elements.namedItem(name) as HTMLInputElement).value = value;
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await vi.waitFor(() => expect(el<HTMLDialogElement>("users-add-dialog").open).toBe(false));
  expect(document.activeElement).toBe(el("users-add"));
});

it("추가 실패는 모달과 입력을 유지하고 중복 제출을 막는다", async () => {
  await controller.init(); click("users-add");
  const form = el<HTMLFormElement>("users-add-form");
  (form.elements.namedItem("name") as HTMLInputElement).value = "유지할 이름";
  api.mockImplementationOnce(async () => response({ detail: "이미 사용 중인 이메일입니다." }, false));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await vi.waitFor(() => expect(el("users-form-error").hidden).toBe(false));
  expect(el<HTMLDialogElement>("users-add-dialog").open).toBe(true);
  expect((form.elements.namedItem("name") as HTMLInputElement).value).toBe("유지할 이름");
});

it("목록 조회 실패는 오류를 표시하고 재시도 후 복구한다", async () => {
  api.mockImplementationOnce(async () => response({}, false));
  await controller.init();
  expect(el("users-error").hidden).toBe(false);
  expect(el("users-rows").textContent).toContain("불러오지 못했습니다");
  click("users-retry");
  await vi.waitFor(() => expect(document.querySelectorAll("[data-user-id]")).toHaveLength(2));
  expect(el("users-error").hidden).toBe(true);
});

it("계정 삭제 확인을 취소하면 요청하지 않는다", async () => {
  await controller.init(); vi.mocked(window.confirm).mockReturnValue(false);
  click("users-delete");
  expect(api.mock.calls.some(([, options]) => options?.method === "DELETE")).toBe(false);
});
