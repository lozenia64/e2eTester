import { afterEach, describe, expect, it, vi } from "vitest";
import { bindDrilldown, renderDrilldown, renderDrilldownError, type DayRun } from "./drilldown";

const run = (overrides: Partial<DayRun> = {}): DayRun => ({
  run_id: "run_1",
  status: "passed",
  status_label: "정상",
  requested_at: "2026-09-01T13:00:00+09:00",
  module_total: 3,
  module_passed: 3,
  suite_id: null,
  ...overrides,
});

function grid(): HTMLElement {
  const root = document.createElement("div");
  const cell = document.createElement("button");
  cell.className = "rhist-cell";
  cell.dataset.day = "2026-09-01";
  cell.dataset.system = "hom";
  root.appendChild(cell);
  return root;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("renderDrilldown", () => {
  it("Run 한 건마다 한 줄과 상세 링크를 낸다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", [run(), run({ run_id: "run_2" })]);

    expect(panel.querySelectorAll(".rhist-drill__row").length).toBe(2);
    expect(panel.querySelector<HTMLAnchorElement>('a[href="/runs/run_1"]')).not.toBeNull();
  });

  it("빈 날은 미실행이라고 말한다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", []);

    expect(panel.querySelector(".rhist-drill__empty")?.textContent).toContain(
      "실행된 Run 이 없습니다",
    );
  });

  it("서버가 준 status_label 을 그대로 쓴다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", [
      run({ status_label: "이상징후", status: "anomaly" }),
    ]);

    expect(panel.textContent).toContain("이상징후");
  });

  it("다시 그려도 행이 쌓이지 않는다", () => {
    const panel = document.createElement("div");

    renderDrilldown(panel, "HOM", "2026-09-01", [run()]);
    renderDrilldown(panel, "HOM", "2026-09-01", [run()]);

    expect(panel.querySelectorAll(".rhist-drill__row").length).toBe(1);
  });
});

describe("bindDrilldown", () => {
  it("셀을 누르면 그 날/시스템으로 조회한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [run()] });
    vi.stubGlobal("fetch", fetchMock);
    const root = grid();
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    await vi.waitFor(() => expect(panel.querySelectorAll(".rhist-drill__row").length).toBe(1));

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("system_code=hom");
    expect(url).toContain("day=2026-09-01");
  });

  it("선택한 셀만 표시된다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    const root = grid();
    const second = document.createElement("button");
    second.className = "rhist-cell";
    second.dataset.day = "2026-09-02";
    second.dataset.system = "hom";
    root.appendChild(second);
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    second.click();
    await vi.waitFor(() => expect(root.querySelectorAll('[data-selected="true"]').length).toBe(1));

    expect(second.dataset.selected).toBe("true");
  });

  it("조회가 실패해도 격자는 살아 있다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    const root = grid();
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    await vi.waitFor(() => expect(panel.textContent).toContain("불러오지 못했습니다"));

    expect(root.querySelectorAll(".rhist-cell").length).toBe(1);
  });

  it("응답이 실패 상태여도 패널에만 표시한다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => [] }));
    const root = grid();
    const panel = document.createElement("div");

    bindDrilldown(root, panel, () => "HOM");
    root.querySelector<HTMLElement>(".rhist-cell")!.click();
    await vi.waitFor(() => expect(panel.textContent).toContain("불러오지 못했습니다"));
  });
});

describe("renderDrilldownError", () => {
  it("실패 문구를 낸다", () => {
    const panel = document.createElement("div");

    renderDrilldownError(panel);

    expect(panel.textContent).toContain("불러오지 못했습니다");
  });
});
