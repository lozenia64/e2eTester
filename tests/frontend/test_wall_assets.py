"""상황판 자산 — 다중 엔트리와 접근성 가드.

P1 §3.2 가 페이지별 Vite 엔트리 구조를 설계했지만 소비자가 없어 검증되지 않았다.
상황판이 첫 소비자다 — 동작하지 않으면 P1 설계에 결함이 있다는 뜻이다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.web.asset_manifest import AssetManifest

MANIFEST = Path("app/web/static/dist/.vite/manifest.json")
WALL_CSS = Path("app/web/frontend/styles/wall.css")
ASSET_MANIFEST = AssetManifest(MANIFEST, base_url="/static/dist")


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.exists(), f"{MANIFEST} 가 없습니다. `npm run build` 를 먼저 실행하세요."
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _resolved_css(entry: str) -> str:
    return "\n".join(
        (Path("app/web/static/dist") / url.removeprefix("/static/dist/")).read_text(
            encoding="utf-8"
        )
        for url in ASSET_MANIFEST.css_urls(entry)
    )


def test_wall_entry_resolves_in_asset_manifest() -> None:
    assert ASSET_MANIFEST.js_url("entries/wall.ts").startswith("/static/dist/assets/")


def test_wall_entry_has_its_own_css() -> None:
    css = ASSET_MANIFEST.css_urls("entries/wall.ts")
    assert css, "상황판 엔트리에 CSS 산출물이 없습니다."


def test_wall_resolved_css_carries_kpi_card_styles() -> None:
    assert ".kpi-card" in _resolved_css("entries/wall.ts")


def test_main_resolved_css_carries_kpi_card_styles() -> None:
    assert ".kpi-card" in _resolved_css("entries/main.ts")


def test_wall_resolved_css_carries_large_card_variant() -> None:
    """상황판은 KpiCard 를 대형 모드로 쓴다(설계 §3.5) — 그 규칙이 실제로 실려야 한다.

    `.kpi-card` 기본 규칙만 검사하면(위 테스트) `data-size="lg"` 블록이 지워져도
    통과한다. 그러면 3~5m 거리용 카드가 조용히 일간 현황 크기로 작아진다.

    빌드 CSS 는 미니파이되어 속성 선택자의 인용부호가 벗겨진다(`data-size=lg`).
    소스 형태(`data-size="lg"`)로만 찾으면 기능이 정상인데도 실패한다.
    """
    css = _resolved_css("entries/wall.ts")
    assert re.search(r'data-size\s*=\s*"?lg"?', css), (
        "상황판 번들에 대형 카드 규칙이 없습니다. "
        'kpi-card/styles.css 의 [data-size="lg"] 블록과 '
        "entries/wall.ts 의 kpi-card 스타일 임포트를 확인하세요."
    )


def test_main_bundle_does_not_carry_wall_styles() -> None:
    """일반 페이지 번들에 상황판 전용 무게를 얹지 않는다(설계 §3.7)."""
    assert ".wall-hero" not in _resolved_css("entries/main.ts")


def test_wall_css_has_no_hardcoded_hex() -> None:
    """FG-002 — 색은 토큰만."""
    source = WALL_CSS.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)


def test_wall_css_guards_reduced_motion() -> None:
    source = WALL_CSS.read_text(encoding="utf-8")
    if "animation" not in source:
        pytest.skip("wall.css 에 움직임이 없다")
    assert "prefers-reduced-motion" in source
    start = source.index("prefers-reduced-motion")
    assert "animation: none" in source[start : start + 400]


def test_wall_css_is_nonscrolling() -> None:
    source = WALL_CSS.read_text(encoding="utf-8")
    assert "overflow: hidden" in source
    assert "100dvh" in source
