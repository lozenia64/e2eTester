import { describe, expect, it } from "vitest";
import { normalizeTone, renderStatusBadge, statusLabel } from "./index";

describe("normalizeTone", () => {
  it("레거시 FAILED 를 anomaly 로 정규화한다", () => {
    expect(normalizeTone("failed")).toBe("anomaly");
    expect(normalizeTone("FAILED")).toBe("anomaly");
  });

  it("queued 를 pending 으로 정규화한다", () => {
    expect(normalizeTone("queued")).toBe("pending");
  });

  it("알 수 없는 상태는 pending 으로 떨어뜨린다", () => {
    expect(normalizeTone("무엇인가")).toBe("pending");
  });

  it("waiting_input 을 running 과 구분한다", () => {
    expect(normalizeTone("waiting_input")).toBe("waiting_input");
    expect(normalizeTone("running")).toBe("running");
  });
});

describe("statusLabel", () => {
  it("생성된 라벨 맵에서 한국어 라벨을 읽는다", () => {
    expect(statusLabel("passed")).toBe("정상");
    expect(statusLabel("error")).toBe("점검실패");
    expect(statusLabel("failed")).toBe("이상징후");
  });
});

describe("renderStatusBadge", () => {
  it("data-tone 속성으로 색을 결정한다(클래스 하드코딩 없음)", () => {
    const el = renderStatusBadge("passed");
    expect(el.dataset.tone).toBe("passed");
    expect(el.className).not.toMatch(/bg-|text-(red|emerald|amber)/);
  });

  it("라벨을 텍스트로 넣는다", () => {
    expect(renderStatusBadge("error").textContent).toBe("점검실패");
  });

  it("size 옵션을 data-size 로 반영한다", () => {
    expect(renderStatusBadge("passed", { size: "sm" }).dataset.size).toBe("sm");
    expect(renderStatusBadge("passed").dataset.size).toBe("md");
  });

  it("라벨을 주면 그것을 쓴다 — 서버가 합성 상태 이름을 줄 때 필요하다", () => {
    const el = renderStatusBadge("not_inspected", { label: "미점검" });
    expect(el.textContent).toBe("미점검");
  });

  it("라벨을 안 주면 기존 동작 그대로다", () => {
    const el = renderStatusBadge("passed");
    expect(el.textContent).toBe("정상");
  });

  it("합성 상태의 톤은 pending 으로 떨어진다 — 색은 회색이어야 한다", () => {
    const el = renderStatusBadge("not_inspected", { label: "미점검" });
    expect(el.dataset.tone).toBe("pending");
  });
});
