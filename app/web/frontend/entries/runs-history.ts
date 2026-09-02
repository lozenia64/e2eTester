/** Run 이력 화면 배선 — 로직은 runs-history/ 안에 있다. */
import "../runs-history/styles.css";
import { buildGrid, renderGrid, type CoverageResponse } from "../runs-history/coverage";
import { bindDrilldown } from "../runs-history/drilldown";

async function boot(): Promise<void> {
  const grid = document.getElementById("rhist-grid");
  const panel = document.getElementById("rhist-drill");
  if (!grid || !panel) {
    return;
  }

  const names = new Map<string, string>();
  bindDrilldown(grid, panel, (code) => names.get(code) ?? code);

  try {
    const response = await fetch("/api/runs/coverage");
    if (!response.ok) {
      grid.textContent = "점검 커버리지를 불러오지 못했습니다.";
      return;
    }
    const payload = (await response.json()) as CoverageResponse;
    for (const system of payload.systems) {
      names.set(system.system_code, system.system_name);
    }
    renderGrid(grid, buildGrid(payload), payload.window.day_keys);
  } catch {
    grid.textContent = "점검 커버리지를 불러오지 못했습니다.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void boot();
});
