import { afterEach, beforeEach, expect, it, vi } from "vitest";
import template from "../../templates/admin/modules.html?raw";
import { ModulesController } from "./controller";

const fixture = () => [
  { system_code: "hom", system_name: "대표홈페이지(PC)", modules: Array.from({ length: 23 }, (_, i) => ({ module_id: `hom.module${i + 1}`, name: `업무 ${i + 1}`, estimated_manual_seconds: 60, manifest_default: 60, is_overridden: i === 1 })) },
  { system_code: "mhm", system_name: "대표홈페이지(모바일)", modules: [{ module_id: "mhm.login", name: "로그인", estimated_manual_seconds: 90, manifest_default: 60, is_overridden: true }] },
];
const response = (data: unknown, ok = true) => ({ ok, status: ok ? 200 : 503, json: async () => data });
let api: ReturnType<typeof vi.fn<(url: string, options?: RequestInit) => Promise<ReturnType<typeof response>>>>;
let controller: ModulesController;
const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const click = (id: string) => el(id).click();
const input = (id: string, value: string) => { el<HTMLInputElement>(id).value = value; el(id).dispatchEvent(new Event("input", { bubbles: true })); };
const edit = (id: string, value: string) => {
  const node = document.querySelector<HTMLInputElement>(`[data-module-id="${id}"]`)!;
  node.value = value; node.dispatchEvent(new Event("input", { bubbles: true }));
};
const choose = (code: string) => document.querySelector<HTMLButtonElement>(`[data-system-code="${code}"]`)!.click();
const body = () => JSON.parse(String(api.mock.calls.find(([, options]) => options?.method === "PUT")![1]!.body));

