import { afterEach, expect, it, vi } from "vitest";
import { closeSuiteRunProgressSocket, refreshSuiteRunProgress, syncSuiteRunProgressSocket } from "./socket";
import { suiteRunCache } from "./steps";

afterEach(() => {
  closeSuiteRunProgressSocket();
  vi.unstubAllGlobals();
  suiteRunCache.clear();
});

it("WS 스냅샷 이후 도착한 HTTP 응답은 스냅샷을 되돌리지 않는다", async () => {
  const replies: Array<(response: Response) => void> = [];
  vi.stubGlobal("fetch", () => new Promise<Response>((resolve) => replies.push(resolve)));
  let socket: EventTarget;
  class Socket extends EventTarget {
    constructor() { super(); socket = this; }
    close(): void { /* 실제 네트워크 연결 없음 */ }
  }
  vi.stubGlobal("WebSocket", Socket);
  syncSuiteRunProgressSocket({ status: "RUNNING", active_run_id: "r2" });
  const pending = refreshSuiteRunProgress("r2");
  socket!.dispatchEvent(new MessageEvent("message", { data: JSON.stringify({
    event_type: "snapshot", payload: { run_id: "r2", status: "PASSED", modules: [] },
  }) }));
  for (const reply of replies) reply(new Response(JSON.stringify({ run_id: "r2", status: "RUNNING", modules: [] })));
  await pending;
  expect(suiteRunCache.get("r2")).toMatchObject({ status: "PASSED" });
});

it("늦게 도착한 이전 HTTP 응답이 최신 완료 상태를 되돌리지 않는다", async () => {
  const replies: Array<(response: Response) => void> = [];
  vi.stubGlobal("fetch", () => new Promise<Response>((resolve) => replies.push(resolve)));
  const older = refreshSuiteRunProgress("r1");
  const newer = refreshSuiteRunProgress("r1");
  replies[1]!(new Response(JSON.stringify({ run_id: "r1", status: "PASSED", modules: [] })));
  await newer;
  replies[0]!(new Response(JSON.stringify({ run_id: "r1", status: "RUNNING", modules: [] })));
  await older;
  expect(suiteRunCache.get("r1")).toMatchObject({ status: "PASSED" });
});
