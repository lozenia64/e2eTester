import "../admin-dashboard/styles.css";
import { createTrend } from "../admin-dashboard/charts";
import { DashboardController } from "../admin-dashboard/controller";
import { reducedMotion } from "../admin-dashboard/dom";
import { renderCoverage, renderDaily, renderPerformance } from "../admin-dashboard/render";
import type { CoverageData, DailyData, PerformanceData } from "../admin-dashboard/types";

const root = document.getElementById("admin-dashboard-root");
if (root) {
  const trend = createTrend(root);
  const controller = new DashboardController(root, (section, data, first) => {
    if (section === "performance") {
      const payload = data as PerformanceData;
      renderPerformance(root, payload, first);
      void trend.update(payload, first);
      if (first && !reducedMotion()) root.classList.add("perf-ready");
    } else if (section === "daily") renderDaily(root, data as DailyData);
    else renderCoverage(root, data as CoverageData);
  });
  void controller.refresh();
  window.addEventListener("pagehide", (event) => {
    if (!event.persisted) { controller.destroy(); trend.destroy(); }
  });
}
