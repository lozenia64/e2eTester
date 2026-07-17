#!/usr/bin/env python3
"""Read/write loop state and build role briefs for the plan-build-verify loop."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
BRIEFS_DIR = ROOT / ".cursor" / "skills" / "orca-plan-build-verify-loop" / "briefs"

BRIEF_FILES = {
    "cursor": BRIEFS_DIR / "cursor-implement-brief.md",
    "grok": BRIEFS_DIR / "grok-verify-brief.md",
    "claude": BRIEFS_DIR / "claude-final-verify-brief.md",
}


def read_loop(loop_dir: Path) -> dict[str, Any]:
    path = loop_dir / "loop.json"
    if not path.is_file():
        msg = f"missing loop.json: {path}"
        raise FileNotFoundError(msg)
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def write_loop(loop_dir: Path, data: dict[str, Any]) -> None:
    import json

    (loop_dir / "loop.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_trace(loop_dir: Path, line: str) -> None:
    trace = loop_dir / "trace.log"
    with trace.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip() + "\n")


def git_changed_files(workspace: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        proc2 = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        staged = [line.strip() for line in proc2.stdout.splitlines() if line.strip()]
        proc3 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        untracked = [line.strip() for line in proc3.stdout.splitlines() if line.strip()]
        return list(dict.fromkeys(names + staged + untracked))
    except OSError:
        return []


def build_spec(role: str, loop: dict[str, Any], *, feedback: str = "") -> str:
    """Render the brief markdown for `role` (cursor|grok|claude) with loop placeholders."""
    brief_path = BRIEF_FILES[role]
    template = brief_path.read_text(encoding="utf-8")
    handles = loop.get("handles") or {}
    plan_path = Path(str(loop.get("plan_path") or ""))
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    changed = loop.get("changed_files") or []
    changed_text = ", ".join(changed) if changed else "(none yet — check git diff)"

    replacements = {
        "{user_request}": str(loop.get("user_request") or ""),
        "{plan}": plan_text,
        "{plan_path}": str(loop.get("plan_path") or ""),
        "{loop_dir}": str(loop.get("loop_dir") or ""),
        "{claude_handle}": str(handles.get("claude") or ""),
        "{cursor_handle}": str(handles.get("cursor") or ""),
        "{grok_handle}": str(handles.get("grok") or ""),
        "{cursor_grok_iteration}": str(loop.get("cursor_grok_iteration") or 0),
        "{max_cursor_grok_iterations}": str(loop.get("max_cursor_grok_iterations") or 5),
        "{claude_gate_iteration}": str(loop.get("claude_gate_iteration") or 0),
        "{max_claude_gate_iterations}": str(loop.get("max_claude_gate_iterations") or 3),
        "{gates_command}": str(loop.get("gates_command") or ""),
        "{changed_files}": changed_text,
        "{feedback}": feedback or "(none — first pass)",
    }
    out = template
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out
