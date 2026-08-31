import { beforeEach, describe, expect, it } from "vitest";
import {
  exportText,
  hiddenCount,
  isFilterManual,
  pushLog,
  resetLog,
  setModuleFilter,
  setSearch,
  visibleEntries,
} from "./log";

const line = (moduleId: string, message: string) => ({ moduleId, message });

beforeEach(() => {
  resetLog([]);
  setModuleFilter("", { manual: false });
  setSearch("");
});

describe("필터", () => {
  it("모듈로 좁힌다", () => {
    resetLog([line("a", "hello"), line("b", "world")]);
    setModuleFilter("a");
    expect(visibleEntries().map((entry) => entry.message)).toEqual(["hello"]);
  });

  it("검색어는 대소문자를 가리지 않는다", () => {
    resetLog([line("a", "TimeoutError"), line("a", "ok")]);
    setSearch("timeout");
    expect(visibleEntries()).toHaveLength(1);
  });

  it("모듈과 검색어가 함께 걸린다", () => {
    resetLog([line("a", "boom"), line("b", "boom")]);
    setModuleFilter("b");
    setSearch("boom");
    expect(visibleEntries()).toHaveLength(1);
  });
});

describe("자동/수동 필터", () => {
  it("기본은 자동이다", () => {
    expect(isFilterManual()).toBe(false);
  });

  it("사용자가 바꾸면 수동이 된다", () => {
    setModuleFilter("a", { manual: true });
    expect(isFilterManual()).toBe(true);
  });

  it("수동으로 바뀐 뒤에도 자동 호출은 값을 덮지 않는다", () => {
    setModuleFilter("a", { manual: true });
    setModuleFilter("b");
    expect(visibleEntries).toBeDefined();
    expect(isFilterManual()).toBe(true);
    resetLog([line("a", "keep"), line("b", "drop")]);
    expect(visibleEntries().map((entry) => entry.message)).toEqual(["keep"]);
  });
});

describe("표시 상한 2,000줄", () => {
  const many = (count: number) =>
    Array.from({ length: count }, (_, index) => line("a", `line-${index}`));

  it("2,000줄을 넘으면 최근 것만 보인다", () => {
    resetLog(many(2500));
    expect(visibleEntries()).toHaveLength(2000);
    expect(visibleEntries()[0]?.message).toBe("line-500");
  });

  it("잘린 줄 수를 센다", () => {
    resetLog(many(2500));
    expect(hiddenCount()).toBe(500);
  });

  it("2,000줄 이하면 아무것도 안 자른다", () => {
    resetLog(many(10));
    expect(hiddenCount()).toBe(0);
  });

  it("상한은 필터 적용 뒤에 걸린다", () => {
    resetLog([...many(2500), line("z", "other")]);
    setModuleFilter("z");
    expect(visibleEntries()).toHaveLength(1);
    expect(hiddenCount()).toBe(0);
  });
});

describe("내보내기", () => {
  it("상한을 적용하지 않는다 — 조사 도구의 본질", () => {
    resetLog(Array.from({ length: 2500 }, (_, index) => line("a", `L${index}`)));
    expect(exportText().split("\n")).toHaveLength(2500);
  });

  it("필터는 적용한다", () => {
    resetLog([line("a", "keep"), line("b", "drop")]);
    setModuleFilter("a");
    expect(exportText()).toBe("[a] keep");
  });
});

describe("추가", () => {
  it("push 한 줄이 보인다", () => {
    resetLog([]);
    pushLog(line("a", "first"));
    expect(visibleEntries()).toHaveLength(1);
  });
});
