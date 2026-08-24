"""상태 팔레트가 하나인지 — 템플릿과 레거시 JS 에 사본이 없는지.

발견 당시 실측: 템플릿 7개가 `--st-passed` 등을 각자 정의했고, 값이 SSOT 와
달랐다(#0ca30c vs #10b981). 이름이 같아서 화면 안에서는 일관돼 보이고 화면을
넘어갈 때만 어긋난다 — 눈으로 잡기 가장 어려운 형태였다.

FG-002 는 hex 자체를 막는다(범위가 넓다). 이 테스트는 **상태 팔레트의 사본**
이라는 특정 병만 본다(범위가 좁고 메시지가 구체적이다). 둘 다 필요하다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.status_colors import PALETTE

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "app/web/templates"
STATIC_DIR = REPO_ROOT / "app/web/static"

# 화면들이 각자 정의하던 짧은 이름. `--st-passed:` 처럼 콜론이 붙은 정의만 잡는다
# (`var(--st-passed)` 사용처는 이 사이클의 대상이 아니다).
SHORT_TOKENS = (
    "--st-passed",
    "--st-anomaly",
    "--st-error",
    "--st-running",
    "--st-cancelled",
    "--st-blocked",
    "--st-idle",
    "--st-track",
    "--st-active",
    "--ease-spring",
)

# 발견 당시 로그 팔레트의 실제 값. 되살아나면 잡는다.
ROGUE_HEX = ("#0ca30c", "#fab219", "#d03b3b", "#2a78d6", "#ec835a", "#b6b4ad", "#ecebe6")


def _templates() -> list[Path]:
    return sorted(TEMPLATE_DIR.rglob("*.html"))


def _legacy_scripts() -> list[Path]:
    """static/ 최상위의 손으로 쓴 스크립트만. dist/ 는 빌드 산출물이라 제외한다."""
    return sorted(STATIC_DIR.glob("*.js"))


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_no_template_defines_a_short_status_token(token: str) -> None:
    pattern = re.compile(rf"^\s*{re.escape(token)}\s*:")
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}"
        for path in _templates()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.match(line)
    ]
    assert not offenders, f"{token} 을 정의하는 템플릿: {offenders}"


@pytest.mark.parametrize("value", ROGUE_HEX)
def test_rogue_palette_value_is_gone(value: str) -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}"
        for path in [*_templates(), *_legacy_scripts()]
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if value in line
    ]
    assert not offenders, f"로그 팔레트 값 {value}: {offenders}"


def test_ssot_values_are_not_copied_into_templates() -> None:
    """SSOT 값을 템플릿에 '올바르게' 베껴 넣는 것도 사본이다 — 다음 변경 때 갈라진다."""
    ssot_values = {variants["solid"] for variants in PALETTE.values()}
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno} {value}"
        for path in _templates()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for value in ssot_values
        if value in line
    ]
    assert not offenders, f"SSOT 색을 베낀 자리: {offenders}"
