#!/usr/bin/env python3
"""Resolve Orca terminal handles for the plan-build-verify loop (claude/cursor/grok)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from orca_cli import configure_stdout_utf8, require_ok, run_orca

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = ROOT / ".cursor" / "orchestration" / "plan-build-verify-loop.config.json"

ROLES = ("claude", "cursor", "grok")


def load_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "claude_terminal_title_pattern": "Claude Code",
        "claude_preview_patterns": ["Perusing", "Pondering", "Claude Code"],
        "cursor_terminal_title_pattern": "Cursor",
        "cursor_preview_patterns": ["Composer", "cursor-agent"],
        "grok_terminal_title_pattern": "grok",
        "grok_preview_patterns": ["Grok 4"],
    }


def list_terminals(worktree: str | None = None) -> list[dict[str, Any]]:
    args = ["terminal", "list", "--json"]
    if worktree:
        args.extend(["--worktree", worktree])
    data = require_ok(run_orca(args))
    return list(data.get("result", {}).get("terminals") or [])


def haystack(term: dict[str, Any]) -> str:
    title = str(term.get("title") or "")
    preview = str(term.get("preview") or "")
    return f"{title}\n{preview}".lower()


def matches(term: dict[str, Any], title_pattern: str, preview_patterns: list[str]) -> bool:
    hay = haystack(term)
    if title_pattern and title_pattern.lower() in hay:
        return True
    return any(p.lower() in hay for p in preview_patterns)


def resolve_role(
    role: str,
    terminals: list[dict[str, Any]],
    config: dict[str, Any],
    excluded_handles: set[str],
) -> dict[str, Any] | None:
    title_pattern = str(config.get(f"{role}_terminal_title_pattern") or "")
    preview_patterns = [str(p) for p in (config.get(f"{role}_preview_patterns") or [])]
    for term in terminals:
        handle = str(term.get("handle") or "")
        if handle in excluded_handles:
            continue
        if matches(term, title_pattern, preview_patterns):
            return term
    return None


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(
        description="Resolve Orca terminal handles for claude/cursor/grok"
    )
    parser.add_argument("--workspace", default=str(ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--claude-handle", default=None, help="Explicit Claude Code handle override"
    )
    parser.add_argument("--cursor-handle", default=None, help="Explicit Cursor handle override")
    parser.add_argument("--grok-handle", default=None, help="Explicit Grok handle override")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    terminals = list_terminals(args.workspace)
    by_handle = {str(t.get("handle")): t for t in terminals}

    overrides = {
        "claude": args.claude_handle,
        "cursor": args.cursor_handle,
        "grok": args.grok_handle,
    }

    resolved: dict[str, dict[str, Any] | None] = {}
    excluded: set[str] = set()

    # Cursor first (strongest signature: "Composer"), then grok (exact title),
    # then claude last so it never accidentally swallows the other two.
    order = ["cursor", "grok", "claude"]
    for role in order:
        if overrides[role]:
            handle = overrides[role]
            resolved[role] = by_handle.get(handle) or {"handle": handle, "title": "(explicit)"}
        else:
            resolved[role] = resolve_role(role, terminals, config, excluded)
        if resolved[role]:
            excluded.add(str(resolved[role].get("handle")))

    out = {
        "ok": all(resolved[r] is not None for r in ROLES),
        "handles": {r: resolved[r] for r in ROLES},
        "terminals_found": len(terminals),
    }
    missing = [r for r in ROLES if resolved[r] is None]
    if missing:
        out["error"] = f"could not resolve terminal(s) for role(s): {', '.join(missing)}"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
