"""OS-specific browser profile directory resolution."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_user_data_root() -> Path:
    return Path.home() / ".e2etester"


def resolve_legacy_profile(profile_name: str, *, override: str | None) -> Path:
    if override:
        target = Path(override).expanduser()
    else:
        target = default_user_data_root() / profile_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def playwright_mcp_profiles_root() -> Path:
    """Cursor Playwright MCP persistent profile root (matches @playwright/mcp layout)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / "ms-playwright-mcp"


def normalize_workspace_for_hash(path: Path) -> str:
    """Stable workspace token across macOS/Windows path separators and casing."""
    return str(path.expanduser().resolve().as_posix()).lower()
