"""Tests for Desktop folder resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.platform.desktop_paths import resolve_desktop_dir


def test_resolve_desktop_dir_returns_existing_directory(monkeypatch, tmp_path: Path) -> None:
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert resolve_desktop_dir() == desktop


@pytest.mark.skipif(sys.platform != "win32", reason="OneDrive scan is Windows-only")
def test_resolve_desktop_dir_skips_inaccessible_onedrive_children(
    monkeypatch, tmp_path: Path
) -> None:
    good = tmp_path / "OneDrive"
    good.mkdir()
    (good / "Desktop").mkdir()

    class BlockedEntry:
        name = "OneDrive-Bad"

        def is_dir(self) -> bool:
            raise OSError("reparse point")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda self: iter([BlockedEntry(), good]) if self == tmp_path else Path.iterdir(self),
    )
    assert resolve_desktop_dir() == good / "Desktop"


@pytest.mark.skipif(sys.platform != "win32", reason="OneDrive Desktop redirect is Windows-only")
def test_resolve_desktop_dir_prefers_onedrive_when_plain_missing(
    monkeypatch, tmp_path: Path
) -> None:
    onedrive = tmp_path / "OneDrive" / "Desktop"
    onedrive.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert resolve_desktop_dir() == onedrive
