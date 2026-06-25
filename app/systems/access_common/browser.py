from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.core.settings import get_settings

PREFERRED_BROWSER_CHANNEL: Final[str] = "chrome"
PC_VIEWPORT: Final[dict[str, int]] = {"width": 1339, "height": 1038}
MOBILE_VIEWPORT: Final[dict[str, int]] = {"width": 390, "height": 844}
MAX_TIMEOUT_MS: Final[int] = 20000
MAIN_ACCESS_TIMEOUT_MS: Final[int] = 20000
DEFAULT_USER_DATA_ROOT: Final[Path] = Path.home() / ".e2etester"
MOBILE_DEVICE_NAME: Final[str] = "iPhone 14 Pro"
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

# Playwright MCP(@playwright/mcp) persistent profile root — %LOCALAPPDATA%/ms-playwright-mcp
PLAYWRIGHT_MCP_PROFILES_ROOT: Final[Path] = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright-mcp"
)
PLAYWRIGHT_MCP_DISABLE_BLINK_FEATURE: Final[str] = "--disable-blink-features=AutomationControlled"

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

# 연수원(SLS) self-defender 가 Playwright CDP 연결을 감지하면 alert("개발자 도구…")를 띄운다.
# window.alert 패치(init script)는 무결성 검사에 걸려 로그인 AJAX 가 차단되므로 쓰지 않는다.
# → add_dialog_logger 에서만 로그·dialog_messages 수집을 생략하고 accept() 한다.
DEVTOOLS_BLOCK_ALERT_SUBSTRING: Final[str] = "개발자 도구"


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
    override = get_settings().user_data_dir or os.environ.get("E2E_USER_DATA_DIR")
    if override:
        target = Path(override).expanduser() / profile_name
    else:
        target = DEFAULT_USER_DATA_ROOT / profile_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_workspace_dir() -> Path:
    """Playwright MCP 가 프로필 해시에 쓰는 workspace 경로(cwd)."""
    override = get_settings().workspace_dir or os.environ.get("E2E_WORKSPACE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT.resolve()


def resolve_playwright_mcp_user_data_dir(
    *,
    channel: str = PREFERRED_BROWSER_CHANNEL,
    workspace_dir: Path | None = None,
) -> Path:
    """Cursor Playwright MCP 와 동일한 persistent profile 경로.

    ms-playwright-mcp/mcp-{channel}-{sha256(workspace)[:7]}
    """
    override = get_settings().playwright_mcp_profile_dir or os.environ.get(
        "E2E_PLAYWRIGHT_MCP_PROFILE_DIR"
    )
    if override:
        target = Path(override).expanduser()
    else:
        workspace = workspace_dir or resolve_workspace_dir()
        token = hashlib.sha256(str(workspace).encode()).hexdigest()[:7]
        target = PLAYWRIGHT_MCP_PROFILES_ROOT / f"mcp-{channel}-{token}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def is_devtools_block_dialog(message: str) -> bool:
    return DEVTOOLS_BLOCK_ALERT_SUBSTRING in message


def launch_legacy_persistent_browser_context(
    playwright,
    headless: bool,
    slow_mo: int,
    user_data_dir: Path,
):
    """설치형 보안프로그램용 영속 Chrome 프로파일 launch (HOM·FP·HRP)."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    disabled_features = ",".join(
        PLAYWRIGHT_DEFAULT_DISABLED_FEATURES + LOCAL_NETWORK_DISABLED_FEATURES
    )
    common_args = {
        "headless": headless,
        "slow_mo": slow_mo,
        "viewport": PC_VIEWPORT,
        "locale": "ko-KR",
        "ignore_default_args": [
            "--enable-automation",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
        ],
        "args": [f"--disable-features={disabled_features}"],
    }
    try:
        print(
            f"[step] Launch persistent browser context: {PREFERRED_BROWSER_CHANNEL} ({user_data_dir})"
        )
        return playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=PREFERRED_BROWSER_CHANNEL,
            **common_args,
        )
    except Exception as exc:
        print(f"[warn] Falling back to bundled Chromium persistent context: {exc}")
        return playwright.chromium.launch_persistent_context(str(user_data_dir), **common_args)


def launch_persistent_browser_context(
    playwright,
    headless: bool,
    slow_mo: int,
    user_data_dir: Path,
):
    """``launch_legacy_persistent_browser_context`` 별칭 (하위 호환)."""
    return launch_legacy_persistent_browser_context(playwright, headless, slow_mo, user_data_dir)


# 설치형 보안프로그램이 필요한 access 시스템 — 시스템별 ``~/.e2etester/{code}-chrome-profile``
LEGACY_BROWSER_ACCESS_SYSTEMS: Final[frozenset[str]] = frozenset({"fp", "hrp"})


def launch_standard_browser_context(playwright, headless: bool):
    """Cursor Playwright MCP 프로필·launch (HWTC·CHBOT 등)."""
    return launch_playwright_mcp_browser_context(
        playwright,
        headless,
        resolve_playwright_mcp_user_data_dir(),
    )


def launch_playwright_mcp_browser_context(playwright, headless: bool, user_data_dir: Path):
    """Playwright MCP(createPersistentBrowser) 와 동일한 launch 옵션.

    - ignore --disable-extensions (확장 프로그램 허용)
    - --disable-blink-features=AutomationControlled
    - viewport: PC_VIEWPORT (headed·headless 동일)
    - grant_permissions·커스텀 --disable-features 없음
    """
    user_data_dir.mkdir(parents=True, exist_ok=True)
    common_args = {
        "headless": headless,
        "viewport": PC_VIEWPORT,
        "ignore_default_args": ["--disable-extensions"],
        "args": [PLAYWRIGHT_MCP_DISABLE_BLINK_FEATURE],
    }
    try:
        print(
            f"[step] Launch Playwright MCP-style browser: {PREFERRED_BROWSER_CHANNEL} "
            f"({user_data_dir})"
        )
        return playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=PREFERRED_BROWSER_CHANNEL,
            **common_args,
        )
    except Exception as exc:
        message = str(exc)
        if "ProcessSingleton" in message or "exitCode=21" in message:
            raise RuntimeError(
                "Playwright MCP Chrome 프로필이 이미 사용 중입니다. "
                "Cursor Playwright MCP 브라우저를 닫거나 "
                "E2E_PLAYWRIGHT_MCP_PROFILE_DIR 로 별도 프로필을 지정하세요."
            ) from exc
        print(f"[warn] Falling back to bundled Chromium (MCP-style): {exc}")
        return playwright.chromium.launch_persistent_context(str(user_data_dir), **common_args)


def apply_mobile_device_mode(playwright, page: Page) -> None:
    """모바일 시스템(CHBOT) 접속 전에 Chrome 모바일 디바이스 모드를 켠다."""
    device = playwright.devices.get(MOBILE_DEVICE_NAME)
    if device is None:
        raise RuntimeError(f"Playwright 디바이스 프로필을 찾지 못했습니다: {MOBILE_DEVICE_NAME}")

    width = MOBILE_VIEWPORT["width"]
    height = MOBILE_VIEWPORT["height"]
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
        devtools = is_devtools_block_dialog(dialog.message)
        try:
            if devtools:
                dialog.accept()
                return
            messages.append(dialog.message)
            print(f"[dialog] {dialog.message}")
            dialog.accept()
        except Exception:
            if not devtools:
                raise

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
