"""모듈 종료 시 스크린샷을 찍는 시스템 공용 로직.

각 시스템/단계가 제각기 스크린샷을 찍던 중복 구현(HOM/MHM/접속 점검)을 한곳으로 모은다.
공용 실행 엔진(`BaseWorkflowExecutor.execute_step`)이 모든 모듈의 종료 시점(성공·실패 공통)에
이 함수를 호출하므로, 개별 단계 함수는 더 이상 스크린샷을 직접 찍지 않는다.

Playwright `Page` 하나에만 의존하는 시스템 무관 코드이며, 어떤 예외도 밖으로 전파하지 않는다
(스크린샷 실패가 단계의 성공/실패 판정을 가리면 안 되기 때문).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Final

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

SCREENSHOT_TIMEOUT_MS: Final[int] = 20000
SCREENSHOT_RETRY_TIMEOUT_MS: Final[int] = 5000
SCREENSHOT_PRE_CAPTURE_WAIT_MS: Final[int] = 3000

# 연수원(SLS) self-defender 는 CDP 세션·DOM 주입을 무결성 위반으로 보고 로그인 AJAX 를 차단한다.
SELF_DEFENDER_HOST_FRAGMENTS: Final[tuple[str, ...]] = ("sls.hwgeneralins.com",)


def _is_self_defender_page(page: Page) -> bool:
    try:
        url = page.url
    except Exception:
        return False
    return any(fragment in url for fragment in SELF_DEFENDER_HOST_FRAGMENTS)


def _scroll_to_top(page: Page) -> None:
    page.evaluate("() => { window.scrollTo({ top: 0, behavior: 'instant' }); }")
    page.wait_for_timeout(300)


def _apply_font_fallback(page: Page) -> None:
    """한글 폰트 렌더링 타임아웃을 피하기 위해 캡처 직전 시스템 폰트로 강제 교체한다."""
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
    """모듈 종료 시 페이지 스크린샷을 ``output_path`` 에 저장한다.

    표준 캡처 → 폰트 폴백 재시도 → CDP 폴백 순으로 시도하며, 모든 단계가 실패해도
    경고만 출력하고 정상 반환한다(예외를 절대 밖으로 던지지 않는다).
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[warn] Failed to prepare screenshot directory: {exc}")
        return

    try:
        _scroll_to_top(page)
    except Exception as exc:
        print(f"[warn] Failed to scroll before screenshot: {exc}")

    try:
        print(f"[wait] Pre-screenshot settle delay ({SCREENSHOT_PRE_CAPTURE_WAIT_MS} ms)")
        settle_ms = 500 if _is_self_defender_page(page) else SCREENSHOT_PRE_CAPTURE_WAIT_MS
        page.wait_for_timeout(settle_ms)
    except Exception as exc:
        print(f"[warn] Pre-screenshot settle delay failed: {exc}")

    try:
        _capture_with_playwright(page, output_path, SCREENSHOT_TIMEOUT_MS)
        print(f"[artifact] Screenshot saved to {output_path}")
        return
    except PlaywrightTimeoutError as exc:
        print(f"[warn] Standard screenshot timed out, retry with font fallback: {exc}")
    except Exception as exc:
        print(f"[warn] Standard screenshot failed, retry with fallbacks: {exc}")

    if not _is_self_defender_page(page):
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
            return
        except Exception as exc:
            print(f"[warn] Failed to save screenshot to {output_path}: {exc}")
    else:
        print(
            "[warn] Skipping font-fallback/CDP screenshot on self-defender host "
            "(would poison subsequent login AJAX)"
        )
