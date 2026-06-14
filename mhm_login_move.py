from __future__ import annotations

import re

import mhm_login_common as common


def run(page) -> str:
    candidates = [
        page.locator('header a[href="/util/login/login.do"]:visible').first,
        page.locator('a[href="/util/login/login.do"]:visible').first,
        page.get_by_role("link", name=re.compile("로그인|로그인센터")).first,
    ]

    login_link = None
    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=3000):
                login_link = candidate
                break
        except Exception:
            continue

    if login_link is None:
        raise RuntimeError("모바일 로그인 버튼을 찾지 못했습니다.")

    common.click_and_wait_for_navigation(page, login_link, r"/util/login/login\.do$")
    return "로그인 화면 이동 성공"