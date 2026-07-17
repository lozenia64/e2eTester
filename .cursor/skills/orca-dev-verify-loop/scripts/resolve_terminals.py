#!/usr/bin/env python3
"""Resolve Orca terminal handles for dev-verify loop (verifier + coordinator)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from orca_cli import configure_stdout_utf8, require_ok, run_orca

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = ROOT / ".cursor" / "orchestration" / "orca-loop.config.json"


def load_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "verifier_terminal_title_pattern": "Claude Code",
        "gates_profile": "full",
        "gates_command": "python3 scripts/ci/run_all_gates.py --profile full",
        "max_verify_iterations": 3,
        "wait_timeout_ms": 900000,
    }


def match_verifier(terminals: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
    lowered = pattern.lower()
    for term in terminals:
        title = str(term.get("title") or "")
        preview = str(term.get("preview") or "")
        haystack = f"{title}\n{preview}".lower()
        if lowered in haystack or "claude code" in haystack:
            return term
    return None


def resolve_coordinator(
    terminals: list[dict[str, Any]], explicit: str | None
) -> dict[str, Any] | None:
    if explicit:
        for term in terminals:
            if term.get("handle") == explicit:
                return term
        return {"handle": explicit, "title": "(explicit)"}
    for term in terminals:
        preview = str(term.get("preview") or "")
        title = str(term.get("title") or "")
        if "Composer" in preview or "Cursor" in title:
            return term
    for term in terminals:
        title = str(term.get("title") or "")
        if "powershell" in title.lower() and "claude" not in title.lower():
            return term
    return terminals[0] if terminals else None


def list_terminals(worktree: str | None = None) -> list[dict[str, Any]]:
    args = ["terminal", "list", "--json"]
    if worktree:
        args.extend(["--worktree", worktree])
    data = require_ok(run_orca(args))
    return list(data.get("result", {}).get("terminals") or [])


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Resolve Orca terminal handles")
    parser.add_argument("--workspace", default=str(ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--coordinator", default=None, help="Explicit coordinator handle")
    parser.add_argument("--verifier", default=None, help="Explicit verifier handle")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    pattern = str(config.get("verifier_terminal_title_pattern") or "Claude Code")
    terminals = list_terminals(args.workspace)

    verifier = None
    if args.verifier:
        verifier = next((t for t in terminals if t.get("handle") == args.verifier), None)
        if verifier is None:
            verifier = {"handle": args.verifier, "title": "(explicit)"}
    else:
        verifier = match_verifier(terminals, pattern)

    coordinator = resolve_coordinator(terminals, args.coordinator)

    out = {
        "ok": bool(verifier and coordinator),
        "verifier": verifier,
        "coordinator": coordinator,
        "terminals_found": len(terminals),
        "pattern": pattern,
    }
    if not verifier:
        out["error"] = f"no terminal matching verifier pattern: {pattern!r}"
    if not coordinator:
        out["error"] = "no coordinator terminal resolved"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
