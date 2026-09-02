"""넌스크롤 셸의 소유권 — 세 화면이 같은 규칙을 각자 복제하지 않는다.

dashboard.css 와 execute.css 가 같은 body:has(...) 블록을 한 벌씩 갖고 있었다.
세 번째 소비자(.suite)가 생기는 시점에 공통으로 뽑는다(설계 D7).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "app/web/frontend/styles"
SHELL = STYLES / "shell.css"


def _text(name: str) -> str:
    return (STYLES / name).read_text(encoding="utf-8")


def test_shell_file_exists() -> None:
    assert SHELL.exists()


def _shell_screen_selectors() -> str:
    """shell.css 가 body:has(...) 로 거는 화면 클래스 전부.

    소비자가 다섯이 되면서 블록마다 나열하던 것을 :has() 셀렉터 목록으로
    접었다(Cycle 4). 계약은 "셸이 모든 화면을 소유한다"이지 철자가 아니므로,
    리터럴 대신 셀렉터 안에 클래스가 있는지로 단언한다.
    """
    css = re.sub(r"/\*.*?\*/", "", _text("shell.css"), flags=re.S)
    return " ".join(re.findall(r"body:has\(([^)]*)\)", css))


@pytest.mark.parametrize("screen", [".dash", ".exec", ".suite", ".run", ".rhist"])
def test_shell_owns_all_screens(screen: str) -> None:
    assert screen in _shell_screen_selectors()


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
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", _text("shell.css"))
