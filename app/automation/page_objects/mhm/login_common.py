from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.runner.step_logging import log

DEFAULT_BASE_URL: Final[str] = "https://m.hwgeneralins.com"
DEFAULT_SCREENSHOT_PATH: Final[Path] = Path("mhwgeneralins-login-result.png")
DEFAULT_ENV_FILE_PATH: Final[Path] = Path(".env")
PREFERRED_BROWSER_CHANNEL: Final[str] = "chrome"
MAX_TIMEOUT_MS: Final[int] = 15000
POST_LOGIN_MAIN_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"/myh/mai/MySubMain")
# 보안프로그램(키보드보안/백신류 로컬 에이전트 + 브라우저 확장)을 일반 브라우저나
# Cursor의 Playwright MCP와 동일하게 인식시키려면, 일회용 시크릿 컨텍스트가 아니라
# 영속 프로파일(persistent context)로 실행해야 한다. 아래 디렉터리에 프로파일 상태
# (로컬 에이전트 loopback 인증서 신뢰, 보안 확장 설치 등)가 누적된다.
# 환경변수 E2E_USER_DATA_DIR 로 경로를 바꿀 수 있으며, 사용자의 실제 Chrome 프로파일을
# 가리키게 하면 그 프로파일에 설치된 보안 확장을 그대로 사용할 수 있다.
DEFAULT_USER_DATA_DIR: Final[Path] = Path.home() / ".e2etester" / "mhm-chrome-profile"
MHM_MOBILE_DEVICE_NAME: Final[str] = "iPhone 14 Pro"

# Playwright 가 Chrome 실행 시 끄는 기본 feature 들(브라우저 안정화 목적). 아래에서
# 로컬 네트워크 차단 해제를 추가할 때, Chromium 은 명령행에서 마지막 --disable-features
# 하나만 인식하므로 Playwright 기본값을 잃지 않도록 반드시 함께 포함해서 넘긴다.
# (출처: playwright chromium chromiumSwitches.ts 의 disabledFeatures)
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

# 한화손보 보안프로그램은 로컬에 떠 있는 보안 에이전트(loopback/사설망)와 통신한다.
# Chrome 의 Local/Private Network Access 가 공개 사이트 -> 로컬 네트워크 요청을
# 기본 차단(설정 화면에 '로컬 네트워크 허용: 차단(기본값)')하므로, 일반 브라우저에서
# 사용자가 '허용'한 것과 동일하게 해당 차단 기능들을 꺼 준다. (모르는 feature 이름은
# Chrome 이 무시하므로 버전별로 넓게 나열해도 안전하다.)
LOCAL_NETWORK_DISABLED_FEATURES: Final[tuple[str, ...]] = (
    "LocalNetworkAccessChecks",
    "BlockInsecurePrivateNetworkRequests",
    "PrivateNetworkAccessSendPreflights",
    "PrivateNetworkAccessRespectPreflightResults",
    "PrivateNetworkAccessForNavigations",
    "PrivateNetworkAccessPermissionPrompt",
)

GENDER_VALUES: Final[dict[str, str]] = {
    "m": "01",
    "male": "01",
    "man": "01",
    "남": "01",
    "남성": "01",
    "f": "02",
    "female": "02",
    "woman": "02",
    "여": "02",
    "여성": "02",
    "01": "01",
    "02": "02",
}

RESIDENCY_VALUES: Final[dict[str, str]] = {
    "domestic": "01",
    "local": "01",
    "korean": "01",
    "내국인": "01",
    "01": "01",
    "foreign": "02",
    "foreigner": "02",
    "외국인": "02",
    "02": "02",
}

CARRIER_VALUES: Final[dict[str, str]] = {
    "01": "01",
    "skt": "01",
    "sk": "01",
    "02": "02",
    "kt": "02",
    "03": "03",
    "lgu": "03",
    "lgu+": "03",
    "lguplus": "03",
    "lg": "03",
    "05": "05",
    "skt_mvno": "05",
    "skt-mvno": "05",
    "sktmvno": "05",
    "skt_alt": "05",
    "06": "06",
    "kt_mvno": "06",
    "kt-mvno": "06",
    "ktmvno": "06",
    "kt_alt": "06",
    "07": "07",
    "lgu_mvno": "07",
    "lgu-mvno": "07",
    "lgumvno": "07",
    "lguplus_mvno": "07",
    "lguplus-mvno": "07",
    "lguplusmvno": "07",
    "lg_alt": "07",
}

PHONE_PREFIXES: Final[set[str]] = {"010", "011", "016", "017", "018", "019"}
FAILURE_DIALOG_KEYWORDS: Final[tuple[str, ...]] = (
    "bad request",
    "error",
    "오류",
    "실패",
    "지연",
    "제한",
    "유효하지",
    "불가",
    "다시 시도",
    "동의해 주세요",
    "고객 여부",
    "확인해 주세요",
)


