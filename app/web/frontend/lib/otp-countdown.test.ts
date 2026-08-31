import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { moduleStartedAtFromRun, startOtpCountdown, stopOtpCountdown } from "./otp-countdown";

describe("startOtpCountdown", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    stopOtpCountdown();
    vi.useRealTimers();
  });

  it("대상 요소에 남은 시간을 쓴다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", el);
    expect(el.textContent).not.toBe("");
  });

  it("native hidden만 쓰는 카운트다운을 열고 stop에서 다시 감춘다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    el.hidden = true;
    el.classList.add("is-hidden");

    startOtpCountdown("2026-08-29T09:00:00Z", el);
    expect(el.hidden).toBe(false);
    expect(el.classList.contains("is-hidden")).toBe(false);

    stopOtpCountdown();
    expect(el.hidden).toBe(true);
    expect(el.classList.contains("is-hidden")).toBe(false);
  });

  it("1초마다 갱신한다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", el);
    const first = el.textContent;
    vi.advanceTimersByTime(2000);
    expect(el.textContent).not.toBe(first);
  });

  it("두 번 시작해도 타이머가 하나만 남는다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const a = document.createElement("p");
    const b = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", a);
    const frozen = a.textContent;
    startOtpCountdown("2026-08-29T09:00:00Z", b);
    vi.advanceTimersByTime(3000);
    expect(a.textContent).toBe(frozen);
    expect(b.textContent).not.toBe(frozen);
  });

  it("stop 후에는 갱신이 멈춘다", () => {
    vi.setSystemTime(new Date("2026-08-29T09:00:10Z"));
    const el = document.createElement("p");
    startOtpCountdown("2026-08-29T09:00:00Z", el);
    stopOtpCountdown();
    const frozen = el.textContent;
    vi.advanceTimersByTime(5000);
    expect(el.textContent).toBe(frozen);
  });
});

describe("moduleStartedAtFromRun", () => {
  it("해당 모듈의 started_at 을 찾는다", () => {
    const run = { modules: [{ module_id: "a", started_at: "2026-08-29T09:00:00Z" }] };
    expect(moduleStartedAtFromRun(run, "a")).toBe("2026-08-29T09:00:00Z");
  });

  it("없는 모듈이면 null", () => {
    expect(moduleStartedAtFromRun({ modules: [] }, "a")).toBeNull();
  });

  it("run 이 null 이어도 던지지 않는다", () => {
    expect(moduleStartedAtFromRun(null, "a")).toBeNull();
  });
});
