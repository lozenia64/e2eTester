import { describe, expect, it } from "vitest";
import { passRateToDegrees } from "./index";

describe("passRateToDegrees", () => {
  it("0 통과는 0도", () => {
    expect(passRateToDegrees(0, 31)).toBe(0);
  });

  it("전부 통과는 360도", () => {
    expect(passRateToDegrees(31, 31)).toBe(360);
  });

  it("절반 통과는 180도", () => {
    expect(passRateToDegrees(5, 10)).toBe(180);
  });

  it("모듈이 0개면 0도 — 0 나눗셈이 NaN 을 만들지 않는다", () => {
    expect(passRateToDegrees(0, 0)).toBe(0);
  });

  it("통과 수가 총계를 넘어도 360도를 넘지 않는다", () => {
    expect(passRateToDegrees(40, 31)).toBe(360);
  });

  it("음수 입력은 0도로 잘린다", () => {
    expect(passRateToDegrees(-3, 31)).toBe(0);
  });
});
