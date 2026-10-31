import type { EChartsCoreOption } from "echarts/core";
import { reducedMotion, setText } from "./dom";
import type { PerformanceData } from "./types";

export function trendOption(daily: PerformanceData["daily"], colors: { accent: string; muted: string; grid: string }, first: boolean, reduced: boolean): EChartsCoreOption {
  return {
    animation: !reduced, animationDuration: first ? 1300 : 0, animationDurationUpdate: 250, animationEasing: "cubicOut",
    grid: { left: 16, right: 24, top: 25, bottom: 18, containLabel: true },
    textStyle: { fontFamily: "Pretendard Variable, Pretendard, sans-serif" },
    tooltip: { trigger: "axis", renderMode: "richText", valueFormatter: (value: unknown) => `${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}시간` },
    xAxis: { type: "category", boundaryGap: false, data: daily.map(d => d.date.slice(5).replace("-", ".")), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: colors.muted, fontSize: 11, hideOverlap: true } },
    yAxis: { type: "value", min: 0, minInterval: .1, axisLabel: { color: colors.muted, fontSize: 10, formatter: "{value}h" }, splitLine: { lineStyle: { color: colors.grid, type: "dashed" } } },
    series: [{ type: "line", data: daily.map(d => d.cumulative_seconds / 3600), smooth: false, showSymbol: daily.length === 1, symbolSize: 7,
      lineStyle: { width: 3, color: colors.accent }, itemStyle: { color: colors.accent },
      areaStyle: { color: colors.accent, opacity: .07 }, emphasis: { focus: "series" } }],
  };
}

export function createTrend(root: HTMLElement): { update: (data: PerformanceData, first: boolean) => Promise<void>; destroy: () => void } {
  const host = root.querySelector<HTMLElement>("#perf-trend");
  let chart: import("echarts/core").EChartsType | undefined;
  let latest: PerformanceData | undefined;
  let signature = "";
  let loading: Promise<void> | undefined;
  let disposed = false;
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => chart?.resize()) : undefined;
  if (host) observer?.observe(host);
  const media = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : undefined;
  const options = (data: PerformanceData, first: boolean): EChartsCoreOption => {
    const css = getComputedStyle(root);
    return trendOption(data.daily, { accent: css.getPropertyValue("--perf-accent").trim(), muted: css.getPropertyValue("--perf-muted").trim(), grid: css.getPropertyValue("--perf-border").trim() }, first, reducedMotion());
  };
  const motionChange = (): void => { if (chart && latest) chart.setOption(options(latest, false)); };
  media?.addEventListener("change", motionChange);
  return {
    async update(data, first) {
      latest = data;
      if (!host || disposed) return;
      const next = JSON.stringify(data.daily);
      if (signature === next && chart) return;
      try {
        if (!loading) {
          loading = (async () => {
            const { init } = await import("./echarts-setup");
            if (!disposed) chart = init(host);
          })();
        }
        await loading;
        if (disposed || !latest) return;
        chart?.setOption(options(latest, first));
        signature = JSON.stringify(latest.daily);
        setText(root, "#perf-chart-note", latest.total_seconds ? "월초부터 오늘까지의 누적 추정 절감 시간" : "아직 산정된 절감 시간이 없습니다. 아래 표에서 일별 집계를 확인하세요.");
      } catch {
        loading = undefined;
        setText(root, "#perf-chart-note", "그래프를 불러오지 못했습니다. 일별 데이터 표에서 결과를 확인하세요.");
      }
    },
    destroy() { disposed = true; observer?.disconnect(); media?.removeEventListener("change", motionChange); chart?.dispose(); },
  };
}
