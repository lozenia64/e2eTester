"""넌스크롤 셸의 소유권 — 세 화면이 같은 규칙을 각자 복제하지 않는다.

dashboard.css 와 execute.css 가 같은 body:has(...) 블록을 한 벌씩 갖고 있었다.
세 번째 소비자(.suite)가 생기는 시점에 공통으로 뽑는다(설계 D7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "app/web/frontend/styles"
SHELL = STYLES / "shell.css"


def _text(name: str) -> str:
    return (STYLES / name).read_text(encoding="utf-8")


def test_shell_file_exists() -> None:
    assert SHELL.exists()


@pytest.mark.parametrize(
    "selector",
    ["body:has(.dash)", "body:has(.exec)", "body:has(.suite)", "body:has(.run)"],
)
def test_shell_owns_all_screens(selector: str) -> None:
    assert selector in _text("shell.css")


@pytest.mark.parametrize("name", ["dashboard.css", "execute.css"])
def test_screen_stylesheets_no_longer_own_the_shell(name: str) -> None:
    """복제가 남아 있으면 한쪽만 고쳤을 때 조용히 갈라진다."""
    assert "body:has(" not in _text(name)


def test_base_css_imports_shell_before_screen_sheets() -> None:
    """셸이 화면 시트보다 먼저 와야 화면 시트가 덮어쓸 수 있다."""
    base = _text("base.css")
    assert '@import "./shell.css";' in base
    assert base.index('@import "./shell.css";') < base.index('@import "./dashboard.css";')


def test_shell_has_no_hex() -> None:
    import re

    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", _text("shell.css"))
