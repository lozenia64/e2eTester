import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = `
    <div class="dash">
      <div class="dash-sys-row" data-system-code="hom">
        <div class="dash-sys-row__modules">
          <a class="dash-mod dash-mod--link" href="/runs/101">
            <span class="dash-mod__label">LOGIN</span>
          </a>
        </div>
        <div class="dash-sys-row__segment">
          <a class="dash-seg dash-seg--link" href="/runs/102" aria-label="segment"></a>
        </div>
      </div>
    </div>
    <div id="dash-drawer-body"></div>
    <div id="dash-error" class="hidden"></div>
  `;
  document.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", (event) => event.preventDefault());
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.doUnmock("alpinejs");
  vi.doUnmock("htmx.org");
  document.body.innerHTML = "";
});

describe("dashboard entry", () => {
  it("행 클릭 시 드로어 타겟으로 htmx.ajax를 호출한다", async () => {
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
      .querySelector(".dash-sys-row")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

    expect(ajax).toHaveBeenCalledWith("get", "/api/dashboard/daily/fragments/system/hom/panel", {
      target: "#dash-drawer-body",
      swap: "innerHTML",
    });
    expect(opened).toBe(1);
  });

  it("기존 중첩 run 링크는 드로어를 열지 않고 통과시킨다", async () => {
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
