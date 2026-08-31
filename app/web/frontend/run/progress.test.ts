import { describe, expect, it } from "vitest";
import { formatClock, summarizeModules } from "./progress";

describe("formatClock", () => {
  it("분:초로 찍는다", () => {
    expect(formatClock(65_000)).toBe("01:05");
  });

  it("0 도 형식을 지킨다", () => {
    expect(formatClock(0)).toBe("00:00");
  });

  it("한 시간을 넘으면 분이 60을 넘어간다", () => {
    expect(formatClock(3_725_000)).toBe("62:05");
  });

  it("음수는 00:00 으로 눕힌다", () => {
    expect(formatClock(-5_000)).toBe("00:00");
  });
});

describe("summarizeModules", () => {
  const mods = (...s: string[]) => s.map((status) => ({ status }));

  it("통과·실패를 센다", () => {
    const r = summarizeModules(mods("passed", "passed", "error", "pending"));
    expect(r.passed).toBe(2);
    expect(r.failed).toBe(1);
    expect(r.total).toBe(4);
  });

  it("anomaly 도 실패로 센다", () => {
    expect(summarizeModules(mods("anomaly")).failed).toBe(1);
  });

  it("skipped 는 분모에서 뺀다", () => {
    const r = summarizeModules(mods("passed", "skipped"));
    expect(r.total).toBe(1);
  });

  it("모듈이 없으면 percent 가 0 이고 나눗셈이 터지지 않는다", () => {
    expect(summarizeModules([]).percent).toBe(0);
  });
});
