import { afterEach, describe, expect, it, vi } from "vitest";
import { applySystemBadges, loadSystemBadges } from "./execute-badges";

function host(codes: string[]): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = codes.map((c) => `<span data-exec-badge="${c}"></span>`).join("");
  return root;
}

const HOM = { system_code: "hom", summary_badge: { label: "정상", tone: "passed" } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("applySystemBadges", () => {
  it("코드가 맞는 자리에 배지를 넣는다", () => {
    const root = host(["hom", "mhm"]);
    applySystemBadges(root, [HOM]);
    const slot = root.querySelector('[data-exec-badge="hom"]')!;
    expect(slot.textContent).toContain("정상");
    expect(slot.querySelector(".status-badge")!.getAttribute("data-tone")).toBe("passed");
  });

  it("서버 라벨을 그대로 쓴다 — 미점검이 대기로 바뀌면 안 된다", () => {
    const root = host(["hwtc"]);
    applySystemBadges(root, [
      { system_code: "hwtc", summary_badge: { label: "미점검", tone: "not_inspected" } },
    ]);
    expect(root.querySelector('[data-exec-badge="hwtc"]')!.textContent).toBe("미점검");
  });

  it("응답에 없는 시스템 자리는 비워 둔다", () => {
    const root = host(["hom", "mhm"]);
    applySystemBadges(root, [HOM]);
    expect(root.querySelector('[data-exec-badge="mhm"]')!.innerHTML).toBe("");
  });

  it("두 번 불러도 배지가 겹쳐 쌓이지 않는다", () => {
    const root = host(["hom"]);
    applySystemBadges(root, [HOM]);
    applySystemBadges(root, [HOM]);
    expect(root.querySelectorAll('[data-exec-badge="hom"] > *').length).toBe(1);
  });

  it("빈 배열이면 모든 자리를 비운다 — 조회 실패 시 화면은 살아야 한다", () => {
    const root = host(["hom"]);
    applySystemBadges(root, [HOM]);
    applySystemBadges(root, []);
    expect(root.querySelector('[data-exec-badge="hom"]')!.innerHTML).toBe("");
  });
});

describe("loadSystemBadges", () => {
  it("조회가 거부돼도 배지를 비워 두고 실행 제어를 바꾸지 않는다", async () => {
    const root = host(["hom"]);
    const start = document.createElement("button");
    start.disabled = false;
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network blocked")));

    await expect(loadSystemBadges(root)).resolves.toBeUndefined();

    expect(root.querySelector('[data-exec-badge="hom"]')!.innerHTML).toBe("");
    expect(start.disabled).toBe(false);
  });

  it("non-OK 응답도 배지를 비워 두고 실행 제어를 바꾸지 않는다", async () => {
    const root = host(["hom"]);
    const start = document.createElement("button");
    start.disabled = false;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: vi.fn().mockResolvedValue({ systems: [HOM] }) }),
    );

    await expect(loadSystemBadges(root)).resolves.toBeUndefined();

    expect(root.querySelector('[data-exec-badge="hom"]')!.innerHTML).toBe("");
    expect(start.disabled).toBe(false);
  });
});
