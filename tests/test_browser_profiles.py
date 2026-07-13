"""Tests for OS-specific browser profile directory resolution."""

from __future__ import annotations

import sys
from pathlib import Path

from app.platform import browser_profiles


def test_playwright_mcp_profiles_root_windows(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\test\AppData\Local")
    root = browser_profiles.playwright_mcp_profiles_root()
    assert root == Path(r"C:\Users\test\AppData\Local") / "ms-playwright-mcp"


def test_playwright_mcp_profiles_root_darwin(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    root = browser_profiles.playwright_mcp_profiles_root()
    assert root == Path.home() / "Library" / "Application Support" / "ms-playwright-mcp"


def test_normalize_workspace_for_hash_is_lowercase_posix(tmp_path: Path) -> None:
    workspace = tmp_path / "Repo"
    workspace.mkdir()
    token = browser_profiles.normalize_workspace_for_hash(workspace)
    assert token == str(workspace.resolve().as_posix()).lower()
