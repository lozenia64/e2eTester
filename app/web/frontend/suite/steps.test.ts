import { describe, expect, it } from "vitest";
import type { StatusTone } from "../lib/status.generated";
import type { ModuleChip } from "./modules";
import { renderModuleChips } from "./steps";

const chip = (moduleId: string, tone: StatusTone): ModuleChip => ({ moduleId, name: moduleId, tone });

describe("renderModuleChips", () => {
  it("칩마다 li[data-module-id][data-tone], 이름과 run 링크", () => {
    const ul = document.createElement("ul");
    renderModuleChips(ul, [chip("로그인", "passed"), chip("메인", "error")], "r1");
    const items = [...ul.querySelectorAll("li")];
    expect(items.map((li) => [li.dataset.moduleId, li.dataset.tone])).toEqual([
      ["로그인", "passed"],
      ["메인", "error"],
    ]);
    expect(items[0]!.textContent).toContain("로그인");
    expect(ul.querySelector("a")?.getAttribute("href")).toBe("/runs/r1");
  });

  it("모듈 이름은 마크업으로 해석하지 않는다", () => {
    const ul = document.createElement("ul");
    renderModuleChips(ul, [{ moduleId: "x", name: "<b>x</b>", tone: "passed" }], "r1");
    expect(ul.querySelector("b")).toBeNull();
  });

  it("첫 렌더에는 pop 이 없다", () => {
    const ul = document.createElement("ul");
    renderModuleChips(ul, [chip("a", "running")], "r1");
    expect(ul.querySelector("[data-pop]")).toBeNull();
  });

  it("톤이 바뀐 칩만 pop, 같은 데이터 재렌더는 pop 없음", () => {
    const ul = document.createElement("ul");
    renderModuleChips(ul, [chip("a", "running"), chip("b", "pending")], "r1");
    renderModuleChips(ul, [chip("a", "passed"), chip("b", "pending")], "r1");
    expect([...ul.querySelectorAll<HTMLElement>("[data-pop]")].map((li) => li.dataset.moduleId)).toEqual(["a"]);
    renderModuleChips(ul, [chip("a", "passed"), chip("b", "pending")], "r1");
    expect(ul.querySelector("[data-pop]")).toBeNull();
  });

  it("차단 칩은 '차단' 을 덧붙인다", () => {
    const ul = document.createElement("ul");
    renderModuleChips(ul, [chip("로그아웃", "blocked")], "r1");
    expect(ul.textContent).toContain("차단");
  });
});
