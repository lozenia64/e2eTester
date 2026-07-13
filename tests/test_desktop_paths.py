"""Tests for Desktop folder resolution."""

from __future__ import annotations

from pathlib import Path

from app.platform.desktop_paths import resolve_desktop_dir


def test_resolve_desktop_dir_returns_existing_directory(monkeypatch, tmp_path: Path) -> None:
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert resolve_desktop_dir() == desktop


def test_resolve_desktop_dir_prefers_onedrive_when_plain_missing(
    monkeypatch, tmp_path: Path
) -> None:
    onedrive = tmp_path / "OneDrive" / "Desktop"
    onedrive.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert resolve_desktop_dir() == onedrive
