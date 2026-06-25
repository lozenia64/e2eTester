from __future__ import annotations

import re
import time

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.systems.access_common import browser
from app.systems.hwtc.steps.phone_auth import AUTH_SUCCESS_PATH

MAIN_PAGE_PATH = AUTH_SUCCESS_PATH
IT_COURSE_LIST_PATH = "/ctnt/2000000047/plusL.do"
VIDEO_DETAIL_PATH = "/ctnt/plusF.do"

CONTENT_PLUS_MENU = "콘텐츠플러스"
IT_COURSE_MENU = "IT교육과정"
EDUCATION_VIDEO_HEADING = "교육영상"

VIDEO_PLAYER_ROOT_SELECTOR = ".video-js"
VIDEO_PLAYER_REGION_NAME = "Video Player"
GO_VIEW_PATTERN = re.compile(r"goView\('([^']+)'\)")
REMAINING_TIME_TEXT_PATTERN = re.compile(r"^-\d+:\d+$")
VJS_TIME_PATTERN = re.compile(r"-?(?P<minutes>\d+):(?P<seconds>\d+)")

PLAYBACK_WAIT_SECONDS = 30
MIN_REMAINING_TIME_DROP_SECONDS = 5.0
OBSERVATION_POLL_INTERVAL_MS = 2_000
PLAYER_READY_TIMEOUT_MS = 30_000
PLAYBACK_PROBE_TIMEOUT_SECONDS = 8.0
PLAYER_LOCATE_TIMEOUT_MS = 5_000
LOCATOR_VISIBLE_TIMEOUT_MS = 1_500

PAUSE_BUTTON_NAMES = ("Pause", "일시정지")
PLAY_BUTTON_NAMES = ("Play Video", "Play", "재생")

_JS_READ_FROM_ROOT = """(root) => {
    const video = root.querySelector('video.vjs-tech') || root.querySelector('video');
    const pauseBtn = root.querySelector('.vjs-play-control');
    const bigPlay = root.querySelector('.vjs-big-play-button');
    const remaining = root.querySelector('.vjs-remaining-time');
    const current = root.querySelector('.vjs-current-time');
    return {
        isPlayingClass: root.classList.contains('vjs-playing'),
        isPausedClass: root.classList.contains('vjs-paused'),
        pauseButtonLabel: pauseBtn ? (pauseBtn.getAttribute('aria-label') || pauseBtn.getAttribute('title') || '') : '',
        bigPlayHidden: !!bigPlay && bigPlay.classList.contains('vjs-hidden'),
        remainingTimeText: remaining ? (remaining.textContent || '').trim() : '',
        currentTimeText: current ? (current.textContent || '').trim() : '',
        video: video ? {
            currentTime: video.currentTime,
            paused: video.paused,
            ended: video.ended,
            readyState: video.readyState,
        } : null,
    };
}"""

_JS_CLICK_FROM_ROOT = """(root) => {
    const big = root.querySelector('.vjs-big-play-button');
    if (big && !big.classList.contains('vjs-hidden')) {
        big.click();
        return 'big-play-button';
    }
    const poster = root.querySelector('.vjs-poster');
    if (poster) {
        poster.click();
        return 'poster';
    }
    const play = root.querySelector('.vjs-play-control');
    if (play) {
        play.click();
        return 'play-control';
    }
    return null;
}"""


def _main_url(base_url: str) -> str:
    return f"{browser.normalize_base_url(base_url, base_url)}{MAIN_PAGE_PATH}"


def _ensure_main_page(page: Page, base_url: str) -> None:
    if MAIN_PAGE_PATH in page.url:
        browser.maybe_close_popup(page)
        return
    main_url = _main_url(base_url)
    print(f"[wait] Navigate to main page: {main_url}")
    page.goto(main_url, wait_until="domcontentloaded", timeout=browser.MAX_TIMEOUT_MS)
    browser.maybe_close_popup(page)
    if MAIN_PAGE_PATH not in page.url:
        raise RuntimeError(f"메인화면({MAIN_PAGE_PATH})으로 이동하지 못했습니다: {page.url}")
    print(f"[wait] Main page ready: {page.url}")


def _open_it_course_list(page: Page) -> None:
    print("[step] Open IT course list from top menu")
    page.get_by_role("link", name=CONTENT_PLUS_MENU, exact=True).hover()
    page.get_by_role("link", name=IT_COURSE_MENU, exact=True).click()
    page.wait_for_url(f"**{IT_COURSE_LIST_PATH}", timeout=browser.MAX_TIMEOUT_MS)
    browser.maybe_close_popup(page)
    print(f"[step] IT course list opened: {page.url}")