@dataclass(frozen=True)
class LoginConfig:
    auth_method: str
    base_url: str
    name: str
    birthdate: str
    gender: str
    residency: str
    carrier: str
    phone_prefix: str
    phone_middle: str
    phone_last: str
    otp_code: str | None
    headless: bool
    slow_mo: int
    timeout_ms: int
    post_login_fragment: str
    screenshot_path: Path
    keep_open: bool
    success_stabilization_ms: int


def load_dotenv_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value

    return values


def env_or_arg(value: str | None, env_name: str, dotenv_values: dict[str, str]) -> str | None:
    if value is not None:
        return value
    env_value = os.getenv(env_name)
    if env_value is not None:
        return env_value
    return dotenv_values.get(env_name)


def normalize_base_url(raw: str | None) -> str:
    candidate = (raw or DEFAULT_BASE_URL).strip()
    if not candidate:
        candidate = DEFAULT_BASE_URL
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        candidate = f"https://{candidate.lstrip('/')}"

    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc or parsed.path
    netloc = netloc.strip("/")
    if netloc.lower() == "www.hwgeneralins.com":
        scheme = "https"
    return f"{scheme}://{netloc}"


def normalize_choice(raw: str, mapping: dict[str, str], field_name: str) -> str:
    normalized = raw.strip().lower().replace(" ", "")
    if normalized not in mapping:
        allowed = ", ".join(sorted(mapping))
        raise ValueError(f"Unsupported {field_name}: {raw}. Allowed values: {allowed}")
    return mapping[normalized]


def parse_phone_number(raw_phone: str, explicit_prefix: str | None) -> tuple[str, str, str]:
    digits = re.sub(r"\D", "", raw_phone)
    prefix = explicit_prefix or digits[:3]
    if prefix not in PHONE_PREFIXES:
        allowed = ", ".join(sorted(PHONE_PREFIXES))
        raise ValueError(f"Unsupported phone prefix: {prefix}. Allowed values: {allowed}")

    if digits.startswith(prefix):
        local_digits = digits[len(prefix) :]
    else:
        local_digits = digits

    if len(local_digits) not in {7, 8}:
        raise ValueError(
            "Phone number must contain 10 or 11 digits total, for example 01012345678."
        )

    if len(local_digits) == 7:
        middle = local_digits[:3]
        last = local_digits[3:]
    else:
        middle = local_digits[:4]
        last = local_digits[4:]

    return prefix, middle, last


def clamp_timeout_ms(value: int) -> int:
    return min(value, MAX_TIMEOUT_MS)


