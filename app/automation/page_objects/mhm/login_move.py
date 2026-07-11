from __future__ import annotations

from . import login_common as common


def run(page) -> str:
    common.maybe_close_pre_login_bottom_popup(page)

    candidates = [
        page.locator('main button.btn:has-text("로그인"):visible').first,
        page.get_by_role("button", name="로그인", exact=True).first,
    ]

    login_button = None
    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=3000):
                login_button = candidate
                break
        except Exception:
            continue

    if login_button is None:
        raise RuntimeError("모바일 로그인 버튼을 찾지 못했습니다.")

    common.click_and_wait_for_navigation(page, login_button, r"/lin/fid/LginTyp")
    return "로그인 화면 이동 성공"
