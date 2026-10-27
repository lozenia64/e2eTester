import { expect, it } from "vitest";
import { trendOption } from "./charts";
it("동작 감소에서는 최초 그리기 모션을 생략하고 갱신은 짧게 전환한다", () => {
  const data = { daily: [{ date: "2026-10-01", saved_seconds: 45, cumulative_seconds: 45 }] };
  const colors = { accent: "blue", muted: "gray", grid: "silver" };
  const reduced = trendOption(data.daily, colors, true, true);
  expect(reduced.animation).toBe(false);
  expect(trendOption(data.daily, colors, true, false).animationDuration).toBe(1300);
  expect(trendOption(data.daily, colors, false, false).animationDurationUpdate).toBe(250);
});