def build_config(args: argparse.Namespace) -> LoginConfig:
    dotenv_path = Path(args.env_file).expanduser()
    dotenv_values = load_dotenv_file(dotenv_path)

    raw_auth = getattr(args, "auth_method", None)
    auth_method = (env_or_arg(raw_auth, "HW_AUTH_METHOD", dotenv_values) or "phone").strip().lower()
    if auth_method not in {"phone", "kakao"}:
        raise ValueError(f"Unsupported auth_method for automation: {auth_method}")

    name = env_or_arg(args.name, "HW_NAME", dotenv_values)
    birthdate = env_or_arg(args.birthdate, "HW_BIRTHDATE", dotenv_values)
    gender = env_or_arg(args.gender, "HW_GENDER", dotenv_values)
    residency = env_or_arg(args.residency, "HW_RESIDENCY", dotenv_values)
    carrier = env_or_arg(args.carrier, "HW_CARRIER", dotenv_values)
    phone_number = env_or_arg(args.phone_number, "HW_PHONE_NUMBER", dotenv_values)
    phone_prefix = env_or_arg(args.phone_prefix, "HW_PHONE_PREFIX", dotenv_values)
    otp_code = env_or_arg(args.otp_code, "HW_OTP_CODE", dotenv_values)

    if auth_method == "kakao":
        missing = [
            env_name
            for env_name, value in (
                ("HW_NAME", name),
                ("HW_BIRTHDATE", birthdate),
                ("HW_PHONE_NUMBER", phone_number),
            )
            if not value
        ]
        gender = gender or "male"
        residency = residency or "domestic"
        carrier = carrier or "skt"
    else:
        missing = [
            env_name
            for env_name, value in (
                ("HW_NAME", name),
                ("HW_BIRTHDATE", birthdate),
                ("HW_GENDER", gender),
                ("HW_RESIDENCY", residency),
                ("HW_CARRIER", carrier),
                ("HW_PHONE_NUMBER", phone_number),
            )
            if not value
        ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required values: {joined}")

    assert birthdate is not None
    if not re.fullmatch(r"\d{8}", birthdate):
        raise ValueError("Birthdate must be 8 digits in YYYYMMDD format.")

    assert phone_number is not None
    prefix, middle, last = parse_phone_number(phone_number, phone_prefix)

    screenshot_path = Path(args.screenshot).expanduser()
    timeout_ms = clamp_timeout_ms(args.timeout_ms)
    success_stabilization_ms = clamp_timeout_ms(args.success_stabilization_ms)

    return LoginConfig(
        auth_method=auth_method,
        base_url=normalize_base_url(env_or_arg(args.base_url, "HW_BASE_URL", dotenv_values)),
        name=name or "",
        birthdate=birthdate,
        gender=normalize_choice(gender or "", GENDER_VALUES, "gender"),
        residency=normalize_choice(residency or "", RESIDENCY_VALUES, "residency"),
        carrier=normalize_choice(carrier or "", CARRIER_VALUES, "carrier"),
        phone_prefix=prefix,
        phone_middle=middle,
        phone_last=last,
        otp_code=otp_code.strip() if otp_code else None,
        headless=args.headless,
        slow_mo=args.slow_mo,
        timeout_ms=timeout_ms,
        post_login_fragment=args.post_login_fragment,
        screenshot_path=screenshot_path,
        keep_open=args.keep_open,
        success_stabilization_ms=success_stabilization_ms,
    )


def add_dialog_logger(page: Page) -> list[str]:
    messages: list[str] = []

    def _handle(dialog) -> None:
        messages.append(dialog.message)
        log(f"[dialog] {dialog.message}")
        dialog.accept()

    page.on("dialog", _handle)
    return messages


def get_new_dialogs(dialog_messages: list[str], start_index: int) -> list[str]:
    return dialog_messages[start_index:]


def is_failure_dialog(message: str) -> bool:
    normalized = message.strip().lower()
    return any(keyword in normalized for keyword in FAILURE_DIALOG_KEYWORDS)


def ensure_no_failure_dialogs(
    dialog_messages: list[str], start_index: int, step_name: str
) -> list[str]:
    new_dialogs = get_new_dialogs(dialog_messages, start_index)
    failures = [message for message in new_dialogs if is_failure_dialog(message)]
    if failures:
        joined = " | ".join(failures)
        raise RuntimeError(f"{step_name} failed: {joined}")
    return new_dialogs


def maybe_close_home_popup(page: Page) -> None:
    close_button = page.get_by_role("button", name=re.compile("닫기"))
    try:
        if close_button.first.is_visible(timeout=3000):
            click_with_log(close_button.first, "Close landing popup")
            log("[step] Closed landing popup")
    except PlaywrightTimeoutError:
        return


def maybe_close_pre_login_bottom_popup(page: Page) -> None:
    """로그인 버튼 클릭 전 하단 이벤트 배너 팝업(.dialog.bottom.bottom_bnr)을 닫는다."""
    log("[step] Check pre-login bottom banner popup")
    dialog_candidates = [
        page.locator(".dialog.bottom.bottom_bnr.show"),
        page.locator('[role="dialog"].bottom.bottom_bnr.show'),
    ]
    dialog = None
    for candidate in dialog_candidates:
        try:
            if candidate.first.is_visible(timeout=3000):
                dialog = candidate.first
                break
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue

    if dialog is None:
        log("[step] No pre-login bottom banner popup detected")
        return

    log("[step] Pre-login bottom banner popup detected")
    close_candidates = [
        dialog.locator("button.btn.s1.c1.ui_dialog_close"),
        dialog.get_by_role("button", name="닫기", exact=True),
        dialog.locator('button.btn.ui_dialog_close:has-text("닫기")'),
    ]
    for candidate in close_candidates:
        try:
            if candidate.first.is_visible(timeout=1500):
                click_with_log(candidate.first, "Close pre-login bottom banner popup")
                wait_timeout_with_log(page, 500, "Post bottom-banner-popup close settle")
                try:
                    if not dialog.is_visible(timeout=2000):
                        log("[step] Pre-login bottom banner popup dismissed")
                        return
                except PlaywrightTimeoutError:
                    log("[step] Pre-login bottom banner popup dismissed")
                    return
        except Exception:
            continue

    log("[warn] Pre-login bottom banner popup is still visible after close attempts")


def resolve_user_data_dir() -> Path:
    override = os.environ.get("E2E_USER_DATA_DIR")
    target = Path(override).expanduser() if override else DEFAULT_USER_DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_mobile_device(playwright) -> dict:
    device = playwright.devices.get(MHM_MOBILE_DEVICE_NAME)
    if device is None:
        raise RuntimeError(
            f"Playwright 디바이스 프로필을 찾지 못했습니다: {MHM_MOBILE_DEVICE_NAME}"
        )
    return device


def launch_persistent_browser_context(
    playwright, headless: bool, slow_mo: int, user_data_dir: Path | None = None
):
    """MHM용 브라우저 기동 — Cursor Playwright MCP 와 동일한 프로필·launch 옵션.

    사이트 접속 전에 반드시 ``apply_mobile_device_mode()`` 를 호출해야 한다.
    """
    from app.systems.access_common import browser as access_browser

    target = (
        Path(user_data_dir)
        if user_data_dir
        else access_browser.resolve_playwright_mcp_user_data_dir()
    )
    return access_browser.launch_playwright_mcp_browser_context(playwright, headless, target)


def apply_mobile_device_mode(playwright, page: Page) -> None:
    """브라우저 기동 직후·사이트 접속 전에 Chrome 모바일 디바이스 모드를 켠다.

    Playwright MCP로 수동 검증할 때와 동일한 순서를 강제한다:
    1) 브라우저 실행 → 2) 모바일 모드 전환 → 3) 이후 ``m.hwgeneralins.com`` 접속.
    """
    from app.systems.access_common.browser import MOBILE_VIEWPORT

    device = resolve_mobile_device(playwright)
    width = MOBILE_VIEWPORT["width"]
    height = MOBILE_VIEWPORT["height"]
    device_scale_factor = device.get("device_scale_factor", 1)
    user_agent = device["user_agent"]
    is_mobile = device.get("is_mobile", True)
    has_touch = device.get("has_touch", True)

    log(
        f"[step] Enable mobile device mode: {MHM_MOBILE_DEVICE_NAME} "
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
        log("[step] Mobile device emulation applied (CDP)")
    except Exception as exc:
        log(f"[warn] CDP mobile emulation fallback (viewport only): {exc}")

    page._mhm_mobile_mode_applied = True
    log("[step] Mobile mode ready - safe to navigate to m.hwgeneralins.com")


def ensure_mobile_mode_before_navigation(page: Page) -> None:
    if not getattr(page, "_mhm_mobile_mode_applied", False):
        raise RuntimeError(
            "m.hwgeneralins.com 접속 전에 모바일 디바이스 모드가 적용되어야 합니다. "
            "브라우저 기동 → 모바일 모드 전환 → 접속 순서를 지키세요."
        )


def wait_timeout_with_log(page: Page, timeout_ms: int, reason: str) -> None:
    log(f"[wait] Start timeout wait: {reason} ({timeout_ms} ms)")
    page.wait_for_timeout(timeout_ms)
    log(f"[wait] End timeout wait: {reason}")


def wait_url_with_log(page: Page, url_or_pattern, timeout_ms: int, reason: str) -> None:
    log(f"[wait] Start URL wait: {reason} ({timeout_ms} ms)")
    page.wait_for_url(url_or_pattern, timeout=timeout_ms)
    log(f"[wait] End URL wait: {reason} -> {page.url}")


def wait_locator_visible_with_log(locator, timeout_ms: int, reason: str) -> None:
    log(f"[wait] Start locator visible wait: {reason} ({timeout_ms} ms)")
    locator.wait_for(state="visible", timeout=timeout_ms)
    log(f"[wait] End locator visible wait: {reason}")


def wait_function_with_log(page: Page, expression: str, timeout_ms: int, reason: str) -> None:
    log(f"[wait] Start function wait: {reason} ({timeout_ms} ms)")
    page.wait_for_function(expression, timeout=timeout_ms)
    log(f"[wait] End function wait: {reason}")


def click_with_log(locator, description: str) -> None:
    log(f"[click] {description}")
    locator.click()


def open_url(page: Page, target_url: str) -> None:
    log(f"[wait] Start direct navigation: {target_url} ({MAX_TIMEOUT_MS} ms default)")
    page.goto(target_url, wait_until="domcontentloaded", timeout=MAX_TIMEOUT_MS)
    log(f"[wait] End direct navigation: {target_url} -> {page.url}")


def click_and_wait_for_navigation(page: Page, locator, expected_url: str) -> None:
    log(f"[wait] Start navigation wait: {expected_url} ({MAX_TIMEOUT_MS} ms default)")
    with page.expect_navigation(wait_until="domcontentloaded"):
        click_with_log(locator, f"Navigate to {expected_url}")
    log(f"[wait] End navigation wait: {expected_url} -> {page.url}")
    wait_url_with_log(
        page, re.compile(expected_url), MAX_TIMEOUT_MS, f"Confirm URL matches {expected_url}"
    )


def grant_browser_permissions(context, base_url: str) -> None:
    origin = normalize_base_url(base_url)
    try:
        context.grant_permissions(["local-network-access"], origin=origin)
        log(f"[step] Granted browser permission: local-network-access for {origin}")
    except Exception as exc:
        log(f"[warn] Failed to pre-grant local-network-access permission: {exc}")


def click_label(page: Page, field_id: str) -> None:
    click_with_log(page.locator(f'label[for="{field_id}"]'), f"Click label for {field_id}")


def select_dropdown_option(root: Page | Locator, headline: str, button_name: str) -> None:
    anchor = root.locator(f'a.headline[title="{headline}"]').first
    sel_root = anchor.locator("xpath=ancestor::div[contains(@class, 'select_list')][1]")
    click_with_log(anchor, f"Open dropdown: {headline}")
    option = sel_root.locator(f'ul >> button[name="{button_name}"]')
    wait_locator_visible_with_log(
        option, MAX_TIMEOUT_MS, f"Dropdown option {button_name} visible in {headline}"
    )
    click_with_log(option, f"Select dropdown option {button_name} from {headline}")


def select_dropdown_option_first_visible(
    root: Page | Locator, headline: str, button_name: str
) -> None:
    """같은 title의 드롭다운이 페이지에 여러 개(숨김 템플릿 등)일 때, 보이는 앵커만 연다."""
    anchors = root.locator(f'a.headline[title="{headline}"]')
    anchor = None
    for i in range(anchors.count()):
        cand = anchors.nth(i)
        try:
            if cand.is_visible(timeout=800):
                anchor = cand
                break
        except Exception:
            continue
    if anchor is None:
        select_dropdown_option(root, headline, button_name)
        return
    sel_root = anchor.locator("xpath=ancestor::div[contains(@class, 'select_list')][1]")
    click_with_log(anchor, f"Open dropdown (visible): {headline}")
    option = sel_root.locator(f'ul >> button[name="{button_name}"]')
    wait_locator_visible_with_log(
        option, MAX_TIMEOUT_MS, f"Dropdown option {button_name} visible in {headline}"
    )
    click_with_log(option, f"Select dropdown option {button_name} from {headline}")


def first_visible_locator(locator: Locator, description: str) -> Locator:
    for i in range(locator.count()):
        candidate = locator.nth(i)
        try:
            if candidate.is_visible(timeout=800):
                return candidate
        except Exception:
            continue
    raise RuntimeError(f"표시 중인 요소를 찾지 못했습니다: {description}")


def ensure_terms_agreed(page: Page, carrier_code: str) -> None:
    click_label(page, "formChkAll")
    for field_id in ("formChkAgree1_1", "formChkAgree2_1", "formChkAgree3_1", "formChkAgree4_1"):
        click_label(page, field_id)

    if carrier_code in {"05", "06", "07"}:
        click_label(page, "formChkAgree5_1")


def select_identity_options(page: Page, config: LoginConfig) -> None:
    click_label(page, "formPolicyGender1" if config.gender == "01" else "formPolicyGender2")
    click_label(page, "formSelMem1" if config.residency == "01" else "formSelMem2")


def fill_phone_fields(page: Page, config: LoginConfig) -> None:
    select_dropdown_option(page, "휴대폰번호(통신사) 선택", config.carrier)
    select_dropdown_option(page, "휴대폰번호(앞자리) 선택", config.phone_prefix)
    click_with_log(page.locator("#hndphTltno"), "Focus phone middle digits input")
    page.locator("#hndphTltno").fill(config.phone_middle)
    click_with_log(page.locator("#hndphTlsno"), "Focus phone last digits input")
    page.locator("#hndphTlsno").fill(config.phone_last)


def fill_kakao_phone_segments(
    page: Page, config: LoginConfig, *, scope: Locator | None = None
) -> None:
    """Kakao 본인인증: 통신사 없이 앞자리·중간·끝 전화번호만 입력.

    팝업/숨김 마크업이 겹칠 수 있어 드롭다운은 **보이는** 앵커만 사용하고,
    휴대폰 칸은 접근성 이름(한화손보 카카오 팝업과 동일)으로 찾는다.
    """
    root: Page | Locator = scope if scope is not None else page
    select_dropdown_option_first_visible(root, "휴대폰번호(앞자리) 선택", config.phone_prefix)
    try:
        mid = first_visible_locator(
            root.get_by_role("textbox", name="휴대폰번호(중간 자리)"),
            "휴대폰번호(중간 자리)",
        )
        last = first_visible_locator(
            root.get_by_role("textbox", name="휴대폰번호(뒷자리)"),
            "휴대폰번호(뒷자리)",
        )
    except RuntimeError:
        mid = page.locator("#hndphTltno")
        last = page.locator("#hndphTlsno")
        wait_locator_visible_with_log(mid, MAX_TIMEOUT_MS, "Kakao #hndphTltno fallback")
        wait_locator_visible_with_log(last, MAX_TIMEOUT_MS, "Kakao #hndphTlsno fallback")
    click_with_log(mid, "Focus phone middle (Kakao)")
    mid.fill(config.phone_middle)
    click_with_log(last, "Focus phone last (Kakao)")
    last.fill(config.phone_last)


def fill_identity(page: Page, config: LoginConfig) -> None:
    log("[step] Fill identity and phone fields")
    page.locator("#custNm").fill(config.name)
    page.locator("#custDscNo1").fill(config.birthdate)
    select_identity_options(page, config)
    fill_phone_fields(page, config)
    ensure_terms_agreed(page, config.carrier)


def scroll_to_page_bottom(page: Page) -> None:
    log("[step] Scroll to page bottom")
    page.evaluate(
        """
        () => {
            const root = document.scrollingElement || document.documentElement || document.body;
            if (!root) {
                return;
            }
            window.scrollTo({ top: root.scrollHeight, behavior: 'instant' });
        }
        """
    )
    wait_timeout_with_log(page, 300, "Scroll settle delay")


def request_sms_code(page: Page, dialog_messages: list[str], timeout_ms: int) -> None:
    log("[step] Request SMS verification code")
    dialog_index = len(dialog_messages)
    scroll_to_page_bottom(page)
    log(f"[wait] Start response wait: hp-sms-request.json ({timeout_ms} ms)")
    with page.expect_response(
        lambda response: "hp-sms-request.json" in response.url, timeout=timeout_ms
    ) as response_info:
        click_with_log(page.locator("#btnSendCrtfNo"), "Request SMS verification code")

    response = response_info.value
    log(f"[wait] End response wait: hp-sms-request.json -> {response.status} {response.url}")
    wait_timeout_with_log(page, 1000, "Post-SMS-request settle delay")

    if not response.ok:
        recent_dialogs = get_new_dialogs(dialog_messages, dialog_index)
        detail = recent_dialogs[-1] if recent_dialogs else f"HTTP {response.status}"
        raise RuntimeError(
            f"SMS verification request failed with status {response.status}: {detail}"
        )

    ensure_no_failure_dialogs(dialog_messages, dialog_index, "SMS verification request")

    try:
        wait_function_with_log(
            page,
            """
            () => {
              const smsInput = document.querySelector('#smsCertNo');
              const authPno = document.querySelector('#authPno');
              return Boolean(
                (authPno && authPno.value.trim() !== '') ||
                (smsInput && !smsInput.disabled)
              );
            }
            """,
            timeout_ms,
            "OTP input becomes available",
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "SMS verification request did not leave the page in a usable OTP-entry state."
        ) from exc


def resolve_otp_code(config: LoginConfig) -> str:
    if config.otp_code:
        otp_code = config.otp_code
    else:
        otp_code = input("Enter the OTP received on the phone: ").strip()

    if not re.fullmatch(r"\d{4,8}", otp_code):
        raise ValueError("OTP code must be 4 to 8 digits.")
    return otp_code


def handle_post_otp_privacy_step(page: Page, timeout_ms: int) -> None:
    def click_if_visible(locator, description: str) -> bool:
        try:
            wait_locator_visible_with_log(locator, 3000, description)
        except PlaywrightTimeoutError:
            return False
        log(f"[step] {description}")
        click_with_log(locator, description)
        wait_timeout_with_log(page, 800, f"Post-click settle delay: {description}")
        return True

    def click_visible_confirm_button() -> bool:
        candidates = [
            page.locator("#btnNext"),
            page.locator('button:has-text("확인")').last,
            page.locator('input[type="button"][value="확인"]').last,
            page.locator('input[type="submit"][value="확인"]').last,
        ]
        for candidate in candidates:
            try:
                wait_locator_visible_with_log(candidate, 1500, "Visible confirm button")
            except PlaywrightTimeoutError:
                continue
            click_with_log(candidate, "Click visible confirm button")
            wait_timeout_with_log(page, 1000, "Post-confirm settle delay")
            return True
        return False

    step_handled = False
    scroll_to_page_bottom(page)

    if click_if_visible(
        page.locator('label[for="formChkAgree6_1"]'), "Handle post-OTP privacy consent"
    ):
        click_visible_confirm_button()
        step_handled = True

    scroll_to_page_bottom(page)

    if click_if_visible(
        page.locator('label[for="comformChkAll"]'), "Handle customer confirmation consent"
    ):
        click_visible_confirm_button()
        step_handled = True

    if not step_handled:
        return

    scroll_to_page_bottom(page)


def submit_otp(page: Page, otp_code: str, dialog_messages: list[str], timeout_ms: int) -> None:
    log("[step] Submit OTP")
    dialog_index = len(dialog_messages)
    page.locator("#smsCertNo").fill(otp_code)
    click_with_log(page.locator("#btnNext2"), "Submit OTP confirmation")
    wait_timeout_with_log(page, 1000, "Post-OTP-submit settle delay")
    handle_post_otp_privacy_step(page, timeout_ms)
    ensure_no_failure_dialogs(dialog_messages, dialog_index, "OTP submission")


def wait_for_login_success(page: Page, config: LoginConfig, dialog_messages: list[str]) -> None:
    dialog_index = len(dialog_messages)
    log(f"[wait] Start login success wait via main page URL ({config.timeout_ms} ms)")
    ensure_no_failure_dialogs(dialog_messages, dialog_index, "post-login")
    wait_for_main_page(page, config.post_login_fragment, config.timeout_ms)
    maybe_close_post_login_popup(page, config.timeout_ms)
    ensure_no_failure_dialogs(dialog_messages, dialog_index, "post-login")
    log("[wait] End login success wait via main page URL")


def dismiss_coach_mark_if_present(page: Page, timeout_ms: int = 8000) -> None:
    coach = page.locator("#coachMarkDialog.dialog.full.show, #coachMarkDialog.show")
    try:
        if not coach.first.is_visible(timeout=1500):
            return
    except Exception:
        return

    log("[step] Dismiss post-login coach mark overlay")
    remaining_ms = timeout_ms
    while remaining_ms > 0:
        try:
            if not coach.first.is_visible(timeout=500):
                log("[step] Coach mark overlay dismissed")
                return
        except Exception:
            log("[step] Coach mark overlay dismissed")
            return

        click_targets = [
            page.locator("#coachMarkDialog .coach_mark").first,
            page.locator(
                "#coachMarkDialog .mark1, #coachMarkDialog .mark2, #coachMarkDialog .mark4"
            ).first,
            page.locator("#coachMarkDialog label[for='notOpenCoachMark']").first,
        ]
        clicked = False
        for target in click_targets:
            try:
                if target.is_visible(timeout=400):
                    click_with_log(target, "Advance/dismiss coach mark overlay")
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            page.keyboard.press("Escape")
        slice_ms = 500
        wait_timeout_with_log(page, slice_ms, "Coach mark step settle")
        remaining_ms -= slice_ms + 400


def wait_for_main_page(page: Page, expected_fragment: str, timeout_ms: int) -> None:
    fragment = expected_fragment or "/myh/mai/MySubMain1000"
    log(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "expectedFragment => window.location.href.includes(expectedFragment)",
        arg=fragment,
        timeout=timeout_ms,
    )
    log(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def maybe_close_post_login_popup(page: Page, timeout_ms: int = MAX_TIMEOUT_MS) -> None:
    log("[step] Check post-login popup")
    dismiss_coach_mark_if_present(page, min(timeout_ms, 8000))

    overlay_candidates = [
        page.locator("#uiPOPCtmAgreOverlay"),
        page.locator(".modal_overlay:visible"),
        page.locator("#coachMarkDialog.dialog.full.show"),
    ]
    modal_candidates = [
        page.locator("#uiPOPCtmAgre:visible, #uiPOPCtmAgreLayer:visible").first,
        page.locator('.dialog.modal.show:has-text("모바일 안내장")').first,
        page.locator(':visible >> text="모바일 안내장 신청 안내"').first,
        page.locator(':visible >> text="모바일 안내장 신청안내"').first,
        page.locator(':visible >> text="모바일 안내장"').first,
    ]
    button_candidates = [
        page.get_by_role("button", name=re.compile(r"다음에\s*할게요")).first,
        page.locator('button:has-text("다음에 할게요")').first,
        page.locator('a:has-text("다음에 할게요")').first,
        page.locator('input[type="button"][value*="다음에"]').first,
        page.locator('input[type="submit"][value*="다음에"]').first,
    ]

    detection_timeout = min(timeout_ms, 5000)
    popup_detected = False

    def popup_blocking() -> bool:
        return page.evaluate(
            """
            () => {
                const isVisible = (element) => {
                    if (!element) {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };

                const overlay = document.querySelector('#uiPOPCtmAgreOverlay');
                if (isVisible(overlay)) {
                    return true;
                }

                for (const selector of ['#coachMarkDialog', '.dialog.full.show', '.dialog.modal.show']) {
                    for (const element of document.querySelectorAll(selector)) {
                        if (isVisible(element)) {
                            return true;
                        }
                    }
                }

                for (const element of document.querySelectorAll('.modal_overlay, .modal_popup, .modal_wrap, .modal, .pop_wrap')) {
                    if (isVisible(element)) {
                        return true;
                    }
                }

                return false;
            }
            """
        )

    def wait_for_popup_to_clear(wait_ms: int) -> bool:
        try:
            page.wait_for_function(
                """
                () => {
                    const isVisible = (element) => {
                        if (!element) {
                            return false;
                        }
                        const style = window.getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };

                    const overlay = document.querySelector('#uiPOPCtmAgreOverlay');
                    if (isVisible(overlay)) {
                        return false;
                    }

                    for (const selector of ['#coachMarkDialog', '.dialog.full.show', '.dialog.modal.show']) {
                        for (const element of document.querySelectorAll(selector)) {
                            if (isVisible(element)) {
                                return false;
                            }
                        }
                    }

                    for (const element of document.querySelectorAll('.modal_overlay, .modal_popup, .modal_wrap, .modal, .pop_wrap')) {
                        if (isVisible(element)) {
                            return false;
                        }
                    }

                    return true;
                }
                """,
                timeout=wait_ms,
            )
            return True
        except Exception:
            return False

    for overlay in overlay_candidates:
        try:
            if overlay.first.is_visible(timeout=1200):
                popup_detected = True
                log("[step] Post-login popup overlay detected")
                break
        except Exception:
            continue

    if not popup_detected:
        for modal in modal_candidates:
            try:
                if modal.is_visible(timeout=1200):
                    popup_detected = True
                    log("[step] Post-login popup modal detected")
                    break
            except Exception:
                continue

    popup_button = None
    deadline_ms = detection_timeout
    while deadline_ms > 0 and popup_button is None:
        for candidate in button_candidates:
            try:
                if candidate.is_visible(timeout=min(800, deadline_ms)):
                    popup_button = candidate
                    popup_detected = True
                    break
            except Exception:
                continue
        if popup_button is not None:
            break
        if popup_detected:
            break
        slice_ms = min(500, deadline_ms)
        wait_timeout_with_log(page, slice_ms, "Wait for post-login popup appearance")
        deadline_ms -= slice_ms

    if not popup_detected and popup_button is None:
        log("[step] No post-login popup detected")
        return

    strategy_used = ""

    if popup_button is not None:
        click_with_log(popup_button, "Dismiss post-login popup with '다음에 할게요'")
        strategy_used = "locator"
        if wait_for_popup_to_clear(2500):
            log("[step] Post-login popup dismissed")
            return
        log("[warn] Popup click completed but overlay is still blocking")

    for attempt in range(2):
        clicked_via_dom = page.evaluate(
            """
            () => {
                const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                const isVisible = (element) => {
                    if (!element) {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const clickTarget = (element) => {
                    if (!element || !isVisible(element)) {
                        return false;
                    }
                    const clickable = element.closest('button, a, input, [role="button"], label, span, div');
                    if (!clickable || !isVisible(clickable)) {
                        return false;
                    }
                    clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    clickable.click();
                    return true;
                };

                const modalRoots = [
                    document.querySelector('#uiPOPCtmAgre'),
                    document.querySelector('#uiPOPCtmAgreLayer'),
                    ...Array.from(document.querySelectorAll('.modal_popup, .modal_wrap, .modal, .pop_wrap')),
                ].filter(Boolean).filter(isVisible);

                const searchRoots = modalRoots.length ? modalRoots : [document.body];

                for (const root of searchRoots) {
                    for (const element of root.querySelectorAll('*')) {
                        const text = normalize(element.textContent);
                        if (text.includes('다음에 할게요') || (text.includes('다음에') && text.includes('할게요'))) {
                            if (clickTarget(element)) {
                                return 'later';
                            }
                        }
                    }
                }

                for (const root of searchRoots) {
                    for (const element of root.querySelectorAll('button, a, input, [role="button"]')) {
                        const text = normalize(element.textContent);
                        const title = normalize(element.getAttribute('title'));
                        const ariaLabel = normalize(element.getAttribute('aria-label'));
                        const value = normalize(element.getAttribute('value'));
                        const closeLike = (
                            text === '×' ||
                            text.toLowerCase() === 'x' ||
                            title.includes('닫기') ||
                            ariaLabel.includes('닫기') ||
                            value.includes('닫기')
                        );
                        if (closeLike && clickTarget(element)) {
                            return 'close';
                        }
                    }
                }

                return '';
            }
            """
        )
        if clicked_via_dom:
            strategy_used = f"dom:{clicked_via_dom}"
            log(f"[step] Post-login popup dismissed via DOM fallback: {clicked_via_dom}")
            if wait_for_popup_to_clear(2500):
                log("[step] Post-login popup dismissed")
                return
            log("[warn] Popup DOM fallback click did not remove blocking overlay")

        if not popup_blocking():
            log("[step] Post-login popup dismissed")
            return
        if attempt == 0:
            wait_timeout_with_log(page, 500, "Retry post-login popup dismiss")

    forcibly_hidden = page.evaluate(
        """
        () => {
            const isVisible = (element) => {
                if (!element) {
                    return false;
                }
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            };

            let changed = false;
            for (const selector of ['#uiPOPCtmAgreOverlay', '#uiPOPCtmAgre', '#uiPOPCtmAgreLayer', '#coachMarkDialog', '.dialog.full.show', '.dialog.modal.show', '.modal_overlay', '.modal_popup', '.modal_wrap', '.modal', '.pop_wrap']) {
                for (const element of document.querySelectorAll(selector)) {
                    if (!isVisible(element)) {
                        continue;
                    }
                    element.setAttribute('data-e2e-forced-hidden', 'true');
                    element.style.setProperty('display', 'none', 'important');
                    element.style.setProperty('visibility', 'hidden', 'important');
                    element.style.setProperty('pointer-events', 'none', 'important');
                    changed = true;
                }
            }
            return changed;
        }
        """
    )

    if forcibly_hidden:
        log(
            f"[warn] Forcibly hid blocking post-login popup after failed dismiss strategy: {strategy_used or 'none'}"
        )
        if wait_for_popup_to_clear(1500):
            log("[step] Post-login popup dismissed")
            return

    raise RuntimeError("로그인 후 팝업을 닫았지만 차단 오버레이가 계속 남아 있습니다.")


def shutdown_browser(page: Page, context, browser=None) -> None:
    log("[step] Closing page")
    try:
        page.close(run_before_unload=False)
    except Exception as exc:
        log(f"[warn] Failed to close page cleanly: {exc}")

    # persistent context 는 별도 browser 객체가 없으며, context 를 닫으면 브라우저도 종료된다.
    log("[step] Closing browser context")
    try:
        context.close()
    except Exception as exc:
        log(f"[warn] Failed to close browser context cleanly: {exc}")

    if browser is not None:
        log("[step] Closing browser")
        try:
            browser.close()
        except Exception as exc:
            log(f"[warn] Failed to close browser cleanly: {exc}")


def keep_script_alive_with_browser_open(page: Page, context) -> None:
    log(
        "[result] Keeping browser open. Close the browser window or press Ctrl+C to end the script."
    )
    sys.stdout.flush()
    sys.stderr.flush()

    try:
        while context.pages and not page.is_closed():
            page.wait_for_timeout(1000)
    except KeyboardInterrupt:
        log("\n[step] KeyboardInterrupt received. Cleaning up browser and exiting.")
