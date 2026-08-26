import { afterEach, describe, expect, it, vi } from "vitest";
import "../../entries/execute";
import { applyModuleSelection, bindModuleSelectors } from "./render";

const definition = {
  modules: [
    { module_id: "login", name: "로그인", depends_on: [], order: 1 },
    { module_id: "list", name: "조회", depends_on: ["login"], order: 2 },
    { module_id: "detail", name: "상세", depends_on: ["list"], order: 3 },
    { module_id: "pay", name: "결제", depends_on: ["login"], order: 4 },
  ],
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("bindModuleSelectors", () => {
  it("선행 모듈을 제외하면 모든 후손을 함께 해제하고 그래프 상태를 갱신한다", () => {
    // 이 동작이 빠지면 잘못된 의존성 조합이 선택 화면에 남는다.
    vi.stubGlobal("ResizeObserver", class { observe() {} });
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => callback(0));
    document.body.innerHTML = `
      <form class="system-form">
        <script type="application/json" data-role="system-definition">${JSON.stringify(definition)}</script>
        <section data-role="module-selector">
          <p data-role="module-selection-summary"></p>
          <div class="module-graph-viewport"><div data-role="module-graph-canvas"><svg data-role="module-graph-edges"></svg><div data-role="module-graph-grid"></div></div></div>
          <div class="is-hidden" data-role="module-selection-warning"></div>
        </section>
      </form>`;

    bindModuleSelectors(document);
    document.querySelector<HTMLButtonElement>('[data-module-id="login"]')!.click();

    expect(document.querySelectorAll('[data-role="module-graph-node"][data-selected="false"]')).toHaveLength(4);
    expect(document.querySelector('[data-role="module-selection-summary"]')!.textContent).toBe("0 / 4 선택 · 4개 제외");
    expect(document.querySelectorAll(".module-graph-edge.is-muted")).toHaveLength(3);
  });

  it("선택 적용은 실제 그래프 상태를 갱신한다", () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} });
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => callback(0));
    document.body.innerHTML = `
      <form class="system-form">
        <script type="application/json" data-role="system-definition">${JSON.stringify(definition)}</script>
        <section data-role="module-selector">
          <p data-role="module-selection-summary"></p>
          <div class="module-graph-viewport"><div data-role="module-graph-canvas"><svg data-role="module-graph-edges"></svg><div data-role="module-graph-grid"></div></div></div>
          <div class="is-hidden" data-role="module-selection-warning"></div>
        </section>
      </form>`;
    bindModuleSelectors(document);

    const form = document.querySelector<HTMLFormElement>(".system-form")!;
    applyModuleSelection(form, ["login", "pay"]);

    expect([...document.querySelectorAll('[data-role="module-graph-node"][data-selected="true"]')].map((node) => node.getAttribute("data-module-id"))).toEqual(["login", "pay"]);
    expect(document.querySelector('[data-role="module-selection-summary"]')!.textContent).toBe("2 / 4 선택 · 2개 제외");
  });
});
