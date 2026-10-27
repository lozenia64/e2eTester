import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardController } from "./controller";

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function root(): HTMLElement {
  document.body.innerHTML = `<main><button data-refresh>새로고침</button>${["performance", "daily", "coverage"].map(id => `<p data-status="${id}"></p>`).join("")}</main>`;
  return document.querySelector("main")!;
}

describe("대시보드 갱신", () => {
  it("최초 조회 실패를 로딩 상태로 남기지 않는다", async () => {
    const el = root();
    el.insertAdjacentHTML("beforeend", '<p data-placeholder="performance">불러오는 중…</p>');
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("연결 실패"); }));
    const controller = new DashboardController(el, vi.fn());
    await controller.refresh();
    expect(el.querySelector("[data-placeholder]")!.textContent).toContain("불러오지 못했습니다");
    controller.destroy();
  });
  it("일부 실패가 다른 영역의 성공을 막지 않고 재시도도 최초 연출을 반복하지 않는다", async () => {
    const render = vi.fn();
    let fail = false;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (fail && url.includes("performance")) throw new Error("연결 실패");
      return { ok: true, json: async () => ({ generated_at: "2026-10-27T01:00:00Z" }) };
    }));
    const el = root();
    const controller = new DashboardController(el, render);
    await controller.refresh();
    expect(render.mock.calls).toHaveLength(3);
    expect(render.mock.calls.every(call => call[2] === true)).toBe(true);
    fail = true;
    await controller.refresh();
    expect(render.mock.calls).toHaveLength(5);
    expect(render.mock.calls.slice(3).every(call => call[2] === false)).toBe(true);
    expect(el.querySelector('[data-status="performance"]')!.textContent).toContain("갱신 실패");
    expect(el.querySelector('[data-status="performance"]')!.textContent).toContain("10:00");
    expect(el.querySelector('[data-status="daily"]')!.textContent).not.toContain("실패");
    controller.destroy();
  });

  it("조회가 끝나기 전 중복 요청을 만들지 않는다", async () => {
    let resolve!: (value: Response) => void;
    const pending = new Promise<Response>(r => { resolve = r; });
    const fetcher = vi.fn(() => pending);
    vi.stubGlobal("fetch", fetcher);
    const controller = new DashboardController(root(), vi.fn());
    const first = controller.refresh();
    await controller.refresh();
    expect(fetcher).toHaveBeenCalledTimes(3);
    resolve({ ok: true, json: async () => ({}) } as Response);
    await first;
    controller.destroy();
  });

  it("숨겨진 탭에서는 주기 요청을 멈추고 복귀하면 갱신한다", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
    const controller = new DashboardController(root(), vi.fn());
    await controller.refresh();
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetch).toHaveBeenCalledTimes(3);
    vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(fetch).toHaveBeenCalledTimes(6);
    controller.destroy();
  });
});
