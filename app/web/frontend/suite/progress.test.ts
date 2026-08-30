import { describe, expect, it } from "vitest";
import { computeRunModuleProgress } from "./progress";

const mods = (...specs: Array<[string, string]>) =>
  specs.map(([module_id, status], order) => ({ module_id, name: module_id, order, status }));

describe("computeRunModuleProgress", () => {
  it("진행 중 모듈을 현재 위치로 잡는다", () => {
    const p = computeRunModuleProgress({
      status: "RUNNING",
      modules: mods(["a", "passed"], ["b", "running"], ["c", "pending"]),
    });
    expect(p.current).toBe(2);
    expect(p.total).toBe(3);
    expect(p.tone).toBe("active");
  });

  it("입력 대기 모듈은 waiting 톤이다", () => {
    const p = computeRunModuleProgress({
      status: "WAITING_INPUT",
      modules: mods(["a", "passed"], ["b", "waiting_input"]),
    });
    expect(p.tone).toBe("waiting");
  });

  it("완료되면 total/total", () => {
    const p = computeRunModuleProgress({
      status: "PASSED",
      modules: mods(["a", "passed"], ["b", "passed"]),
    });
    expect(p.label).toBe("2/2");
    expect(p.tone).toBe("passed");
  });

  it("모듈이 없으면 빈 결과를 돌려주고 던지지 않는다", () => {
    expect(computeRunModuleProgress({ status: "PENDING", modules: [] }).total).toBe(0);
    expect(computeRunModuleProgress(null).total).toBe(0);
  });

  it("skipped 모듈은 분모에서 빠진다", () => {
    const p = computeRunModuleProgress({
      status: "RUNNING",
      modules: mods(["a", "passed"], ["b", "skipped"], ["c", "running"]),
    });
    expect(p.total).toBe(2);
  });
});
