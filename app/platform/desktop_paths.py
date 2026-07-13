"""Resolve the user's Desktop folder across OS locales and OneDrive redirects."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_desktop_dir() -> Path:
    home = Path.home()
    candidates: list[Path] = [home / "Desktop"]
    if sys.platform == "win32":
        candidates.extend(
            [
                home / "OneDrive" / "Desktop",
                home / "OneDrive - Personal" / "Desktop",
            ]
        )
        for child in home.iterdir():
            try:
                if child.is_dir() and child.name.lower().startswith("onedrive"):
                    candidates.append(child / "Desktop")
            except OSError:
                continue
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]
