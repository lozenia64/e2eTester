import { describe, expect, it } from "vitest";
import { formatRunTime } from "./format";

describe("formatRunTime", () => {
  it("빈 값은 빈 문자열", () => {
    expect(formatRunTime(null)).toBe("");
    expect(formatRunTime(undefined)).toBe("");
    expect(formatRunTime("")).toBe("");
  });

  it("깨진 값도 던지지 않는다", () => {
    expect(formatRunTime("not-a-date")).toBe("");
  });

  it("시:분 을 24시간으로 낸다", () => {
    expect(formatRunTime("2026-09-01T13:05:00+09:00")).toMatch(/^\d{2}:\d{2}$/);
  });
});
