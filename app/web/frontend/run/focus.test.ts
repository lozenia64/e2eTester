import { describe, expect, it } from "vitest";
import { computeFocusModuleId } from "./focus";

const m = (...specs: Array<[string, string]>) =>
  specs.map(([module_id, status], order) => ({ module_id, order, status }));

describe("computeFocusModuleId", () => {
  it("error 가 최우선이다", () => {
    expect(
      computeFocusModuleId(m(["a", "passed"], ["b", "anomaly"], ["c", "error"], ["d", "running"])),
    ).toBe("c");
  });

  it("error 가 여럿이면 order 가 가장 앞선 것", () => {
    expect(computeFocusModuleId(m(["a", "error"], ["b", "error"]))).toBe("a");
  });

  it("error 가 없으면 첫 anomaly", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "anomaly"], ["c", "running"]))).toBe("b");
  });

  it("둘 다 없으면 첫 running", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "running"], ["c", "pending"]))).toBe("b");
  });

  it("waiting_input 도 현재 모듈로 본다 — OTP 대기는 사람이 볼 자리다", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "waiting_input"]))).toBe("b");
  });

  it("전부 정상이면 null", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "passed"]))).toBeNull();
  });

  it("아직 시작 전이면 null", () => {
    expect(computeFocusModuleId(m(["a", "pending"], ["b", "pending"]))).toBeNull();
  });

  it("모듈이 없으면 null 이고 던지지 않는다", () => {
    expect(computeFocusModuleId([])).toBeNull();
  });

  it("order 가 배열 순서와 다르면 order 를 따른다", () => {
    const shuffled = [
      { module_id: "late", order: 5, status: "error" },
      { module_id: "early", order: 1, status: "error" },
    ];
    expect(computeFocusModuleId(shuffled)).toBe("early");
  });

  it("상태 대소문자가 섞여도 같게 판정한다", () => {
    expect(computeFocusModuleId(m(["a", "PASSED"], ["b", "ERROR"]))).toBe("b");
  });

  it("건너뛴 모듈은 초점이 되지 않는다", () => {
    expect(computeFocusModuleId(m(["a", "passed"], ["b", "skipped"], ["c", "passed"]))).toBeNull();
  });
});
