import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = `
    <div class="dash">
      <div class="dash-sys-row" data-system-code="hom">
        <span class="dash-sys-row__icon">HOM</span>
        <button type="button" class="dash-sys-row__name" data-action="detail" aria-label="홈 상세 보기">홈</button>
        <div class="dash-sys-row__cells">
          <a class="dash-cell dash-cell--link" href="/runs/101" aria-label="로그인 · 통과">
            <span class="dash-cell__glyph" aria-hidden="true">●</span>
          </a>
        </div>
      </div>
    </div>
    <div id="dash-drawer-body"></div>
    <div id="dash-error" class="hidden"></div>
  `;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.doUnmock("alpinejs");
  vi.doUnmock("htmx.org");
  document.body.innerHTML = "";
});

describe("dashboard entry", () => {
  it("행 일반 영역 클릭 시 드로어 타겟으로 htmx.ajax를 호출한다", async () => {
    const ajax = vi.fn();
    const defineExtension = vi.fn();
    vi.doMock("alpinejs", () => ({
      default: { start: vi.fn() },
    }));
    vi.doMock("htmx.org", () => ({
      default: { ajax, defineExtension },
    }));
    vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);

    let opened = 0;
    window.addEventListener("dash-open-drawer", () => {
      opened += 1;
    });

    await import("./main");
    await import("./dashboard");

    document
      .querySelector(".dash-sys-row__icon")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

    expect(ajax).toHaveBeenCalledWith("get", "/api/dashboard/daily/fragments/system/hom/panel", {
      target: "#dash-drawer-body",
      swap: "innerHTML",
    });
    expect(opened).toBe(1);
  });

  it("시스템 이름 버튼 클릭 시 드로어를 연다", async () => {
    const ajax = vi.fn();
    const defineExtension = vi.fn();
    vi.stubGlobal("htmx", { ajax });
    vi.doMock("htmx.org", () => ({
      default: { ajax, defineExtension },
    }));
    vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);

    let opened = 0;
    window.addEventListener("dash-open-drawer", () => {
      opened += 1;
    });

    await import("./dashboard");

    document
      .querySelector(".dash-sys-row__name")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

    expect(ajax).toHaveBeenCalledWith("get", "/api/dashboard/daily/fragments/system/hom/panel", {
      target: "#dash-drawer-body",
      swap: "innerHTML",
    });
    expect(opened).toBe(1);
  });

  it("새 run 셀 링크의 마우스·키보드 동작은 드로어를 열거나 기본 동작을 막지 않는다", async () => {
    const ajax = vi.fn();
    const defineExtension = vi.fn();
    vi.stubGlobal("htmx", { ajax });
    vi.doMock("htmx.org", () => ({
      default: { ajax, defineExtension },
    }));
    vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);

    let opened = 0;
    window.addEventListener("dash-open-drawer", () => {
      opened += 1;
    });

    await import("./dashboard");

    const link = document.querySelector<HTMLAnchorElement>(".dash-cell--link");
    expect(link).not.toBeNull();
    const mouse = new MouseEvent("click", { bubbles: true, cancelable: true });
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    const space = new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
    link?.dispatchEvent(mouse);
    link?.dispatchEvent(enter);
    link?.dispatchEvent(space);

    expect(ajax).not.toHaveBeenCalled();
    expect(opened).toBe(0);
    expect(mouse.defaultPrevented).toBe(false);
    expect(enter.defaultPrevented).toBe(false);
    expect(space.defaultPrevented).toBe(false);
  });

  it("기존 중첩 run 링크도 드로어를 열지 않고 통과시킨다", async () => {
    const ajax = vi.fn();
    const defineExtension = vi.fn();
    vi.stubGlobal("htmx", { ajax });
    vi.doMock("htmx.org", () => ({
      default: { ajax, defineExtension },
    }));
    vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);

    let opened = 0;
    window.addEventListener("dash-open-drawer", () => {
      opened += 1;
    });

    await import("./dashboard");

    const row = document.querySelector(".dash-sys-row");
    row?.insertAdjacentHTML(
      "beforeend",
      `<a class="dash-mod dash-mod--link" href="/runs/102"><span class="dash-mod__label">LOGIN</span></a>
       <a class="dash-seg dash-seg--link" href="/runs/103" aria-label="segment"></a>`,
    );
    document
      .querySelector(".dash-mod__label")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(ajax).not.toHaveBeenCalled();
    expect(opened).toBe(0);

    document
      .querySelector(".dash-seg--link")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(ajax).not.toHaveBeenCalled();
    expect(opened).toBe(0);
  });
});
