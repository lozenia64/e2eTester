from __future__ import annotations

import base64
from pathlib import Path
from typing import Final

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


# 모든 시스템(HOM/MHM/접속점검)이 공유하는 모듈 종료 스크린샷 캡처 설정.
SCREENSHOT_TIMEOUT_MS: Final[int] = 20000
SCREENSHOT_RETRY_TIMEOUT_MS: Final[int] = 5000
SCREENSHOT_PRE_CAPTURE_WAIT_MS: Final[int] = 2000


def _scroll_to_page_top(page: Page) -> None:
    print("[step] Scroll to page top")
    page.evaluate("() => { window.scrollTo({ top: 0, behavior: 'instant' }); }")


def _apply_font_fallback(page: Page) -> None:
    page.evaluate(
        """
        () => {
            if (document.getElementById('e2e-screenshot-font-fallback')) {
                return;
            }
            const style = document.createElement('style');
            style.id = 'e2e-screenshot-font-fallback';
            style.textContent = `
                *, *::before, *::after {
                    font-family: Arial, sans-serif !important;
                }
            `;
            document.head.appendChild(style);
        }
        """
    )
    page.wait_for_timeout(150)


def _capture_with_playwright(page: Page, output_path: Path, timeout_ms: int) -> None:
    page.screenshot(path=str(output_path), full_page=False, timeout=timeout_ms)


def _capture_with_cdp(page: Page, output_path: Path) -> None:
    session = page.context.new_cdp_session(page)
    result = session.send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    output_path.write_bytes(base64.b64decode(result["data"]))


def capture_screenshot(page: Page, output_path: Path) -> None:
    """현재 페이지 상태를 ``output_path`` 에 저장한다(시스템 공통).

    표준 Playwright 캡처를 먼저 시도하고, 실패 시 폰트 폴백 재시도 → CDP 캡처 순으로
    단계적으로 폴백한다. 모든 경로에서 예외를 삼키므로 본 함수는 호출자에게 예외를
    전파하지 않는다(스크린샷 실패가 점검 결과를 바꾸지 않도록).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _scroll_to_page_top(page)
    except Exception as exc:
        print(f"[warn] Failed to scroll before screenshot: {exc}")

    try:
        page.wait_for_timeout(SCREENSHOT_PRE_CAPTURE_WAIT_MS)
    except Exception as exc:
        print(f"[warn] Pre-screenshot settle delay skipped: {exc}")

    try:
        _capture_with_playwright(page, output_path, SCREENSHOT_TIMEOUT_MS)
        print(f"[artifact] Screenshot saved to {output_path}")
        return
    except PlaywrightTimeoutError as exc:
        print(f"[warn] Standard screenshot timed out, retry with font fallback: {exc}")
    except Exception as exc:
        print(f"[warn] Standard screenshot failed, retry with fallbacks: {exc}")

    try:
        _apply_font_fallback(page)
        _capture_with_playwright(page, output_path, SCREENSHOT_RETRY_TIMEOUT_MS)
        print(f"[artifact] Screenshot saved to {output_path} (font fallback)")
        return
    except Exception as exc:
        print(f"[warn] Font-fallback screenshot failed, trying CDP capture: {exc}")

    try:
        _capture_with_cdp(page, output_path)
        print(f"[artifact] Screenshot saved to {output_path} (CDP fallback)")
    except Exception as exc:
        print(f"[warn] Failed to save screenshot to {output_path}: {exc}")
