"""가설 검증: page.on("dialog") 콜백에서 부른 log() 가 run 로그 싱크에 도달하는가?

Playwright sync_api 의 이벤트 콜백은 dispatcher greenlet 에서 실행된다. greenlet 은
자체 contextvars 컨텍스트를 가지므로 ContextVar 싱크가 보이지 않을 것으로 의심된다.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from app.runner.step_logging import log, pop_sink, push_sink

captured: list[str] = []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    token = push_sink(captured.append)
    try:
        log("[sanity] sink works on main context")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()

            def _handle(dialog):
                log(f"[dialog] {dialog.message}")
                captured.append(f"__handler_ran__ {dialog.message}")
                dialog.accept()

            page.on("dialog", _handle)
            page.goto("data:text/html,<script>alert('defense-alert')</script>")
            page.wait_for_timeout(500)
            browser.close()
    finally:
        pop_sink(token)

    print("captured lines:")
    for line in captured:
        print("  ", line)
    handler_ran = any(line.startswith("__handler_ran__") for line in captured)
    log_arrived = any(line.startswith("[dialog]") for line in captured)
    print(f"\nhandler_ran={handler_ran}  log_reached_sink={log_arrived}")
    assert handler_ran, "dialog 핸들러가 아예 실행되지 않았다 — 전제가 틀렸다"
    print("RESULT:", "로그 유실 확인(가설 참)" if not log_arrived else "로그 정상 도달(가설 거짓)")


if __name__ == "__main__":
    main()
