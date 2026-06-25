from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.runner.screenshot import capture_screenshot
from app.systems.hom.steps import kakao_login, login_move, main_access, phone_login
from app.systems.hom.steps import login_common as common


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Playwright E2E login script for hwgeneralins.com cellphone authentication"
    )
    parser.add_argument(
        "--env-file",
        default=str(common.DEFAULT_ENV_FILE_PATH),
        help="Path to a dotenv file. Defaults to .env in the current working directory",
    )
    parser.add_argument(
        "--auth-method",
        default="phone",
        choices=["phone", "kakao"],
        help="본인인증 수단. kakao는 인증요청 후 30초 대기(카카오톡 인증) 뒤 인증완료 클릭까지 자동화하며, 미완료 시 최대 3회 재시도합니다.",
    )
    parser.add_argument("--name", default=None, help="Customer name")
    parser.add_argument("--birthdate", default=None, help="Birthdate in YYYYMMDD")
    parser.add_argument("--gender", default=None, help="male/female or 남성/여성")
    parser.add_argument("--residency", default=None, help="domestic/foreign or 내국인/외국인")
    parser.add_argument(
        "--carrier", default=None, help="skt, kt, lgu+, skt_mvno, kt_mvno, lgu_mvno"
    )
    parser.add_argument(
        "--phone-number", default=None, help="Full phone number, for example 01012345678"
    )
    parser.add_argument(
        "--phone-prefix", default=None, help="Optional prefix override, for example 010"
    )
    parser.add_argument(
        "--otp-code",
        default=None,
        help="SMS verification code. If omitted, the script prompts in the terminal.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument(
        "--slow-mo", type=int, default=250, help="Delay between Playwright actions in milliseconds"
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=common.MAX_TIMEOUT_MS,
        help=f"Playwright timeout in milliseconds (max {common.MAX_TIMEOUT_MS})",
    )
    parser.add_argument(
        "--success-stabilization-ms",
        type=int,
        default=common.MAX_TIMEOUT_MS,
        help=f"How long the authenticated page must remain stable before success is declared (max {common.MAX_TIMEOUT_MS})",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the browser open after success in headed mode",
    )
    parser.add_argument(
        "--post-login-fragment",
        default="/my/main.do",
        help="Expected URL fragment after successful login. Use an empty string to accept any non-login page.",
    )
    parser.add_argument(
        "--screenshot",
        default=str(common.DEFAULT_SCREENSHOT_PATH),
        help="Path for the final screenshot artifact",
    )
    return parser


def main() -> int:
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        config = common.build_config(args)
    except ValueError as exc:
        parser.error(str(exc))

    with sync_playwright() as playwright:
        context = common.launch_persistent_browser_context(
            playwright, config.headless, config.slow_mo
        )
        common.grant_browser_permissions(context, config.base_url)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(config.timeout_ms)
        page.set_default_navigation_timeout(config.timeout_ms)
        dialog_messages = common.add_dialog_logger(page)
        cleanup_needed = True

        try:
            main_access.run(page, config)
            login_move.run(page)
            if config.auth_method == "kakao":
                kakao_login.run(page, config, dialog_messages)
            else:
                phone_login.request_sms(page, config, dialog_messages)
                phone_login.submit_otp_and_login(page, config, dialog_messages)
            capture_screenshot(page, config.screenshot_path)
            print(f"[result] Login successful. Current URL: {page.url}")
            if dialog_messages:
                print(f"[result] Dialogs seen: {dialog_messages}")
            if not config.headless:
                common.keep_script_alive_with_browser_open(page, context)
            if config.keep_open and not config.headless:
                input("Login verified. Press Enter to close the browser... ")
            return 0
        finally:
            print(f"테스트 종료 시점 URL: {page.url}")
            if cleanup_needed:
                common.shutdown_browser(page, context)


if __name__ == "__main__":
    raise SystemExit(main())
