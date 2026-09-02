import { describe, expect, it } from "vitest";
import { buildGrid, renderGrid } from "./coverage";

const cell = (day: string, slot: string, tone: string | null, status: string) => ({
  day_key: day,
  slot_id: slot,
  status,
  status_label: null,
  tone,
  run_id: null,
  checked_at: null,
});

const payload = (cells: ReturnType<typeof cell>[]) => ({
  window: { day_keys: ["2026-09-01", "2026-09-02"] },
  systems: [{ system_code: "hom", system_name: "HOM", cells }],
});

describe("buildGrid", () => {
  it("하루 3슬롯이 모두 비면 not_checked 다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "not_checked", "not_checked"),
      cell("2026-09-01", "afternoon", "not_checked", "not_checked"),
      cell("2026-09-01", "evening", "not_checked", "not_checked"),
    ]));

    expect(rows[0]!.days[0]!.tone).toBe("not_checked");
    expect(rows[0]!.days[0]!.ran).toBe(0);
  });

  it("한 슬롯만 돌고 둘이 비면 그 슬롯의 톤을 따른다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "not_checked", "not_checked"),
      cell("2026-09-01", "evening", "not_checked", "not_checked"),
    ]));

    expect(rows[0]!.days[0]!.tone).toBe("passed");
    expect(rows[0]!.days[0]!.ran).toBe(1);
  });

  it("돌아간 것들 중 최악을 고른다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "error", "error"),
      cell("2026-09-01", "evening", "anomaly", "anomaly"),
    ]));

    expect(rows[0]!.days[0]!.tone).toBe("error");
  });

  it("anomaly 는 passed 를 이긴다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "anomaly", "anomaly"),
    ]));

    expect(rows[0]!.days[0]!.tone).toBe("anomaly");
  });

  it("running 은 passed 보다 앞선다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-02", "morning", "passed", "passed"),
      cell("2026-09-02", "afternoon", "running", "running"),
    ]));

    expect(rows[0]!.days[1]!.tone).toBe("running");
  });

  it("응답에 없는 날도 열을 만든다", () => {
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "passed", "passed")]));

    expect(rows[0]!.days.map((d) => d.day_key)).toEqual(["2026-09-01", "2026-09-02"]);
    expect(rows[0]!.days[1]!.tone).toBe("not_checked");
  });

  it("슬롯 톤을 순서대로 보존한다", () => {
    const rows = buildGrid(payload([
      cell("2026-09-01", "morning", "passed", "passed"),
      cell("2026-09-01", "afternoon", "error", "error"),
    ]));

    expect(rows[0]!.days[0]!.slots).toEqual(["passed", "error"]);
  });
});

describe("renderGrid", () => {
  it("셀에 톤과 좌표를 data 속성으로 싣는다", () => {
    const root = document.createElement("div");
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "error", "error")]));

    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);

    const target = root.querySelector<HTMLElement>('[data-day="2026-09-01"][data-system="hom"]');
    expect(target).not.toBeNull();
    expect(target!.dataset.tone).toBe("error");
  });

  it("다시 그려도 셀이 쌓이지 않는다", () => {
    const root = document.createElement("div");
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "passed", "passed")]));

    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);
    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);

    expect(root.querySelectorAll("[data-day]").length).toBe(2);
  });

  it("시스템이 하나여도 성립한다", () => {
    const root = document.createElement("div");
    const rows = buildGrid(payload([cell("2026-09-01", "morning", "passed", "passed")]));

    renderGrid(root, rows, ["2026-09-01", "2026-09-02"]);

    expect(root.querySelectorAll("[data-system]").length).toBeGreaterThan(0);
  });
});
