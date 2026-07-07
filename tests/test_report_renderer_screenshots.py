"""메일 본문 스크린샷 크기 고정(Outlook 11cm)·세로형 2장 가로 배치 규칙 검증."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.notifications.report_renderer import (
    SCREENSHOT_MAX_HEIGHT_PX,
    SCREENSHOT_PAIR_MAX_WIDTH_PX,
    _screenshot_display_size,
    _screenshot_gallery,
    _screenshot_image_html,
)
from app.notifications.run_completion_email import _read_png_size


def _png_bytes(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = (
        (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    return signature + ihdr


def _screenshot(seq: int, width: int | None, height: int | None) -> dict:
    return {
        "cid": f"shot_{seq}@e2etester",
        "seq": seq,
        "order": seq * 10,
        "module_id": f"module_{seq}",
        "module_name": f"모듈{seq}",
        "system_code": "MHM",
        "status": "passed",
        "status_label": "정상",
        "image_width": width,
        "image_height": height,
    }


def test_read_png_size_parses_ihdr_dimensions() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "final.png"
        path.write_bytes(_png_bytes(390, 844))
        assert _read_png_size(path) == (390, 844)


def test_read_png_size_returns_none_for_non_png() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "final.png"
        path.write_bytes(b"not a png at all, definitely")
        assert _read_png_size(path) is None


def test_display_size_caps_portrait_height_to_11cm() -> None:
    width, height = _screenshot_display_size(390, 844)
    assert height == SCREENSHOT_MAX_HEIGHT_PX  # 96dpi 기준 11cm ≈ 416px
    assert width == round(390 * SCREENSHOT_MAX_HEIGHT_PX / 844)


def test_display_size_caps_landscape_width_and_height() -> None:
    width, height = _screenshot_display_size(1920, 912)
    assert width == 600
    assert height <= SCREENSHOT_MAX_HEIGHT_PX


def test_display_size_never_upscales_small_image() -> None:
    assert _screenshot_display_size(100, 50) == (100, 50)


def test_image_html_sets_outlook_size_attributes() -> None:
    html = _screenshot_image_html("cid:x@e2etester", "모듈", (192, 416))
    assert 'width="192"' in html
    assert 'height="416"' in html
    assert "width:192px;height:416px;" in html


def test_image_html_falls_back_without_known_size() -> None:
    html = _screenshot_image_html("cid:x@e2etester", "모듈", None)
    assert 'width="600"' in html
    assert "max-width:600px" in html
    assert "height:auto" in html


def test_gallery_pairs_consecutive_portrait_screenshots() -> None:
    gallery = _screenshot_gallery([_screenshot(1, 390, 844), _screenshot(2, 390, 844)])
    # 세로형 2장은 50% 셀 2개짜리 한 행에 나란히 배치된다.
    assert gallery.count('td width="50%"') == 2
    assert "cid:shot_1@e2etester" in gallery
    assert "cid:shot_2@e2etester" in gallery
    assert f'height="{SCREENSHOT_MAX_HEIGHT_PX}"' in gallery
    pair_width = round(390 * SCREENSHOT_MAX_HEIGHT_PX / 844)
    assert pair_width <= SCREENSHOT_PAIR_MAX_WIDTH_PX
    assert f'width="{pair_width}"' in gallery


def test_gallery_keeps_landscape_full_width_between_portraits() -> None:
    gallery = _screenshot_gallery(
        [
            _screenshot(1, 1920, 912),
            _screenshot(2, 390, 844),
            _screenshot(3, 390, 844),
        ]
    )
    # 가로형 1장은 전체 폭 카드, 세로형 2장은 한 행으로 묶인다.
    assert gallery.count('td width="50%"') == 2
    assert 'width="600"' in gallery


def test_gallery_lone_portrait_keeps_pair_cell_width() -> None:
    gallery = _screenshot_gallery([_screenshot(1, 390, 844)])
    assert gallery.count('td width="50%"') == 2
    assert "&nbsp;" in gallery


def test_gallery_unknown_size_renders_fallback_full_width() -> None:
    gallery = _screenshot_gallery([_screenshot(1, None, None)])
    assert 'td width="50%"' not in gallery
    assert 'width="600"' in gallery
    assert "height:auto" in gallery
