"""hom.main.access → hom.login 운영 시퀀스를 그대로 재생해 reload 루프를 재현한다.

production 과의 유일한 차이: dialog 를 **전부** 기록한다(운영 add_dialog_logger 는
'개발자도구' alert 을 조용히 accept 하므로 로그에 남지 않는다).
사용: python -m research.hom._replay_login_move [--slow-mo 250] [--no-screenshot] [--no-guard]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from playwright.sync_api import sync_playwright

from app.automation.page_objects.hom import login_common as common
from app.automation.page_objects.hom import login_move

URL = "https://www.hwgeneralins.com"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slow-mo", type=int, default=250)
    ap.add_argument("--no-screenshot", action="store_true")
    ap.add_argument("--no-guard", action="store_true")
    ap.add_argument("--label", default="replay")
    args = ap.parse_args()

    events: list[dict] = []
    t0 = time.monotonic()

    def rec(kind: str, **kw) -> None:
        events.append({"t": round(time.monotonic() - t0, 3), "kind": kind, **kw})

    with sync_playwright() as pw:
        if args.no_guard:
            import app.systems.access_common.browser as browser_mod

            browser_mod.CONSOLE_SERIALIZATION_GUARD_SCRIPT = "(() => {})();"
            common.add_console_serialization_guard = lambda ctx: None  # type: ignore[assignment]
        ctx = common.launch_persistent_browser_context(pw, False, args.slow_mo)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        common.grant_browser_permissions(ctx, URL)
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(15000)

        page.on("framenavigated", lambda f: rec("nav", url=f.url) if f == page.main_frame else None)
        page.on(
            "dialog",
            lambda d: (rec("DIALOG", type=d.type, message=d.message), d.accept()),
        )
        page.on("console", lambda m: rec("console", type=m.type, text=m.text[:120])
                if m.type not in ("clear",) else None)

        rec("access_goto_start")
        page.goto(URL, wait_until="load", timeout=20000)
        rec("access_goto_end", url=page.url)
        page.wait_for_timeout(3000)
        if not args.no_screenshot:
            page.screenshot(path="research/hom/_replay_access.png", full_page=False)
            rec("access_screenshot")

        rec("login_move_start")
        try:
            rec("login_move_ok", result=login_move.run(page))
        except Exception as exc:
            rec("login_move_error", text=str(exc)[:2000])
        rec("end", url=page.url)
        ctx.close()

    navs = [e for e in events if e["kind"] == "nav"]
    sys.stdout.reconfigure(encoding="utf-8")
    print(
        json.dumps(
            {
                "label": args.label,
                "slow_mo": args.slow_mo,
                "guard": not args.no_guard,
                "screenshot": not args.no_screenshot,
                "nav_count": len(navs),
                "dialogs": [e for e in events if e["kind"] == "DIALOG"],
                "events": events,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
