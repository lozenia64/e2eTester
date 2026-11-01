"""상황판 브라우저 콘솔 검사 — 수동 실행. CI 게이트가 아니다.

docs/CI.md 가 "라이브 Playwright E2E 는 CI 밖" 을 정책으로 두므로 이 검사는
게이트가 될 수 없다. P1·P2·P3-1 이 세 번 미룬 "콘솔 에러 0" 항목을 실행 가능한
형태로 남기는 것이 목적이다(P3-2 설계 §3.6 — 절반 해소).

사용:
    python3 scripts/run_local.py            # 별 터미널에서 앱 기동
    python3 scripts/check_wall_console.py   # 기본 http://127.0.0.1:2222/wall
    python3 scripts/check_wall_console.py --url http://host:port/wall
"""

from __future__ import annotations

import argparse
import sys

DEFAULT_URL = "http://127.0.0.1:2222/wall"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="상황판 콘솔 에러 검사(수동)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--wait-ms", type=int, default=3000, help="로드 후 관찰 시간")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 가 없습니다: python3 -m pip install -r requirements-dev.txt")
        return 2

    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in {"error", "warning"}
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        response = page.goto(args.url, wait_until="networkidle")
        if response is None or response.status != 200:
            status = response.status if response else "no response"
            print(f"실패: {args.url} 이 200 이 아닙니다 ({status})")
            browser.close()
            return 1
        page.wait_for_timeout(args.wait_ms)
        has_scrollbar = page.evaluate("document.documentElement.scrollHeight > window.innerHeight")
        browser.close()

    if has_scrollbar:
        problems.append("넌스크롤 위반: 1920x1080 에서 스크롤이 생겼습니다.")

    if problems:
        print(f"상황판 검사 실패 {len(problems)}건:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("상황판 검사 통과 (콘솔 에러 0 · 넌스크롤)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
