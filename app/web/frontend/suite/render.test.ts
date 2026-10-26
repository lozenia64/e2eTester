import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { animateCount, renderSuiteSummary, rememberSuite } from "./render";
import { suiteRunCache } from "./steps";

const byId = (id: string) => document.getElementById(id) as HTMLElement;

const SUMMARY_MARKUP = `
  <section class="suite-sum">
    <div class="suite-ring" id="suite-ring"><span id="suite-ring-value">0</span></div>
    <div class="suite-now" id="suite-now" data-kind="idle">
      <p id="suite-now-eyebrow"></p><p id="suite-now-title"></p><p id="suite-now-meta"></p>
    </div>
    <p class="suite-counts" id="suite-counts">
      <span id="suite-count-passed"></span><span id="suite-count-failed"></span>
      <span id="suite-count-blocked"></span><span id="suite-count-remaining"></span>
      <span id="suite-progress-elapsed"></span><span id="suite-progress-eta"></span>
    </p>
  </section>`;

const step = (status: string) => ({ order: 0, system_name: "모바일", system_code: "mhm", run_id: "r1", status, module_total: 2 });

describe("renderSuiteSummary", () => {
  afterEach(() => vi.unstubAllGlobals());
  beforeEach(() => {
    document.body.innerHTML = SUMMARY_MARKUP;
    suiteRunCache.clear();
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
  });

  it("스냅샷 + 캐시로 링·집계·카드를 채운다", () => {
    suiteRunCache.set("r1", {
      status: "RUNNING",
      modules: [
        { module_id: "a", name: "로그인", order: 0, status: "PASSED" },
        { module_id: "b", name: "보험금청구", order: 1, status: "RUNNING" },
      ],
    });
    rememberSuite({ status: "RUNNING", current_step_index: 0, active_run_id: "r1", steps: [step("RUNNING")] });
    renderSuiteSummary();
    expect(byId("suite-ring-value").textContent).toBe("50");
    expect(byId("suite-ring").style.getPropertyValue("--ring-deg")).toBe("180deg");
    expect(byId("suite-ring").getAttribute("aria-label")).toBe("전체 모듈 진행률 50%");
    expect(byId("suite-now").dataset.kind).toBe("running");
    expect(byId("suite-now-title").textContent).toBe("모바일 › 보험금청구");
    expect(byId("suite-now-meta").textContent).toBe("시스템 1/1 · 모듈 2/2");
    expect(byId("suite-count-passed").textContent).toBe("✓ 1 통과");
    expect(byId("suite-count-failed").textContent).toBe("✕ 0 실패");
    expect(byId("suite-count-remaining").textContent).toBe("남음 1");
    expect(byId("suite-count-blocked").hidden).toBe(true);
  });

  it("차단이 있으면 차단 칸을 보인다", () => {
    suiteRunCache.set("r1", {
      status: "ERROR",
      modules: [
        { module_id: "a", name: "로그인", order: 0, status: "ERROR" },
        { module_id: "b", name: "보험금청구", order: 1, status: "BLOCKED" },
      ],
    });
    rememberSuite({ status: "ERROR", current_step_index: 0, steps: [step("ERROR")] });
    renderSuiteSummary();
    expect(byId("suite-count-blocked").hidden).toBe(false);
    expect(byId("suite-count-blocked").textContent).toBe("⊘ 1 차단");
    expect(byId("suite-ring-value").textContent).toBe("100");
  });

  it("끝나면 finished 카드", () => {
    rememberSuite({ status: "PASSED", current_step_index: 0, steps: [step("PASSED")] });
    renderSuiteSummary();
    expect(byId("suite-now").dataset.kind).toBe("finished");
    expect(byId("suite-now-eyebrow").textContent).toBe("정상");
    expect(byId("suite-now-title").textContent).toBe("통과 2 · 실패 0");
  });

  it("끝난 수트의 경과는 ended_at 에서 멈춘다 — 1초 시계가 계속 올리지 않는다", () => {
    rememberSuite({
      status: "PASSED",
      current_step_index: 0,
      started_at: "2026-10-26T04:41:37Z",
      ended_at: "2026-10-26T04:55:00Z",
      steps: [step("PASSED")],
    });
    renderSuiteSummary();
    expect(byId("suite-progress-elapsed").textContent).toBe("13:23 경과");
  });

  it("같은 문구는 다시 쓰지 않는다 — 1초 시계가 텍스트 노드를 갈아끼우지 않는다", () => {
    rememberSuite({ status: "PASSED", current_step_index: 0, steps: [step("PASSED")] });
    renderSuiteSummary();
    const before = byId("suite-now-title").firstChild;
    renderSuiteSummary();
    expect(byId("suite-now-title").firstChild).toBe(before);
  });

  it("OTP 대기면 waiting 카드", () => {
    suiteRunCache.set("r1", {
      status: "WAITING_INPUT",
      modules: [{ module_id: "a", name: "로그인", order: 0, status: "WAITING_INPUT" }],
    });
    rememberSuite({ status: "WAITING_INPUT", current_step_index: 0, awaiting_input_run_id: "r1", steps: [step("WAITING_INPUT")] });
    renderSuiteSummary();
    expect(byId("suite-now").dataset.kind).toBe("waiting");
    expect(byId("suite-now-eyebrow").textContent).toBe("OTP 입력 대기");
  });

  it("같은 목표값 재렌더가 카운트업 도중 숫자를 앞뒤로 튀게 하지 않는다", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => frames.push(callback));
    const node = byId("suite-ring-value");
    animateCount(node, 100);
    frames.shift()!(performance.now() + 100);
    const intermediate = Number(node.textContent);
    expect(intermediate).toBeGreaterThan(0);
    expect(intermediate).toBeLessThan(100);
    animateCount(node, 100);
    expect(Number(node.textContent)).toBe(intermediate);
  });
});
