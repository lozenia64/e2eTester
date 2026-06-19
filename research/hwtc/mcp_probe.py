#!/usr/bin/env python3
"""Playwright MCP HTTP 클라이언트 — 로그인 후 페이지 스냅샷/셀렉터 수집용."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

import urllib.request

MCP_URL = os.environ.get("PLAYWRIGHT_MCP_URL", "http://localhost:8931/mcp")
OUTPUT_DIR = Path(__file__).resolve().parent / "hwtc"


class McpHttpClient:
    def __init__(self, url: str) -> None:
        self.url = url
        self.session_id: str | None = None
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            if not self.session_id:
                self.session_id = resp.headers.get("Mcp-Session-Id")
            raw = resp.read().decode("utf-8")
        if not raw.strip():
            return {}
        for line in raw.splitlines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if "error" in data:
                    raise RuntimeError(data["error"])
                return data
        raise RuntimeError(f"Unexpected MCP response: {raw[:500]}")

    def initialize(self) -> None:
        self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "hwtc-probe", "version": "1.0"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        content = result.get("result", {}).get("content", [])
        texts = [block.get("text", "") for block in content if block.get("type") == "text"]
        return "\n".join(texts)


def main() -> int:
    user_id = os.environ.get("HWTC_USER_ID", "").strip()
    password = os.environ.get("HWTC_PASSWORD", "").strip()
    manual_wait = os.environ.get("HWTC_MANUAL_LOGIN", "").strip() in {"1", "true", "yes"}
    if not manual_wait and (not user_id or not password):
        print(
            "HWTC_USER_ID, HWTC_PASSWORD 환경변수를 설정하거나\n"
            "HWTC_MANUAL_LOGIN=1 로 MCP Chrome 창에서 직접 로그인하세요.\n"
            "예: HWTC_USER_ID=... HWTC_PASSWORD=... python3 research/hwtc/mcp_probe.py",
            file=sys.stderr,
        )
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = McpHttpClient(MCP_URL)
    client.initialize()

    print("[mcp] navigate login")
    print(client.call_tool("browser_navigate", {"url": "https://sls.hwgeneralins.com/login/loginForm.do"}))

    if manual_wait:
        print("[mcp] Chrome 창에서 직접 로그인해 주세요 (최대 180초)...")
        wait_code = """
async (page) => {
  const loginPath = 'login/loginForm';
  try {
    const close = page.locator('button:has-text("닫기")').first();
    if (await close.isVisible({ timeout: 2000 })) await close.click();
  } catch (e) {}
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    if (!page.url().includes(loginPath)) {
      return { url: page.url(), title: await page.title() };
    }
    await page.waitForTimeout(1000);
  }
  throw new Error('로그인 대기 시간 초과: ' + page.url());
}
"""
        print(client.call_tool("browser_run_code_unsafe", {"code": wait_code}))
    else:
        print("[mcp] login")
        login_code = f"""
async (page) => {{
  await page.locator('#userId').fill({user_id!r});
  await page.locator('#password').fill({password!r});
  await page.locator('button.btn.org.login').click();
  try {{
    await page.locator('.wrap-loading').waitFor({{ state: 'hidden', timeout: 30000 }});
  }} catch (e) {{}}
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {{
    if (!page.url().includes('login/loginForm')) {{
      return {{ url: page.url(), title: await page.title() }};
    }}
    await page.waitForTimeout(500);
  }}
  throw new Error('로그인 실패: ' + page.url());
}}
"""
        print(client.call_tool("browser_run_code_unsafe", {"code": login_code}))

    print("[mcp] snapshot")
    snapshot = client.call_tool("browser_snapshot", {"filename": str(OUTPUT_DIR / "post_login_snapshot.md")})
    print(snapshot[:3000])

    print("[mcp] collect DOM selectors")
    dom_code = """
async (page) => {
  return await page.evaluate(() => {
    const pick = (el) => ({
      tag: el.tagName,
      id: el.id || null,
      name: el.getAttribute('name'),
      className: el.className || null,
      text: (el.innerText || el.value || '').trim().slice(0, 80),
      href: el.href || null,
      role: el.getAttribute('role'),
    });
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const links = [...document.querySelectorAll('a')].filter(visible).slice(0, 40).map(pick);
    const buttons = [...document.querySelectorAll('button, input[type=button], input[type=submit]')]
      .filter(visible).slice(0, 40).map(pick);
    const nav = [...document.querySelectorAll('nav a, header a, .gnb a, #gnb a, .menu a')]
      .filter(visible).slice(0, 40).map(pick);
    const inputs = [...document.querySelectorAll('input, select, textarea')]
      .filter(visible).slice(0, 30).map(pick);
    return { url: location.href, title: document.title, nav, links, buttons, inputs };
  });
}
"""
    dom_result = client.call_tool("browser_run_code_unsafe", {"code": dom_code})
    out_path = OUTPUT_DIR / "post_login_selectors.json"
    # Extract JSON from MCP text if wrapped
    match = re.search(r"\{.*\}", dom_result, re.DOTALL)
    if match:
        parsed = json.loads(match.group())
        out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {out_path}")
        print(json.dumps(parsed, ensure_ascii=False, indent=2)[:4000])
    else:
        out_path.write_text(dom_result, encoding="utf-8")
        print(dom_result[:4000])

    screenshot = client.call_tool(
        "browser_take_screenshot",
        {"filename": str(OUTPUT_DIR / "post_login.png"), "fullPage": True},
    )
    print(screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
