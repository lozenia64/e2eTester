"""Probe m.hwgeneralins.com main page links and login entry points."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mhm_login_common as common
from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        context = common.launch_persistent_browser_context(playwright, headless=True, slow_mo=0)
        page = context.pages[0] if context.pages else context.new_page()
        common.apply_mobile_device_mode(playwright, page)
        page.goto(common.DEFAULT_BASE_URL, wait_until="domcontentloaded", timeout=30000)
        print("URL:", page.url)
        common.maybe_close_home_popup(page)
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.getAttribute('href'), text: (e.innerText||'').trim().slice(0,80)}))",
        )
        login_links = [l for l in links if l.get("href") and re.search(r"login", l["href"], re.I)]
        print("login links:", login_links[:20])
        for pattern in [r"로그인", r"login", r"MY", r"햄버거", r"menu"]:
            loc = page.get_by_role("link", name=re.compile(pattern, re.I))
            print(f"role=link /{pattern}/ count:", loc.count())
        context.close()


if __name__ == "__main__":
    main()
