import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { exportText, resetLog, setModuleFilter, setSearch } from "./log";
import { moduleRuntimeState } from "./modules";
import { bindRunSocket } from "./socket";

type MessageListener = (event: MessageEvent<string>) => void;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  private readonly listeners = new Map<string, MessageListener[]>();

  constructor(url: string) {
    void url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: MessageListener): void {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(message: unknown): void {
    const event = new MessageEvent("message", { data: JSON.stringify(message) });
    for (const listener of this.listeners.get("message") ?? []) listener(event);
  }
}

function moduleCard(id: string, status: string, order: number): string {
  return `<li data-module-id="${id}" data-status="${status}" data-order="${order}">
    <span data-role="module-status"></span>
    <span data-role="module-message"></span>
    <span data-role="module-duration"></span>
    <span data-role="module-artifacts"></span>
    <span data-role="module-artifacts-list"></span>
  </li>`;
}

function renderPage(): void {
  document.body.innerHTML = `<main id="run-root" data-run-id="run-1">
    <span id="run-status"></span>
    <button id="run-cancel"></button><button id="run-rerun"></button>
    <div id="run-progress-bar"></div><span id="run-progress-label"></span>
    <ol id="run-module-list">${moduleCard("a", "pending", 0)}${moduleCard("b", "pending", 1)}</ol>
    <select id="log-filter"><option value=""></option><option value="a"></option><option value="b"></option></select>
    <input id="log-search"><button id="log-copy"></button><button id="log-download"></button>
    <div id="log-console"></div>
  </main>`;
}

function snapshot(logs: string[] = ["first"]): unknown {
  return {
    event_type: "snapshot",
    payload: {
      status: "running",
      modules: [
        { module_id: "a", order: 0, status: "passed", logs: [], artifacts: [] },
        { module_id: "b", order: 1, status: "error", logs, artifacts: [] },
      ],
    },
  };
}

function socket(): FakeWebSocket {
  bindRunSocket();
  return FakeWebSocket.instances.at(-1)!;
}

function setScrollMetrics(node: HTMLElement, scrollTop: number): void {
  Object.defineProperties(node, {
    scrollHeight: { configurable: true, value: 1_000 },
    clientHeight: { configurable: true, value: 100 },
    scrollTop: { configurable: true, writable: true, value: scrollTop },
  });
}

beforeEach(() => {
  renderPage();
  resetLog([]);
  setModuleFilter("", { manual: false });
  setSearch("");
  moduleRuntimeState.clear();
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

afterEach(() => vi.unstubAllGlobals());

describe("run socket", () => {
  it("로그 행을 모듈 카드·초점·진행률 입력에서 분리한다", () => {
    socket().emit(snapshot());

    expect(document.querySelector(".log-line")?.hasAttribute("data-module-id")).toBe(false);
    expect(document.querySelectorAll('[data-focus="true"]')).toHaveLength(1);
    expect(document.querySelector('[data-focus="true"]')?.getAttribute("data-module-id")).toBe("b");
    expect(document.getElementById("run-progress-label")?.textContent).toBe("통과 1/2");
  });

  it("실시간 로그도 화면에는 최근 2,000줄만 남기고 저장소 내보내기는 자르지 않는다", () => {
    const lines = Array.from({ length: 1_999 }, (_, index) => `line-${index}`);
    const live = socket();
    live.emit(snapshot(lines));
    live.emit({ event_type: "module_log", payload: { module_id: "b", message: "line-1999" } });
    live.emit({ event_type: "module_log", payload: { module_id: "b", message: "line-2000" } });

    expect(document.querySelectorAll("#log-console .log-line")).toHaveLength(2_000);
    expect(exportText().split("\n")).toHaveLength(2_001);
  });

  it("필터 밖 로그와 초점이 그대로인 모듈 이벤트는 조사 중 스크롤을 건드리지 않는다", () => {
    const live = socket();
    live.emit(snapshot());
    const consoleNode = document.getElementById("log-console")!;
    setScrollMetrics(consoleNode, 200);

    live.emit({ event_type: "module_log", payload: { module_id: "a", message: "filtered out" } });
    expect(consoleNode.scrollTop).toBe(200);

    consoleNode.scrollTop = 250;
    live.emit({
      event_type: "module_started",
      payload: { module: { module_id: "b", status: "error", artifacts: [] } },
    });
    expect(consoleNode.scrollTop).toBe(250);
  });
});
