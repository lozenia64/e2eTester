"""모듈 이상징후(ANOMALY) 시 화면 HTML 진단 덤프.

셀렉터 수정을 위해 execution.log 에 페이지/오버레이 HTML 을 남긴다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.runner.step_logging import log

PAGE_HTML_ARTIFACT_NAME = "page.html"
_DIAGNOSTIC_HTML_BEGIN = "[diagnostic] page_html_begin"
_DIAGNOSTIC_HTML_END = "[diagnostic] page_html_end"
_DIAGNOSTIC_OVERLAY_BEGIN = "[diagnostic] overlay_html_begin"
_DIAGNOSTIC_OVERLAY_END = "[diagnostic] overlay_html_end"

_OVERLAY_SELECTOR = (
    ".modal_popup, .modal_wrap, .pop_wrap, .popup_wrap, .layer_popup, "
    ".ui_popup, .pop_round, .pop_modal1, [role='dialog'], "
    "[class*='popup'], [class*='layer'], #uiPOPGmea000, #uiPOPCustInfoChg"
)


def _emit_multiline(log_fn: Callable[[str], None], begin: str, body: str, end: str) -> None:
    log_fn(begin)
    for line in body.splitlines():
        log_fn(line)
    log_fn(end)


def capture_page_html_diagnostic(
    page: object,
    artifact_dir: Path,
    log_fn: Callable[[str], None],
) -> None:
    """이상징후 시점의 페이지 HTML 을 아티팩트 + execution.log 에 기록한다."""
    try:
        page_url = str(page.url)  # type: ignore[attr-defined]
    except Exception:
        page_url = "(unknown)"

    try:
        html = page.content()  # type: ignore[attr-defined]
    except Exception as exc:
        log_fn(f"[diagnostic] page HTML capture failed: {exc}")
        return

    artifact_dir.mkdir(parents=True, exist_ok=True)
    html_path = artifact_dir / PAGE_HTML_ARTIFACT_NAME
    try:
        html_path.write_text(html, encoding="utf-8")
    except Exception as exc:
        log_fn(f"[diagnostic] page HTML artifact write failed: {exc}")
        return

    log_fn(
        f"[diagnostic] anomaly page HTML captured url={page_url} "
        f"bytes={len(html.encode('utf-8'))} artifact={PAGE_HTML_ARTIFACT_NAME}"
    )
    _emit_multiline(log_fn, _DIAGNOSTIC_HTML_BEGIN, html, _DIAGNOSTIC_HTML_END)

    try:
        overlays: list[dict[str, str]] = page.evaluate(  # type: ignore[attr-defined]
            """
            (selector) => {
                const isVisible = (element) => {
                    if (!element) {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0;
                };

                const seen = new Set();
                const overlays = [];
                for (const element of document.querySelectorAll(selector)) {
                    if (!isVisible(element) || seen.has(element)) {
                        continue;
                    }
                    seen.add(element);
                    overlays.push({
                        id: element.id || '',
                        className: element.className || '',
                        tag: element.tagName || '',
                        html: element.outerHTML || '',
                    });
                }
                return overlays;
            }
            """,
            _OVERLAY_SELECTOR,
        )
    except Exception as exc:
        log_fn(f"[diagnostic] overlay HTML capture failed: {exc}")
        return

    if not overlays:
        log_fn("[diagnostic] no visible overlay/modal HTML detected")
        return

    log_fn(f"[diagnostic] visible overlay count={len(overlays)}")
    for index, overlay in enumerate(overlays):
        overlay_id = overlay.get("id") or "-"
        overlay_class = overlay.get("className") or "-"
        overlay_tag = overlay.get("tag") or "-"
        overlay_html = overlay.get("html") or ""
        log_fn(
            f"[diagnostic] overlay index={index} tag={overlay_tag} "
            f"id={overlay_id} class={overlay_class} bytes={len(overlay_html.encode('utf-8'))}"
        )
        _emit_multiline(
            log_fn,
            f"{_DIAGNOSTIC_OVERLAY_BEGIN} index={index}",
            overlay_html,
            f"{_DIAGNOSTIC_OVERLAY_END} index={index}",
        )


def capture_page_html_diagnostic_safe(
    page: object,
    artifact_dir: Path,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """HTML 덤프 실패가 모듈 결과를 가리지 않도록 예외를 삼킨다."""
    sink = log_fn or log
    try:
        capture_page_html_diagnostic(page, artifact_dir, sink)
    except Exception as exc:
        sink(f"[diagnostic] page HTML capture aborted: {exc}")
