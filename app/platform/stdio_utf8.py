"""Cross-platform UTF-8 console configuration for CLI entrypoints."""

from __future__ import annotations

import os
import sys


def configure_stdio_utf8(*, env: dict[str, str] | None = None) -> None:
    """Ensure Korean and other non-ASCII text renders correctly on Windows consoles."""
    target_env = env if env is not None else os.environ
    target_env.setdefault("PYTHONUTF8", "1")
    target_env.setdefault("PYTHONIOENCODING", "utf-8")

    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