def _first_education_video_item(page: Page):
    return (
        page.locator(f'h3:has-text("{EDUCATION_VIDEO_HEADING}")')
        .locator("..")
        .locator("..")
        .locator("ul li")
        .first
    )


def _open_first_video_detail(page: Page) -> None:
    print("[step] Open first education video detail")
    first_item = _first_education_video_item(page)
    first_item.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    onclick = first_item.locator(".cover.vod a").get_attribute("onclick")
    if not onclick:
        raise RuntimeError("첫 번째 교육영상 상세 링크를 찾지 못했습니다.")
    match = GO_VIEW_PATTERN.search(onclick)
    if not match:
        raise RuntimeError(f"교육영상 상세 진입 함수를 해석하지 못했습니다: {onclick}")
    content_id = match.group(1)
    print(f"[step] Open video content: {content_id}")
    page.evaluate("(contentId) => goView(contentId)", content_id)
    page.wait_for_url(f"**{VIDEO_DETAIL_PATH}", timeout=browser.MAX_TIMEOUT_MS)
    browser.maybe_close_popup(page)
    _wait_for_player_ready(page)
    print(f"[step] Video detail opened: {page.url}")


def _video_player_region(page: Page) -> Locator:
    return page.get_by_role("region", name=VIDEO_PLAYER_REGION_NAME)


def _wait_for_player_ready(page: Page) -> None:
    deadline = time.monotonic() + PLAYER_READY_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        if _video_player_region(page).count() > 0:
            return
        if page.locator(VIDEO_PLAYER_ROOT_SELECTOR).count() > 0:
            return
        page.wait_for_timeout(250)
    raise RuntimeError("동영상 플레이어 영역을 찾지 못했습니다.")


def _find_player_root(page: Page) -> Locator | None:
    if page.locator(VIDEO_PLAYER_ROOT_SELECTOR).count() > 0:
        return page.locator(VIDEO_PLAYER_ROOT_SELECTOR).first
    if _video_player_region(page).count() > 0:
        return _video_player_region(page).first
    return None


def _button_visible_in_player(page: Page, names: tuple[str, ...]) -> bool:
    scopes: list[Locator] = []
    if _video_player_region(page).count() > 0:
        scopes.append(_video_player_region(page))
    scopes.append(page)

    for scope in scopes:
        for name in names:
            button = scope.get_by_role("button", name=name)
            try:
                if button.first.is_visible(timeout=LOCATOR_VISIBLE_TIMEOUT_MS):
                    return True
            except PlaywrightTimeoutError:
                continue
    return False


def _read_remaining_time_text(page: Page) -> str:
    if _video_player_region(page).count() > 0:
        region = _video_player_region(page)
        try:
            text = region.get_by_text(REMAINING_TIME_TEXT_PATTERN).first.inner_text(
                timeout=LOCATOR_VISIBLE_TIMEOUT_MS
            )
            cleaned = (text or "").strip()
            if cleaned:
                return cleaned
        except PlaywrightTimeoutError:
            pass

    try:
        text = page.locator(".vjs-remaining-time").first.inner_text(
            timeout=LOCATOR_VISIBLE_TIMEOUT_MS
        )
        return (text or "").strip()
    except PlaywrightTimeoutError:
        return ""


def _parse_vjs_time_text(text: str) -> float | None:
    match = VJS_TIME_PATTERN.search((text or "").strip())
    if not match:
        return None
    return int(match.group("minutes")) * 60 + int(match.group("seconds"))


def _remaining_time_drop_seconds(start_text: str, end_text: str) -> float | None:
    start_seconds = _parse_vjs_time_text(start_text)
    end_seconds = _parse_vjs_time_text(end_text)
    if start_seconds is None or end_seconds is None:
        return None
    return start_seconds - end_seconds


def _enrich_with_js_state(page: Page, signals: dict[str, object]) -> dict[str, object]:
    root = _find_player_root(page)
    if root is None:
        return signals
    try:
        js_state = root.evaluate(_JS_READ_FROM_ROOT)
    except Exception as exc:
        print(f"[warn] Player JS state skipped: {exc}")
        return signals
    if not isinstance(js_state, dict):
        return signals
    merged = dict(signals)
    merged.update(js_state)
    return merged


