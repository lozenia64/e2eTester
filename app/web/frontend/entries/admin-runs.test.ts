import { afterEach, expect, it, vi } from "vitest";
import script from "../../static/admin-runs.js?raw";
import template from "../../templates/admin/runs.html?raw";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
  localStorage.clear();
});

async function setup({ delayInitial = false } = {}) {
  const statuses = ["PASSED", "ANOMALY", "ERROR", "CANCELLED"];
  let loop = 0;
  document.body.innerHTML = template
    .replace(/{% for option in status_options\("admin_runs"\) %}[\s\S]*?{% endfor %}/g, () => {
      loop += 1;
      return statuses.map((value) => loop === 1
        ? `<input type="checkbox" class="adm-filter-option" data-group="status" value="${value}">`
        : `<option value="${value}">${value}</option>`).join("");
    })
    .replace(/{%[\s\S]*?%}|{{[\s\S]*?}}/g, "");
  window.history.replaceState(null, "", "/admin/runs");
  vi.spyOn(window, "setInterval").mockReturnValue(1);
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  document.getElementById("runs-explore")!.scrollIntoView = vi.fn();
  const handlers: Record<string, (event: { data: { systemCode: string } }) => void> = {};
  vi.stubGlobal("echarts", { init: () => ({
    on: (name: string, handler: typeof handlers[string]) => { handlers[name] = handler; },
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  }) });
  const queries: URLSearchParams[] = [];
  let finishInitial: (() => void) | undefined;
  const initialResponse = new Promise<void>((resolve) => { finishInitial = resolve; });
  vi.stubGlobal("fetch", async (url: string) => {
    let payload: unknown = [];
    if (url === "/api/admin/systems") payload = [{ system_code: "hom", system_name: "홈" }];
    if (url === "/api/admin/runs/board") payload = {
      today_start: "2026-10-27T15:00:00Z",
      system_map: {
        period: { from: "2026-09-30T15:00:00Z", to: "2026-10-28T00:00:45Z" },
        systems: [{ system_code: "hom", system_name: "홈", runs: 3, anomaly: 2 }],
        top_runs: "hom", top_anomaly: "hom",
      },
    };
    if (url === "/api/admin/runs/heatmap") payload = { users: [], systems: [], matrix: [] };
    if (url.startsWith("/api/admin/runs?")) {
      queries.push(new URL(url, window.location.origin).searchParams);
      if (delayInitial && queries.length === 1) await initialResponse;
      payload = { items: [], total: 0 };
    }
    return { ok: true, json: async () => payload };
  });
  new Function(script)();
  await vi.waitFor(() => expect(queries).toHaveLength(1));
  return { handlers, queries, finishInitial: finishInitial! };
}

it("시스템 타일 클릭은 레거시 이상징후까지 목록에 포함한다", async () => {
  const { handlers, queries } = await setup();
  // 초기 목록 응답의 finally까지 기다린 뒤 타일을 클릭한다.
  await Promise.resolve();
  handlers.click!({ data: { systemCode: "hom" } });
  await vi.waitFor(() => expect(queries).toHaveLength(2));
  const query = queries[1]!;
  expect(query.getAll("status").sort()).toEqual(["ANOMALY", "FAILED", "PASSED"]);
  expect(query.getAll("system_code")).toEqual(["hom"]);
  expect(new Date(query.get("from")!).toISOString()).toBe("2026-09-30T15:00:00.000Z");
  // 상태 필터는 URL 복원에도 유지된다.
  await vi.waitFor(() => {
    expect(new URL(window.location.href).searchParams.getAll("status")).toEqual(["PASSED", "ANOMALY"]);
  });
});

it("목록 조회 중 타일을 클릭해도 최신 필터 조회를 누락하지 않는다", async () => {
  const { handlers, queries, finishInitial } = await setup({ delayInitial: true });
  handlers.click!({ data: { systemCode: "hom" } });
  finishInitial();
  await vi.waitFor(() => expect(queries).toHaveLength(2));
  expect(queries[1]!.getAll("system_code")).toEqual(["hom"]);
  expect(queries[1]!.getAll("status").sort()).toEqual(["ANOMALY", "FAILED", "PASSED"]);
});
