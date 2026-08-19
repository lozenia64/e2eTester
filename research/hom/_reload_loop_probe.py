"""대표홈페이지 EVFW/OhRep 재진입(reload) 루프 재현·계측 probe.

production 과 동일한 launch 옵션으로 띄우고, 20초간 navigation/console/dialog/
evfw 요청을 기록해 '왜 reload 하는가' 의 증거를 모은다.
사용: python -m research.hom._reload_loop_probe [--no-guard] [--headless] [--label X]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from playwright.sync_api import sync_playwright

from app.automation.page_objects.hom import login_common as common
from app.systems.access_common.browser import CONSOLE_SERIALIZATION_GUARD_SCRIPT

URL = "https://www.hwgeneralins.com"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-guard", action="store_true", help="console serialization guard 미적용")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--observe", type=int, default=20, help="관찰 시간(초)")
    ap.add_argument("--profile", default=None, help="user_data_dir 오버라이드")
    ap.add_argument("--label", default="prod")
    args = ap.parse_args()

    events: list[dict] = []
    t0 = time.monotonic()

    def rec(kind: str, **kw) -> None:
        events.append({"t": round(time.monotonic() - t0, 3), "kind": kind, **kw})

    with sync_playwright() as pw:
        from pathlib import Path

        udd = Path(args.profile).expanduser() if args.profile else None
        # guard 적용 여부만 다르게 하려면 launch 후 add_init_script 를 우리가 제어해야 하므로
        # production 함수를 그대로 쓰고, --no-guard 일 때는 guard 를 안 넣은 동등 launch 를 직접 한다.
        if args.no_guard:
            udd = udd or common.resolve_user_data_dir()
            udd.mkdir(parents=True, exist_ok=True)
            disabled = ",".join(
                common.PLAYWRIGHT_DEFAULT_DISABLED_FEATURES + common.LOCAL_NETWORK_DISABLED_FEATURES
            )
            ctx = pw.chromium.launch_persistent_context(
                str(udd),
                channel="chrome",
                headless=args.headless,
                slow_mo=0,
                viewport=common.PC_VIEWPORT,
                locale="ko-KR",
                ignore_default_args=[
                    "--enable-automation",
                    "--disable-extensions",
                    "--disable-component-extensions-with-background-pages",
                ],
                args=[
                    f"--disable-features={disabled}",
                    common.DISABLE_AUTOMATION_CONTROLLED_FLAG,
                ],
            )
        else:
            ctx = common.launch_persistent_browser_context(pw, args.headless, 0, udd)

        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.on("framenavigated", lambda f: rec("nav", url=f.url) if f == page.main_frame else None)
        page.on("console", lambda m: rec("console", type=m.type, text=m.text[:200]))
        page.on(
            "dialog",
            lambda d: (rec("dialog", type=d.type, message=d.message), d.accept()),
        )
        page.on("pageerror", lambda e: rec("pageerror", text=str(e)[:200]))
        page.on(
            "request",
            lambda r: rec("req_evfw", url=r.url[:160], rtype=r.resource_type)
            if "evfw" in r.url
            else None,
        )
        page.on(
            "response",
            lambda r: rec("resp_doc", url=r.url[:160], status=r.status)
            if r.request.resource_type == "document"
            else None,
        )

        rec("goto_start", url=URL)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            rec("goto_end", url=page.url)
        except Exception as exc:
            rec("goto_error", text=str(exc)[:300])

        deadline = time.monotonic() + args.observe
        while time.monotonic() < deadline:
            try:
                snap = page.evaluate(
                    """() => ({
                        bodyChildren: document.body ? document.body.children.length : -1,
                        loginLinks: document.querySelectorAll('a[href="/util/login/login.do"]').length,
                        hasOhRep: Boolean(window.OhRep),
                        webdriver: navigator.webdriver,
                        ua: navigator.userAgent,
                        cookieLen: document.cookie.length,
                        cookie: document.cookie.slice(0, 300),
                        ss: Object.keys(sessionStorage || {}),
                        ls: Object.keys(localStorage || {}),
                    })"""
                )
                rec("snap", **snap)
            except Exception as exc:
                rec("snap_error", text=str(exc)[:160])
            page.wait_for_timeout(2000)

        ctx.close()

    navs = [e for e in events if e["kind"] == "nav"]
    out = {
        "label": args.label,
        "guard": not args.no_guard,
        "headless": args.headless,
        "nav_count": len(navs),
        "events": events,
    }
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
