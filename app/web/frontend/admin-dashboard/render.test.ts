import { expect, it, vi, afterEach } from "vitest";
import { renderPerformance, renderDaily, renderCoverage } from "./render";
import type { PerformanceData } from "./types";

afterEach(() => vi.unstubAllGlobals());
export const performanceData: PerformanceData = {
  generated_at: "2026-10-27T01:00:00Z", timezone: "Asia/Seoul",
  period: { from: "2026-10-01T00:00:00+09:00", to: "2026-10-27T10:00:00+09:00", previous_from: "2026-09-01T00:00:00+09:00", previous_to: "2026-09-27T10:00:00+09:00" },
  total_seconds: 0, previous_seconds: 0, change_percent: null, total_runs: 0,
  basis_note: "현재 기준 시간으로 재계산합니다.",
  daily: [{ date: "2026-10-01", saved_seconds: 0, cumulative_seconds: 0 }],
  by_system: [{ system_code: "hom", system_name: '<img src=x onerror="bad()">', runs: 0, saved_seconds: 0 }],
};
function root(): HTMLElement {
  document.body.innerHTML = `<main><span id="perf-saved"></span><span id="perf-month"></span><span id="perf-comparison"></span><span id="perf-basis-note"></span><span id="perf-runs"></span><span id="perf-period"></span><span id="perf-saving-note"></span><div id="perf-contribution"></div><div id="perf-trend-table"></div><div id="perf-observation"></div><div id="adm-heatmap"></div><div id="adm-daily-compact"></div><span id="perf-today-rate"></span><span id="perf-today-basis"></span><span id="perf-systems"></span><span id="perf-attention"></span><div id="perf-attention-links"></div></main>`;
  return document.querySelector("main")!;
}
it("0 실적과 비교 불가를 구분하고 시스템명을 HTML로 해석하지 않는다", () => {
  const el = root();
  renderPerformance(el, performanceData, false);
  expect(el.querySelector("#perf-saved")!.textContent).toBe("0.0");
  expect(el.querySelector("#perf-comparison")!.textContent).toContain("비교할 전월 실적 없음");
  expect(el.querySelector("#perf-saving-note")!.textContent).toContain("산정 가능한 절감 시간 없음");
  expect(el.querySelector("img")).toBeNull();
  expect(el.textContent).toContain("<img");
});
it("미점검을 통과로 표시하지 않고 일간 API의 분모를 사용한다", () => {
  const el = root();
  renderDaily(el, { generated_at: "", date_label: "2026-10-27", totals: { modules: 10, passed: 0, pass_rate: 0, systems: 1, anomaly: 0, error: 0, inspected: 0 }, systems: [] });
  expect(el.querySelector("#perf-today-rate")!.textContent).toBe("미점검");
  expect(el.querySelector("#perf-today-basis")!.textContent).toContain("0 / 10");
});
it("커버리지 갱신에서 같은 실행 링크의 포커스를 보존한다", () => {
  const el = root();
  const data = { generated_at: "", columns: [{ day_key: "2026-10-27", slot_id: "day", label: "화 주간" }], systems: [{ system_code: "hom", system_name: "홈", latest_tone: "passed", cells: [{ day_key: "2026-10-27", slot_id: "day", status_label: "정상", tone: "passed", run_id: "abc", checked_at: null }] }] };
  renderCoverage(el, data);
  const link = el.querySelector<HTMLAnchorElement>("a")!;
  link.focus();
  data.systems[0]!.cells[0]!.status_label = "갱신된 결과";
  renderCoverage(el, data);
  expect(document.activeElement?.getAttribute("href")).toBe("/runs/abc");
  expect(document.activeElement?.getAttribute("aria-label")).toContain("갱신된 결과");
});
it("기여도 갱신 때 막대 노드를 보존해 기존 너비에서 전환한다", () => {
  const el = root();
  renderPerformance(el, performanceData, false);
  const bar = el.querySelector(".perf-bar-fill");
  renderPerformance(el, { ...performanceData, total_seconds: 75, by_system: [{ ...performanceData.by_system[0]!, saved_seconds: 75 }] }, false);
  expect(el.querySelector(".perf-bar-fill")).toBe(bar);
  expect((bar as HTMLElement).style.getPropertyValue("--bar-width")).toBe("100%");
});
it("시스템이 없음에서 등록됐다가 다시 없어지면 이전 막대를 지운다", () => {
  const el = root();
  renderPerformance(el, { ...performanceData, by_system: [] }, false);
  renderPerformance(el, performanceData, false);
  expect(el.querySelectorAll(".perf-bar-row")).toHaveLength(1);
  renderPerformance(el, { ...performanceData, by_system: [] }, false);
  expect(el.querySelectorAll(".perf-bar-row")).toHaveLength(0);
});
