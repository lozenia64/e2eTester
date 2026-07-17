#!/usr/bin/env python3
"""Build verifier dispatch spec from loop state and template."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
BRIEF_PATH = ROOT / ".cursor" / "skills" / "orca-dev-verify-loop" / "verifier-brief.md"


def read_loop(loop_dir: Path) -> dict[str, Any]:
    path = loop_dir / "loop.json"
    if not path.is_file():
        msg = f"missing loop.json: {path}"
        raise FileNotFoundError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def write_loop(loop_dir: Path, data: dict[str, Any]) -> None:
    (loop_dir / "loop.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_verifier_spec(loop: dict[str, Any], *, iteration: int) -> str:
    template = BRIEF_PATH.read_text(encoding="utf-8")
    changed = loop.get("changed_files") or []
    if isinstance(changed, list):
        changed_text = ", ".join(changed) if changed else "(none yet — check git diff)"
    else:
        changed_text = str(changed)
    return (
        template.replace("{user_request}", str(loop.get("user_request") or ""))
        .replace("{loop_dir}", str(loop.get("loop_dir") or ""))
        .replace("{iteration}", str(iteration))
        .replace("{max_iterations}", str(loop.get("max_iterations") or 3))
        .replace("{changed_files}", changed_text)
        .replace("{gates_command}", str(loop.get("gates_command") or ""))
    )


def append_trace(loop_dir: Path, line: str) -> None:
    trace = loop_dir / "trace.log"
    with trace.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip() + "\n")
