import { afterEach, expect, it, vi } from "vitest";
import source from "../../static/schedules.js?raw";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

async function openEditor(kind = "suite") {
  document.body.innerHTML = '<main class="schedc"></main>';
  for (const id of new Set(source.match(/schedc-[a-z-]+/g))) {
    const node = document.createElement("div");
    node.id = id;
    document.querySelector("main")!.appendChild(node);
  }
  document.querySelector("#schedc-systems-data")!.textContent = JSON.stringify({
    fp: { system_code: "fp", name: "영업가족", modules: [], run_form: [{ key: "manager_employee_id", label: "관리자사번" }] },
  });
  const detail = {
    schedule_id: "s1", schedule_kind: kind, name: "아침 점검", system_code: kind === "suite" ? "suite" : "fp",
    preset_id: kind === "suite" ? undefined : null, system_name: "전체 점검", cron: "0 7 * * *", enabled: true, browser_mode: "headless",
    selected_system_codes: ["fp"], preset_ids: { fp: "p1" },
    preset_bindings: { fp: { preset_id: "p1", name: "기존 프리셋", status: "live" } },
    preset_options: [
      { preset_id: "p1", system_code: "fp", name: "기존 프리셋" },
      { preset_id: "p2", system_code: "fp", name: "새 프리셋" },
    ],
  };
  const writes: Record<string, unknown>[] = [];
  const toasts = vi.fn();
  vi.stubGlobal("showToast", toasts);
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === "PUT") writes.push(JSON.parse(String(options.body)));
    const data = path.endsWith("/board") ? { schedules: [detail] }
      : path.endsWith("/history") ? { stats: {} } : detail;
    return { ok: true, json: async () => data };
  }));
  vi.spyOn(globalThis, "setInterval").mockReturnValue(0 as never);
  window.eval(source);
  await vi.waitFor(() => expect(document.querySelector('[data-schedule-id="s1"]')).toBeTruthy());
  document.querySelector<HTMLElement>('[data-schedule-id="s1"]')!.click();
  await vi.waitFor(() => expect(document.querySelector('[data-preset-code="fp"]')).toBeTruthy());
  document.querySelector<HTMLDetailsElement>("details")!.open = true;
  return { writes, toasts };
}

it("예약 편집에서 프리셋을 교체하고 ID를 저장한다", async () => {
  const { writes, toasts } = await openEditor();
  expect(document.querySelector("#schedc-drawer-body")!.textContent).toContain("최신값 사용");
  document.querySelector<HTMLSelectElement>('[data-preset-code="fp"]')!.value = "p2";
  document.querySelector<HTMLButtonElement>('[data-role="edit-save"]')!.click();
  expect(toasts.mock.calls).toEqual([]);
  await vi.waitFor(() => expect(writes).toEqual([{ preset_ids: { fp: "p2" } }]));
});

it("인증값 수정과 프리셋 연결을 함께 입력하면 저장 안내 후 차단한다", async () => {
  const { writes, toasts } = await openEditor("system");
  document.querySelector<HTMLInputElement>('[data-auth-key="manager_employee_id"]')!.value = "7654321";
  document.querySelector<HTMLSelectElement>('[data-preset-code="fp"]')!.value = "p1";
  document.querySelector<HTMLButtonElement>('[data-role="edit-save"]')!.click();
  expect(writes).toEqual([]);
  expect(toasts.mock.calls[0]?.[0]).toMatch(/프리셋.*저장/);
});