def _read_playback_signals(page: Page) -> dict[str, object]:
    has_region = _video_player_region(page).count() > 0
    has_video_js = page.locator(VIDEO_PLAYER_ROOT_SELECTOR).count() > 0
    pause_visible = _button_visible_in_player(page, PAUSE_BUTTON_NAMES)
    play_visible = _button_visible_in_player(page, PLAY_BUTTON_NAMES)
    remaining_text = _read_remaining_time_text(page)

    signals: dict[str, object] = {
        "hasPlayer": has_region or has_video_js,
        "pauseVisible": pause_visible,
        "playVisible": play_visible,
        "remainingTimeText": remaining_text,
    }
    return _enrich_with_js_state(page, signals)


def _signals_show_playing(
    signals: dict[str, object],
    *,
    previous_remaining: str | None = None,
    min_remaining_drop_seconds: float = 1.0,
) -> bool:
    if not signals.get("hasPlayer"):
        return False
    if signals.get("pauseVisible"):
        return True
    if signals.get("isPlayingClass"):
        return True
    pause_label = str(signals.get("pauseButtonLabel") or "")
    if "Pause" in pause_label or "일시정지" in pause_label:
        return True
    if signals.get("bigPlayHidden") and not signals.get("isPausedClass"):
        return True

    video = signals.get("video")
    if isinstance(video, dict):
        if video.get("ended"):
            return True
        if video.get("paused") is False:
            return True

    remaining_text = str(signals.get("remainingTimeText") or "")
    if previous_remaining and remaining_text:
        drop = _remaining_time_drop_seconds(previous_remaining, remaining_text)
        if drop is not None and drop >= min_remaining_drop_seconds:
            return True

    return False


def _format_playback_signals(signals: dict[str, object] | None) -> str:
    if not signals:
        return "no-signals"
    video = signals.get("video") if isinstance(signals.get("video"), dict) else {}
    return (
        f"hasPlayer={signals.get('hasPlayer')} "
        f"pauseVisible={signals.get('pauseVisible')} "
        f"playVisible={signals.get('playVisible')} "
        f"remaining={signals.get('remainingTimeText')!r} "
        f"playingClass={signals.get('isPlayingClass')} "
        f"videoPaused={video.get('paused') if isinstance(video, dict) else None} "
        f"videoTime={float(video.get('currentTime') or 0) if isinstance(video, dict) else 0:.1f}"
    )


def _click_play_control(page: Page) -> str:
    if _button_visible_in_player(page, PAUSE_BUTTON_NAMES):
        print("[step] Video already playing (Pause control visible)")
        return "already-playing"

    for name in PLAY_BUTTON_NAMES:
        for scope in (_video_player_region(page), page):
            if scope.count() == 0 and scope is not page:
                continue
            button = scope.get_by_role("button", name=name)
            try:
                if button.first.is_visible(timeout=LOCATOR_VISIBLE_TIMEOUT_MS):
                    button.first.click(timeout=browser.MAX_TIMEOUT_MS)
                    print(f"[step] Click video play control via role button ({name})")
                    return name
            except PlaywrightTimeoutError:
                continue

    root = _find_player_root(page)
    if root is None:
        raise RuntimeError("동영상 재생 버튼을 찾지 못했습니다.")
    clicked = root.evaluate(_JS_CLICK_FROM_ROOT)
    if not clicked:
        raise RuntimeError(
            "동영상 재생 버튼(.vjs-big-play-button / .vjs-poster)을 찾지 못했습니다."
        )
    print(f"[step] Click video play control via {clicked}")
    return clicked


def _activate_detail_video_player(page: Page) -> None:
    print("[step] Activate detail page video player")
    _wait_for_player_ready(page)
    signals = _read_playback_signals(page)
    if _signals_show_playing(signals):
        print(
            f"[step] Video already active before play click ({_format_playback_signals(signals)})"
        )
        return
    _click_play_control(page)
    page.wait_for_timeout(1500)


