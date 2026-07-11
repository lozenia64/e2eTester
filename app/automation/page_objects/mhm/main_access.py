from __future__ import annotations

from . import login_common as common

MAIN_ACCESS_TIMEOUT_MS = 20000


def run(page, config: common.LoginConfig) -> str:
    common.ensure_mobile_mode_before_navigation(page)
    print(
        f"[wait] Start direct navigation: {config.base_url} ({MAIN_ACCESS_TIMEOUT_MS} ms main access)"
    )
    page.goto(config.base_url, wait_until="domcontentloaded", timeout=MAIN_ACCESS_TIMEOUT_MS)
    print(f"[wait] End direct navigation: {config.base_url} -> {page.url}")
    common.maybe_close_home_popup(page)
    return "메인화면 접속 성공"
