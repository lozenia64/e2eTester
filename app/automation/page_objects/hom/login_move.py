from __future__ import annotations

import re

from . import login_common as common


def run(page) -> str:
    # EVFW 방어 스크립트가 강제 새로고침을 반복하는 동안은 DOM 이 통째로 비어 있어
    # 어떤 후보도 보이지 않는다. 먼저 문서가 정착할 때까지 기다린 뒤 탐색한다.
    common.wait_for_document_settled(page)
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
        raise RuntimeError(f"상단 로그인 버튼을 찾지 못했습니다. (현재 URL {page.url})")

    common.click_and_wait_for_navigation(page, login_link, r"/util/login/login\.do$")
    return "로그인 화면 이동 성공"
