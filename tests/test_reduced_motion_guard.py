"""움직임을 넣는 CSS 는 prefers-reduced-motion 가드를 동반해야 한다.

P2 에서 카운트업을 컴포넌트로 이관할 때 원본 dashboard.js 의 `if (REDUCED)`
가드를 빠뜨려 접근성 회귀를 만들었다. 그 재발을 막는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ANIMATED_CSS = [
    Path("app/web/frontend/components/status-badge/styles.css"),
    Path("app/web/frontend/components/kpi-card/styles.css"),
]


@pytest.mark.parametrize("path", ANIMATED_CSS, ids=lambda p: p.name)
def test_animation_is_guarded_by_reduced_motion(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    uses_motion = "animation" in source or "@keyframes" in source
    if not uses_motion:
        pytest.skip(f"{path} 에 움직임이 없다")
    assert "prefers-reduced-motion" in source, (
        f"{path} 가 애니메이션을 쓰는데 prefers-reduced-motion 가드가 없다."
    )


def test_status_badge_defines_running_and_waiting_input_motion() -> None:
    """설계 §3.4 — running 은 은은하게, waiting_input 은 눈에 띄게."""
    source = Path("app/web/frontend/components/status-badge/styles.css").read_text(encoding="utf-8")
    assert '[data-tone="running"]' in source
    assert '[data-tone="waiting_input"]' in source
    assert "@keyframes" in source


def test_reduced_motion_block_disables_animation() -> None:
    source = Path("app/web/frontend/components/status-badge/styles.css").read_text(encoding="utf-8")
    start = source.index("prefers-reduced-motion")
    block = source[start : start + 400]
    assert "animation: none" in block, block
