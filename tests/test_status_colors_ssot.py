"""상태 색 SSOT — 화면과 메일이 같은 출처를 본다.

팔레트가 scripts/gen_frontend_tokens.py 안에 있던 동안 메일은 그 값을 쓸 수 없었다
(앱이 빌드 스크립트를 import 하는 것은 방향이 거꾸로다). 그래서 메일이 자기 hex 를
따로 들고 있었고, 같은 상태를 화면과 다른 색으로 말했다.
"""

from __future__ import annotations

import re

from app.core.status_colors import PALETTE
from app.core.status_labels import STATUS_TONES

_HEX = re.compile(r"^#[0-9a-f]{6}$")
_VARIANTS = ("solid", "surface", "text", "border")


def test_palette_covers_every_tone() -> None:
    """톤이 하나 늘었는데 색이 없으면 화면이 조용히 회색으로 떨어진다."""
    missing = [tone for tone in STATUS_TONES if tone not in PALETTE]
    assert not missing, f"PALETTE 에 없는 톤: {missing}"


def test_palette_has_no_extra_tones() -> None:
    extra = [tone for tone in PALETTE if tone not in STATUS_TONES]
    assert not extra, f"STATUS_TONES 에 없는 톤: {extra}"


def test_every_tone_has_all_four_variants() -> None:
    for tone, variants in PALETTE.items():
        assert set(variants) == set(_VARIANTS), tone


def test_every_value_is_a_lowercase_six_digit_hex() -> None:
    """생성기가 CSS 로 그대로 찍으므로 형식이 어긋나면 토큰이 깨진다."""
    for tone, variants in PALETTE.items():
        for name, value in variants.items():
            assert _HEX.match(value), f"{tone}.{name} = {value!r}"


def test_generator_reads_the_shared_palette() -> None:
    """생성기가 자기 사본을 되살리면 SSOT 가 다시 둘로 갈라진다."""
    import scripts.gen_frontend_tokens as generator

    assert generator.PALETTE is PALETTE
