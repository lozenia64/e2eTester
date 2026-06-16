from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


PREFERRED_BROWSER_CHANNEL: Final[str] = "chrome"
MAX_TIMEOUT_MS: Final[int] = 20000
MAIN_ACCESS_TIMEOUT_MS: Final[int] = 20000
DEFAULT_USER_DATA_ROOT: Final[Path] = Path.home() / ".e2etester"
MOBILE_DEVICE_NAME: Final[str] = "iPhone 14 Pro"

# Playwright 가 Chrome 실행 시 끄는 기본 feature 들. 로컬 네트워크 차단 해제를 위해
# --disable-features 를 직접 넘기면 Chromium 은 마지막 하나만 인식하므로, Playwright
# 기본값을 잃지 않도록 함께 포함해서 넘긴다. (mhm/login_common 과 동일한 목록)
PLAYWRIGHT_DEFAULT_DISABLED_FEATURES: Final[tuple[str, ...]] = (
    "AvoidUnnecessaryBeforeUnloadCheckSync",
    "BoundaryEventDispatchTracksNodeRemoval",
    "DestroyProfileOnBrowserClose",
    "DialMediaRouteProvider",
    "GlobalMediaControls",
    "HttpsUpgrades",
    "LensOverlay",
    "MediaRouter",
    "PaintHolding",
    "ThirdPartyStoragePartitioning",
    "Translate",
    "AutoDeElevate",
    "RenderDocument",
    "OptimizationHints",
    "msForceBrowserSignIn",
    "msEdgeUpdateLaunchServicesPreferredVersion",
)

# 한화손보 계열 사이트(fp/sls/chbot)는 로컬 보안 에이전트와 통신하므로, 일반 브라우저에서
# 사용자가 '허용'한 것과 동일하게 공개 사이트 -> 로컬 네트워크 요청 차단 기능을 꺼 준다.
# (모르는 feature 이름은 Chrome 이 무시하므로 외부 사이트에서도 안전하다.)
LOCAL_NETWORK_DISABLED_FEATURES: Final[tuple[str, ...]] = (
    "LocalNetworkAccessChecks",
    "BlockInsecurePrivateNetworkRequests",
    "PrivateNetworkAccessSendPreflights",
    "PrivateNetworkAccessRespectPreflightResults",
    "PrivateNetworkAccessForNavigations",
    "PrivateNetworkAccessPermissionPrompt",
)


def normalize_base_url(raw: str | None, default: str) -> str:
    candidate = (raw or default).strip()
    if not candidate:
        candidate = default
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        candidate = f"https://{candidate.lstrip('/')}"
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc or parsed.path.split("/")[0]
    path = ""
    if parsed.netloc:
        path = parsed.path
    elif "/" in parsed.path:
        path = "/" + parsed.path.split("/", 1)[1]
    return f"{scheme}://{netloc}{path}".rstrip("/")


def origin_of(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_user_data_dir(profile_name: str) -> Path:
    override = os.environ.get("E2E_USER_DATA_DIR")
    if override:
        target = Path(override).expanduser() / profile_name
    else:
        target = DEFAULT_USER_DATA_ROOT / profile_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def launch_persistent_browser_context(playwright, headless: bool, slow_mo: int, user_data_dir: Path):
    user_data_dir.mkdir(parents=True, exist_ok=True)
    disabled_features = ",".join(
        PLAYWRIGHT_DEFAULT_DISABLED_FEATURES + LOCAL_NETWORK_DISABLED_FEATURES
    )
    common_args = {
        "headless": headless,
        "slow_mo": slow_mo,
        "no_viewport": True,
        "locale": "ko-KR",
        "ignore_default_args": [
            "--enable-automation",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
        ],
        "args": [f"--disable-features={disabled_features}"],
    }
    try:
        print(f"[step] Launch persistent browser context: {PREFERRED_BROWSER_CHANNEL} ({user_data_dir})")
        return playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=PREFERRED_BROWSER_CHANNEL,
            **common_args,
        )
    except Exception as exc:
        print(f"[warn] Falling back to bundled Chromium persistent context: {exc}")
        return playwright.chromium.launch_persistent_context(str(user_data_dir), **common_args)


def apply_mobile_device_mode(playwright, page: Page) -> None:
    """모바일 시스템(CHBOT) 접속 전에 Chrome 모바일 디바이스 모드를 켠다."""
    device = playwright.devices.get(MOBILE_DEVICE_NAME)
    if device is None:
        raise RuntimeError(f"Playwright 디바이스 프로필을 찾지 못했습니다: {MOBILE_DEVICE_NAME}")

    viewport = device["viewport"]
    width = viewport["width"]
    height = viewport["height"]
    device_scale_factor = device.get("device_scale_factor", 1)
    user_agent = device["user_agent"]
    is_mobile = device.get("is_mobile", True)
    has_touch = device.get("has_touch", True)

    print(
        f"[step] Enable mobile device mode: {MOBILE_DEVICE_NAME} "
        f"({width}x{height}, scale={device_scale_factor}) before site navigation"
    )
    page.set_viewport_size({"width": width, "height": height})
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": device_scale_factor,
                "mobile": is_mobile,
            },
        )
        cdp.send("Emulation.setUserAgentOverride", {"userAgent": user_agent})
        if has_touch:
            cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        print("[step] Mobile device emulation applied (CDP)")
    except Exception as exc:
        print(f"[warn] CDP mobile emulation fallback (viewport only): {exc}")


def grant_browser_permissions(context, base_url: str) -> None:
    origin = origin_of(base_url)
    try:
        context.grant_permissions(["local-network-access"], origin=origin)
        print(f"[step] Granted browser permission: local-network-access for {origin}")
    except Exception as exc:
        print(f"[warn] Failed to pre-grant local-network-access permission: {exc}")


def add_dialog_logger(page: Page) -> list[str]:
    messages: list[str] = []

    def _handle(dialog) -> None:
        messages.append(dialog.message)
        print(f"[dialog] {dialog.message}")
        dialog.accept()

    page.on("dialog", _handle)
    return messages


def maybe_close_popup(page: Page) -> None:
    """메인화면 진입 직후 흔히 뜨는 '닫기' 형태의 안내 팝업을 정리한다(있으면)."""
    close_button = page.get_by_role("button", name=re.compile("닫기|오늘 ?하루|그만 ?보기"))
    try:
        if close_button.first.is_visible(timeout=3000):
            print("[step] Close landing popup")
            close_button.first.click()
    except PlaywrightTimeoutError:
        return
    except Exception as exc:
        print(f"[warn] Landing popup close skipped: {exc}")


def shutdown_browser(page: Page, context) -> None:
    print("[step] Closing page")
    try:
        page.close(run_before_unload=False)
    except Exception as exc:
        print(f"[warn] Failed to close page cleanly: {exc}")
    # persistent context 는 별도 browser 객체가 없으며, context 를 닫으면 브라우저도 종료된다.
    print("[step] Closing browser context")
    try:
        context.close()
    except Exception as exc:
        print(f"[warn] Failed to close browser context cleanly: {exc}")