beforeEach(() => {
  document.body.innerHTML = template.replace(/{% macro[\s\S]*?{% endmacro %}/g, "").replace(/{%[\s\S]*?%}|{{[\s\S]*?}}/g, "");
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
  api = vi.fn(async (_url: string, options?: RequestInit) => options?.method === "PUT"
    ? response({ ok: true, saved: JSON.parse(String(options.body)).modules }) : response(fixture()));
  vi.stubGlobal("fetch", api);
  controller = new ModulesController(el("admin-modules-root"));
});
afterEach(() => { controller.destroy(); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ""; });

it("시스템·모듈 검색과 페이지 크기가 표시 건수를 제한한다", async () => {
  await controller.init();
  expect(document.querySelectorAll("[data-module-id]")).toHaveLength(10);
  input("modules-system-search", "MHM");
  expect(document.querySelectorAll("[data-system-code]")).toHaveLength(1);
  input("modules-search", "hom.module23");
  expect(document.querySelectorAll("[data-module-id]")).toHaveLength(1);
  input("modules-search", "");
  el<HTMLSelectElement>("modules-page-size").value = "15"; el("modules-page-size").dispatchEvent(new Event("change", { bubbles: true }));
  expect(document.querySelectorAll("[data-module-id]")).toHaveLength(15);
});

it("다른 페이지와 검색으로 숨겨진 초안까지 현재 시스템 저장에 포함한다", async () => {
  await controller.init(); edit("hom.module1", "75"); click("modules-next"); edit("hom.module11", "125");
  input("modules-search", "hom.module23"); click("modules-save");
  await vi.waitFor(() => expect(body().modules).toEqual([{ module_id: "hom.module1", estimated_manual_seconds: 75 }, { module_id: "hom.module11", estimated_manual_seconds: 125 }]));
});

it("기본값과 같은 override도 별도 설정 필터에 표시한다", async () => {
  await controller.init(); click("modules-filter-custom");
  expect(document.querySelectorAll("[data-module-id]")).toHaveLength(1);
  expect(document.querySelector<HTMLInputElement>("[data-module-id]")!.dataset.moduleId).toBe("hom.module2");
});

it("변경 취소는 모든 페이지 초안을 마지막 저장값으로 되돌린다", async () => {
  await controller.init(); edit("hom.module1", "80"); click("modules-next"); edit("hom.module11", "120"); click("modules-reset");
  expect(el<HTMLButtonElement>("modules-save").disabled).toBe(true);
  click("modules-prev"); expect(document.querySelector<HTMLInputElement>("[data-module-id]")!.value).toBe("60");
});

it("시스템 전환 확인을 취소하면 초안을 유지하고 승인하면 폐기한다", async () => {
  await controller.init(); edit("hom.module1", "75"); choose("mhm");
  expect(el<HTMLDialogElement>("modules-discard-dialog").open).toBe(true);
  click("modules-keep"); expect(el("modules-title").textContent).toBe("대표홈페이지(PC)");
  expect(el<HTMLButtonElement>("modules-save").disabled).toBe(false);
  choose("mhm"); click("modules-discard"); choose("hom");
  expect(document.querySelector<HTMLInputElement>("[data-module-id]")!.value).toBe("60");
});

it.each(["", "-1", "1.5", "9007199254740992"])("잘못된 시간 %s는 저장하지 않는다", async value => {
  await controller.init(); edit("hom.module1", value);
  expect(el<HTMLButtonElement>("modules-save").disabled).toBe(true);
  expect(document.querySelector<HTMLInputElement>("[data-module-id]")!.getAttribute("aria-invalid")).toBe("true");
});

it("0초도 정상적으로 저장한다", async () => {
  await controller.init(); edit("hom.module1", "0"); click("modules-save");
  await vi.waitFor(() => expect(body().modules[0].estimated_manual_seconds).toBe(0));
});

it("부분 저장은 성공 항목만 기준값을 갱신하고 실패 항목만 재시도한다", async () => {
  await controller.init(); edit("hom.module1", "75"); edit("hom.module2", "85");
  api.mockImplementationOnce(async () => response({ ok: false, saved: [{ module_id: "hom.module1", estimated_manual_seconds: 75 }], failed: [{ module_id: "hom.module2", detail: "실패" }] }));
  click("modules-save");
  await vi.waitFor(() => expect(el("modules-feedback").textContent).toContain("일부"));
  expect(el("modules-dirty-count").textContent).toBe("1");
  api.mockClear(); click("modules-save");
  await vi.waitFor(() => expect(body().modules).toEqual([{ module_id: "hom.module2", estimated_manual_seconds: 85 }]));
});

it("저장 중 중복 제출·다른 시스템 전환을 막고 실패 시 초안을 유지한다", async () => {
  await controller.init(); edit("hom.module1", "75");
  let finish!: (value: ReturnType<typeof response>) => void;
  api.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  click("modules-save"); click("modules-save"); choose("mhm");
  expect(api.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(1);
  expect(el("modules-title").textContent).toBe("대표홈페이지(PC)");
  finish(response({ detail: "설정 저장소 오류" }, false));
  await vi.waitFor(() => expect(el("modules-feedback").textContent).toBe("설정 저장소 오류"));
  expect(document.querySelector<HTMLInputElement>("[data-module-id]")!.value).toBe("75");
  expect(el<HTMLButtonElement>("modules-save").disabled).toBe(false);
});

it("네트워크 조회 실패는 빈 데이터와 구분하고 재시도로 복구한다", async () => {
  api.mockRejectedValueOnce(new Error("연결 실패")); await controller.init();
  expect(el("modules-load-error").hidden).toBe(false); click("modules-retry");
  await vi.waitFor(() => expect(document.querySelectorAll("[data-module-id]")).toHaveLength(10));
  expect(el("modules-load-error").hidden).toBe(true);
});

it("빈 시스템·모듈 목록과 HTML 문자를 안전하게 표시한다", async () => {
  const data = fixture(); data[0]!.system_name = "<img src=x onerror=alert(1)>"; data[0]!.modules[0]!.name = "<svg onload=alert(1)>";
  api.mockResolvedValueOnce(response(data)); await controller.init();
  expect(el("modules-title").textContent).toBe(data[0]!.system_name);
  expect(document.querySelector("#modules-rows svg[onload]")).toBeNull();
  api.mockResolvedValueOnce(response([])); await controller.init();
  expect(el("modules-editor").hidden).toBe(true);
  expect(el("modules-systems").textContent).toContain("등록된 시스템이 없습니다");
});

it("입력 중 같은 DOM과 포커스·표 스크롤을 유지한다", async () => {
  await controller.init(); const node = document.querySelector<HTMLInputElement>("[data-module-id]")!;
  node.focus(); el("modules-table-scroll").scrollTop = 80; edit("hom.module1", "75");
  expect(document.activeElement).toBe(node); expect(el("modules-table-scroll").scrollTop).toBe(80);
});

it("페이지 번호로 이동한 뒤 새 페이지 번호 버튼에 포커스를 유지한다", async () => {
  await controller.init();
  const button = document.querySelector<HTMLButtonElement>('[data-module-page="2"]')!;
  button.focus(); button.click();
  expect((document.activeElement as HTMLElement).dataset.modulePage).toBe("2");
  expect(el("modules-range").textContent).toContain("11–20");
});
