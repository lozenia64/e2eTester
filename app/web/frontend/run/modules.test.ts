import { beforeEach, describe, expect, it } from "vitest";
import { applyFocus, moduleRuntimeState, updateModuleCard } from "./modules";

function host(...specs: Array<[string, string]>) {
  document.body.innerHTML = specs
    .map(
      ([id, status], order) =>
        `<li class="run-mod" data-module-id="${id}" data-order="${order}" data-status="${status}"></li>`,
    )
    .join("");
  return document.body;
}

function moduleCard(id: string, status: string, order: number) {
  return `<li class="run-mod status-${status}" data-module-id="${id}" data-order="${order}" data-status="${status}">
    <span class="status-badge" data-role="module-status"></span>
    <p data-role="module-message"></p>
    <span data-role="module-duration"></span>
    <span data-role="module-artifacts"></span>
    <section class="analysis-panel is-hidden" data-role="failure-analysis" hidden>
      <span data-role="analysis-category"></span>
      <p data-role="analysis-summary"></p>
      <p data-role="analysis-action"></p>
      <p data-role="analysis-details"></p>
    </section>
    <div data-role="module-artifacts-list"></div>
  </li>`;
}

function moduleHost(...specs: Array<[string, string]>) {
  document.body.innerHTML = specs.map(([id, status], order) => moduleCard(id, status, order)).join("");
}

function update(module_id: string, status: string, failure_analysis: unknown = null) {
  updateModuleCard({
    module_id,
    status,
    started_at: "2026-08-31T00:00:00Z",
    message: "완료",
    duration_ms: 123,
    artifact_count: 0,
    artifacts: [],
    failure_analysis,
  });
}

beforeEach(() => {
  document.body.innerHTML = "";
  moduleRuntimeState.clear();
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

describe("updateModuleCard", () => {
  it("카드가 아직 없어도 소켓용 실행 상태를 기억한다", () => {
    update("a", "waiting_input");

    expect(moduleRuntimeState.get("a")).toEqual({
      status: "waiting_input",
      startedAt: "2026-08-31T00:00:00Z",
    });
  });

  it("새 실패 분석이 오면 레거시 숨김 클래스를 제거해 패널을 보인다", () => {
    moduleHost(["a", "error"]);

    update("a", "error", {
      category: "selector",
      user_summary: "버튼을 찾지 못했습니다.",
      recommended_action: "선택자를 확인하세요.",
      developer_details: "#submit 이 없습니다.",
    });

    const panel = document.querySelector<HTMLElement>('[data-role="failure-analysis"]')!;
    expect(panel.classList.contains("is-hidden")).toBe(false);
    expect(panel.hidden).toBe(false);
    expect(panel.querySelector('[data-role="analysis-summary"]')!.textContent).toBe("버튼을 찾지 못했습니다.");
  });

  it("상태가 바뀌면 이전 status 클래스를 새 상태 클래스로 교체한다", () => {
    moduleHost(["a", "running"]);

    update("a", "passed");

    const card = document.querySelector('[data-module-id="a"]')!;
    expect(card.classList.contains("status-running")).toBe(false);
    expect(card.classList.contains("status-passed")).toBe(true);
  });

  it("카드 상태 갱신 뒤 새 초점 모듈을 반영한다", () => {
    moduleHost(["a", "running"], ["b", "anomaly"]);
    applyFocus();

    update("b", "passed");

    expect(document.querySelector('[data-focus="true"]')!.getAttribute("data-module-id")).toBe("a");
  });
});
