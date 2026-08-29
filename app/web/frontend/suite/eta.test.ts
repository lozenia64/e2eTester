import { describe, expect, it } from "vitest";
import { computeSuiteEta } from "./eta";

const MIN = 60_000;
const step = (order: number, code: string, status: string) => ({ order, system_code: code, status });

const base: Parameters<typeof computeSuiteEta>[0] = {
  steps: [step(0, "hom", "passed"), step(1, "fp", "running"), step(2, "hrp", "pending")],
  baselines: { hom: 3 * MIN, fp: 2 * MIN, hrp: 4 * MIN },
  currentStepOrder: 1,
  currentStepElapsedMs: 30_000,
  suiteStatus: "running",
};

describe("computeSuiteEta", () => {
  it("끝난 스텝은 빼고, 현재 스텝은 경과를 뺀다", () => {
    // fp 남은 90초 + hrp 4분 = 5분 30초
    expect(computeSuiteEta(base).remainingMs).toBe(90_000 + 4 * MIN);
  });

  it("현재 스텝이 baseline 을 넘겨도 음수로 가지 않는다", () => {
    const r = computeSuiteEta({ ...base, currentStepElapsedMs: 10 * MIN });
    expect(r.remainingMs).toBe(4 * MIN);
  });

  it("입력 대기 중에는 계산을 보류한다", () => {
    const r = computeSuiteEta({ ...base, suiteStatus: "waiting_input" });
    expect(r.held).toBe(true);
    expect(r.remainingMs).toBeNull();
  });

  it("baseline 이 없는 스텝은 제외하고 partial 을 세운다", () => {
    const r = computeSuiteEta({ ...base, baselines: { hom: 3 * MIN, fp: 2 * MIN } });
    expect(r.remainingMs).toBe(90_000);
    expect(r.partial).toBe(true);
  });

  it("남은 스텝의 baseline 이 전부 없으면 계산하지 않는다", () => {
    const r = computeSuiteEta({ ...base, baselines: {} });
    expect(r.remainingMs).toBeNull();
    expect(r.partial).toBe(true);
  });

  it("남은 스텝이 없으면 0 이다", () => {
    const r = computeSuiteEta({
      ...base,
      steps: [step(0, "hom", "passed"), step(1, "fp", "passed")],
      currentStepOrder: null,
    });
    expect(r.remainingMs).toBe(0);
  });
});