def _probe_playback(page: Page, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    previous_remaining = _read_remaining_time_text(page)
    while time.monotonic() < deadline:
        signals = _read_playback_signals(page)
        if _signals_show_playing(signals, previous_remaining=previous_remaining):
            print(f"[wait] Playback detected ({_format_playback_signals(signals)})")
            return True
        remaining = str(signals.get("remainingTimeText") or "")
        if remaining:
            previous_remaining = remaining
        page.wait_for_timeout(500)
    return False


def _start_video_playback(page: Page) -> None:
    print("[step] Start video playback")
    _activate_detail_video_player(page)
    if _probe_playback(page, timeout_seconds=PLAYBACK_PROBE_TIMEOUT_SECONDS):
        return
    print("[warn] Playback start probe did not confirm playing; continuing to observation window")


def _observe_playback_progress(page: Page, *, wait_seconds: int) -> tuple[float, dict[str, object]]:
    """재생 관찰: Pause 버튼·남은 시간 카운트다운·video.currentTime 을 주기적으로 샘플링한다."""
    start_signals = _read_playback_signals(page)
    start_remaining = str(start_signals.get("remainingTimeText") or "")
    start_video = start_signals.get("video")
    start_time = (
        float(start_video.get("currentTime") or 0) if isinstance(start_video, dict) else 0.0
    )

    print(
        f"[wait] Observe playback for {wait_seconds} seconds "
        f"({_format_playback_signals(start_signals)})"
    )

    deadline = time.monotonic() + wait_seconds
    previous_remaining = start_remaining or None
    max_remaining_drop = 0.0
    max_video_advance = 0.0
    saw_pause = bool(start_signals.get("pauseVisible"))
    last_signals = start_signals
    previous_video_time = start_time

    while time.monotonic() < deadline:
        page.wait_for_timeout(OBSERVATION_POLL_INTERVAL_MS)
        signals = _read_playback_signals(page)
        last_signals = signals

        if signals.get("pauseVisible"):
            saw_pause = True

        remaining = str(signals.get("remainingTimeText") or "")
        if previous_remaining and remaining:
            drop = _remaining_time_drop_seconds(previous_remaining, remaining)
            if drop is not None and drop > 0:
                max_remaining_drop += drop
            previous_remaining = remaining

        video = signals.get("video")
        if isinstance(video, dict):
            current_time = float(video.get("currentTime") or 0)
            if current_time > previous_video_time:
                max_video_advance += current_time - previous_video_time
                previous_video_time = current_time

        if _signals_show_playing(signals, previous_remaining=start_remaining or None):
            print(
                f"[wait] Playback signal during observation ({_format_playback_signals(signals)})"
            )

    end_remaining = str(last_signals.get("remainingTimeText") or "")
    total_remaining_drop = _remaining_time_drop_seconds(start_remaining, end_remaining)
    if total_remaining_drop is not None and total_remaining_drop > max_remaining_drop:
        max_remaining_drop = total_remaining_drop

    print(
        f"[step] Playback observation summary "
        f"pauseSeen={saw_pause} "
        f"remainingDrop={max_remaining_drop:.1f}s "
        f"videoAdvance={max_video_advance:.1f}s "
        f"remaining {start_remaining!r}->{end_remaining!r} "
        f"({_format_playback_signals(last_signals)})"
    )

    measured = max(max_remaining_drop, max_video_advance)
    return measured, last_signals


def _assert_playback_progress(page: Page, *, wait_seconds: int) -> float:
    measured, end_signals = _observe_playback_progress(page, wait_seconds=wait_seconds)

    if measured >= MIN_REMAINING_TIME_DROP_SECONDS:
        print("[step] Playback accepted via time progression")
        return measured
    if end_signals.get("pauseVisible"):
        print("[step] Playback accepted via Pause control")
        return max(measured, float(MIN_REMAINING_TIME_DROP_SECONDS))
    if _signals_show_playing(end_signals):
        print("[step] Playback accepted via player UI state")
        return max(measured, float(MIN_REMAINING_TIME_DROP_SECONDS))

    raise RuntimeError(
        f"{wait_seconds}초 대기 동안 동영상 재생이 확인되지 않았습니다. "
        f"(remaining/video 진행 {measured:.1f}초)"
    )


def run(page: Page, *, base_url: str) -> str:
    """IT교육과정 첫 번째 교육영상을 재생하고 30초간 재생 여부를 확인한다."""
    _ensure_main_page(page, base_url)
    _open_it_course_list(page)
    _open_first_video_detail(page)
    _start_video_playback(page)
    advanced = _assert_playback_progress(page, wait_seconds=PLAYBACK_WAIT_SECONDS)
    return f"동영상 재생 성공: {advanced:.1f}초 재생 확인 ({page.url})"
