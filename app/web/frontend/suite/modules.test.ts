import { describe, expect, it } from "vitest";
import { buildModuleChips, describeNow, summarizeSuiteModules } from "./modules";

const mods = (...specs: Array<[string, string]>) =>
  specs.map(([module_id, status], order) => ({ module_id, name: module_id, order, status }));

describe("buildModuleChips", () => {
  it("order 순, 톤은 normalizeTone, skipped 는 제외", () => {
    const chips = buildModuleChips({
      status: "RUNNING",
      modules: mods(["b", "RUNNING"], ["a", "PASSED"], ["s", "SKIPPED"], ["f", "FAILED"]),
    });
    expect(chips.map((c) => [c.moduleId, c.tone])).toEqual([
      ["b", "running"],
      ["a", "passed"],
      ["f", "anomaly"],
    ]);
  });
});

describe("summarizeSuiteModules", () => {
  it("BLOCKED 를 끝난 것으로 센다 — 실패 run 이 끝나면 100%", () => {
    const runs = new Map([
      ["r1", { status: "ERROR", modules: mods(["a", "PASSED"], ["b", "ERROR"], ["c", "BLOCKED"], ["d", "BLOCKED"]) }],
    ]);
    const s = summarizeSuiteModules([{ order: 0, run_id: "r1", status: "ERROR", module_total: 4 }], runs);
    expect(s).toEqual({ done: 4, total: 4, percent: 100, passed: 1, failed: 1, blocked: 2, remaining: 0 });
  });

  it("캐시에 없는 passed 스텝은 module_total 전부 통과로 친다", () => {
    const s = summarizeSuiteModules([{ order: 0, run_id: "r0", status: "PASSED", module_total: 10 }], new Map());
    expect(s.passed).toBe(10);
    expect(s.percent).toBe(100);
  });

  it("캐시에 없는 비-passed 스텝·대기 스텝은 전부 남음", () => {
    const s = summarizeSuiteModules([{ order: 0, run_id: null, status: "PENDING", module_total: 3 }], new Map());
    expect(s).toMatchObject({ done: 0, total: 3, remaining: 3, percent: 0 });
  });

  it("skipped 스텝은 분모에서 빠지고, 전부 skipped 면 0% (NaN 아님)", () => {
    const s = summarizeSuiteModules([{ order: 0, run_id: null, status: "SKIPPED", module_total: 4 }], new Map());
    expect(s).toMatchObject({ total: 0, percent: 0 });
  });

  it("끝난 스텝에 남은 미실행 모듈은 남음이 아니다 — 끝난 수트가 100% 에 닿는다", () => {
    const runs = new Map([["r", { status: "ERROR", modules: mods(["a", "ERROR"], ["b", "PENDING"]) }]]);
    const s = summarizeSuiteModules(
      [
        { order: 0, run_id: "r", status: "ERROR", module_total: 2 },
        { order: 1, run_id: null, status: "CANCELLED", module_total: 3 },
      ],
      runs,
    );
    expect(s).toMatchObject({ total: 5, done: 5, percent: 100, failed: 1, remaining: 0 });
  });

  it("anomaly 는 failed 에 합산, cancelled 는 done 에만", () => {
    const runs = new Map([
      ["r", { status: "RUNNING", modules: mods(["a", "ANOMALY"], ["b", "CANCELLED"], ["c", "PENDING"]) }],
    ]);
    const s = summarizeSuiteModules([{ order: 0, run_id: "r", status: "RUNNING", module_total: 3 }], runs);
    expect(s).toMatchObject({ done: 2, failed: 1, passed: 0, remaining: 1 });
  });
});

describe("describeNow", () => {
  const steps = [
    { order: 0, system_name: "대표홈페이지(PC)", run_id: "r0", status: "PASSED", module_total: 2 },
    { order: 1, system_name: "대표홈페이지(모바일)", run_id: "r1", status: "RUNNING", module_total: 3 },
    { order: 2, system_name: "현장출동", run_id: null, status: "SKIPPED", module_total: 4 },
  ];

  it("실행 중 모듈을 카드로 — 시스템 순번은 skipped 제외 기준", () => {
    const runs = new Map([
      [
        "r1",
        {
          status: "RUNNING",
          modules: [
            { module_id: "a", name: "로그인", order: 0, status: "PASSED" },
            { module_id: "b", name: "보험금청구", order: 1, status: "RUNNING", started_at: "2026-10-26T04:00:00Z" },
            { module_id: "c", name: "로그아웃", order: 2, status: "PENDING" },
          ],
        },
      ],
    ]);
    const suite = { status: "RUNNING", steps, current_step_index: 1, active_run_id: "r1" };
    expect(describeNow(suite, runs, summarizeSuiteModules(steps, runs))).toEqual({
      kind: "running",
      systemName: "대표홈페이지(모바일)",
      moduleName: "보험금청구",
      moduleStartedAt: "2026-10-26T04:00:00Z",
      systemIndex: 2,
      systemTotal: 2,
      moduleIndex: 2,
      moduleTotal: 3,
    });
  });

  it("OTP 대기면 waiting", () => {
    const runs = new Map([
      ["r1", { status: "WAITING_INPUT", modules: [{ module_id: "a", name: "로그인", order: 0, status: "WAITING_INPUT" }] }],
    ]);
    const suite = { status: "WAITING_INPUT", steps, current_step_index: 1, awaiting_input_run_id: "r1" };
    expect(describeNow(suite, runs, summarizeSuiteModules(steps, runs))).toMatchObject({
      kind: "waiting",
      moduleName: "로그인",
    });
  });

  it("수트가 끝나면 finished — 라벨은 statusLabel", () => {
    const suite = { status: "ANOMALY", steps, current_step_index: 2 };
    const summary = { done: 5, total: 5, percent: 100, passed: 4, failed: 1, blocked: 0, remaining: 0 };
    expect(describeNow(suite, new Map(), summary)).toEqual({
      kind: "finished",
      statusLabel: "이상징후",
      passed: 4,
      failed: 1,
    });
  });
});
