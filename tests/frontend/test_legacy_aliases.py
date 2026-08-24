"""레거시 짧은 별칭이 실재하는 SSOT 토큰을 가리키는지.

별칭은 이름만 이어 붙인다. 대상 토큰이 사라지거나 이름이 바뀌면 `var()` 가
미정의가 되고, CSS 는 그 선언을 통째로 무효화한다 — 화면에서 색이 조용히
사라진다. 그 순간을 여기서 잡는다.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "app/web/frontend/styles"
ALIAS_CSS = STYLES / "legacy-aliases.css"
BASE_CSS = STYLES / "base.css"
SOURCES = (STYLES / "tokens.generated.css", STYLES / "primitives.css")

_ALIAS_RE = re.compile(r"^\s*(--[\w-]+)\s*:\s*var\(\s*(--[\w-]+)\s*\)\s*;")
_DEFINE_RE = re.compile(r"^\s*(--[\w-]+)\s*:")


def _aliases() -> dict[str, str]:
    pairs = {}
    for line in ALIAS_CSS.read_text(encoding="utf-8").splitlines():
        match = _ALIAS_RE.match(line)
        if match:
            pairs[match.group(1)] = match.group(2)
    return pairs


def _defined_elsewhere() -> set[str]:
    names = set()
    for path in SOURCES:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _DEFINE_RE.match(line)
            if match:
                names.add(match.group(1))
    return names


def test_alias_file_exists() -> None:
    assert ALIAS_CSS.exists(), "legacy-aliases.css 가 없다"


def test_every_alias_target_is_defined() -> None:
    aliases = _aliases()
    assert aliases, "별칭 선언이 하나도 파싱되지 않았다"
    defined = _defined_elsewhere()
    dangling = {name: target for name, target in aliases.items() if target not in defined}
    assert not dangling, f"가리키는 토큰이 없는 별칭: {dangling}"


def test_alias_file_has_no_hex() -> None:
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", ALIAS_CSS.read_text(encoding="utf-8"))
    assert not hexes, f"별칭 파일에 hex: {hexes}"


def test_status_aliases_point_at_solid_variants() -> None:
    aliases = _aliases()
    for tone in ("passed", "anomaly", "error", "running", "cancelled", "blocked"):
        assert aliases[f"--st-{tone}"] == f"--st-{tone}-solid"


def test_base_css_imports_the_alias_file() -> None:
    text = BASE_CSS.read_text(encoding="utf-8")
    assert '@import "./legacy-aliases.css";' in text
