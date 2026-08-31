import { beforeEach, describe, expect, it } from "vitest";
import { applyFocus } from "./modules";

function host(...specs: Array<[string, string]>) {
  document.body.innerHTML = specs
    .map(
      ([id, status], order) =>
        `<li class="run-mod" data-module-id="${id}" data-order="${order}" data-status="${status}"></li>`,
    )
    .join("");
  return document.body;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("applyFocus", () => {
  it("초점 모듈에만 data-focus 를 세운다", () => {
    host(["a", "passed"], ["b", "error"], ["c", "pending"]);
    expect(applyFocus()).toBe("b");
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(1);
    expect(document.querySelector('[data-focus="true"]')!.getAttribute("data-module-id")).toBe("b");
  });

  it("초점이 옮겨가면 이전 것을 지운다", () => {
    host(["a", "running"], ["b", "pending"]);
    applyFocus();
    document.querySelector('[data-module-id="a"]')!.setAttribute("data-status", "passed");
    document.querySelector('[data-module-id="b"]')!.setAttribute("data-status", "error");
    expect(applyFocus()).toBe("b");
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(1);
  });

  it("초점이 없으면 아무것도 세우지 않는다", () => {
    host(["a", "passed"], ["b", "passed"]);
    expect(applyFocus()).toBeNull();
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(0);
  });

  it("모듈이 없어도 던지지 않는다", () => {
    expect(applyFocus()).toBeNull();
  });
});
