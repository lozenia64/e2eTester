"""톤 → 글리프 — 템플릿이 자체 맵을 들지 않게 한다.

_macros.html 이 10개짜리 글리프 딕셔너리를 들고 있었다. 톤이 하나 늘면
그 템플릿만 조용히 기본값(○)으로 떨어진다.
"""

from __future__ import annotations

from app.core.status_colors import TONE_GLYPHS
from app.core.status_labels import STATUS_TONES
from app.web.status_view import tone_glyph


def test_every_tone_has_a_glyph() -> None:
    missing = [tone for tone in STATUS_TONES if tone not in TONE_GLYPHS]
    assert not missing, f"TONE_GLYPHS 에 없는 톤: {missing}"


def test_no_extra_tones() -> None:
    extra = [tone for tone in TONE_GLYPHS if tone not in STATUS_TONES]
    assert not extra, f"STATUS_TONES 에 없는 톤: {extra}"


def test_lookup_returns_the_mapped_glyph() -> None:
    assert tone_glyph("passed") == "✓"
    assert tone_glyph("error") == "×"


def test_view_only_tone_folds_onto_pending() -> None:
    """not_inspected 는 화면 전용 파생 상태다 — 축을 늘리지 않고 pending 으로 접는다."""
    assert tone_glyph("not_inspected") == tone_glyph("pending")


def test_unknown_tone_falls_back_without_raising() -> None:
    """템플릿 렌더 중 예외는 화면 전체를 죽인다 — 모르는 톤은 중립 글리프로."""
    assert tone_glyph("no_such_tone") == TONE_GLYPHS["pending"]
