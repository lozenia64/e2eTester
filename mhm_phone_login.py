from __future__ import annotations

from pathlib import Path
import re

import mhm_login_common as common


def request_sms(page, config: common.LoginConfig, dialog_messages: list[str]) -> str:
    candidates = [
        page.locator('a[href="cellphone-login.do"]:visible').first,
        page.get_by_role("link", name=re.compile("휴대폰|휴대폰인증|휴대폰 로그인")).first,
    ]

    phone_login_link = None
    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=3000):
                phone_login_link = candidate
                break
        except Exception:
            continue

    if phone_login_link is None:
        raise RuntimeError("휴대폰 인증 로그인 버튼을 찾지 못했습니다.")

    common.click_and_wait_for_navigation(page, phone_login_link, r"/util/login/cellphone-login\.do$")
    common.fill_identity(page, config)
    common.request_sms_code(page, dialog_messages, config.timeout_ms)
    return "휴대폰 인증문자 발송 성공"


def submit_otp_and_login(
    page,
    config: common.LoginConfig,
    dialog_messages: list[str],
    screenshot_path: Path,
) -> str:
    otp_code = common.resolve_otp_code(config)
    common.submit_otp(page, otp_code, dialog_messages, config.timeout_ms)
    common.wait_for_login_success(page, config, dialog_messages)
    common.save_screenshot(page, screenshot_path)
    return f"휴대폰 로그인 성공: {page.url}"