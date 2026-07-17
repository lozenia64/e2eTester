#!/usr/bin/env python3
"""Initialize a plan-build-verify loop session (run by Claude Code)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loop_state import git_changed_files
from orca_cli import configure_stdout_utf8

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / ".cursor" / "orchestration" / "plan-build-verify-loop.config.json"

LOOP_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def load_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def resolve_handles(
    workspace: Path,
    config_path: Path,
    claude_handle: str | None,
    cursor_handle: str | None,
    grok_handle: str | None,
) -> dict[str, Any]:
    script = SCRIPTS / "resolve_terminals.py"
    cmd = [sys.executable, str(script), "--workspace", str(workspace), "--config", str(config_path)]
    if claude_handle:
        cmd.extend(["--claude-handle", claude_handle])
    if cursor_handle:
        cmd.extend(["--cursor-handle", cursor_handle])
    if grok_handle:
        cmd.extend(["--grok-handle", grok_handle])
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    data = json.loads(proc.stdout or "{}")
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or proc.stderr or "resolve_terminals failed")
    return {role: v.get("handle") for role, v in data["handles"].items()}


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Initialize plan-build-verify loop")
    parser.add_argument("workspace", help="Project workspace root")
    parser.add_argument("user_request", help="Original user requirement (short)")
    parser.add_argument(
        "--plan-file", required=True, help="Path to the plan markdown Claude Code wrote"
    )
    parser.add_argument("--loop-id", default=None, help="Optional 8-char hex loop id")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--claude-handle", default=None)
    parser.add_argument("--cursor-handle", default=None)
    parser.add_argument("--grok-handle", default=None)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    config_path = Path(args.config)
    config = load_config(config_path)

    if args.loop_id is not None:
        if not LOOP_ID_PATTERN.fullmatch(args.loop_id):
            print(json.dumps({"error": "loop-id must be 8 lowercase hex chars"}))
            return 1
        loop_id = args.loop_id
    else:
        loop_id = str(uuid.uuid4())[:8]

    loop_dir = workspace / ".cursor" / "orchestration" / "loops" / loop_id
    loop_dir.mkdir(parents=True, exist_ok=True)

    plan_src = Path(args.plan_file).resolve()
    if not plan_src.is_file():
        print(json.dumps({"error": f"plan file not found: {plan_src}"}))
        return 1
    plan_dst = loop_dir / "plan.md"
    shutil.copyfile(plan_src, plan_dst)

    handles = resolve_handles(
        workspace, config_path, args.claude_handle, args.cursor_handle, args.grok_handle
    )

    now = datetime.now(UTC).isoformat()
    loop_json: dict[str, Any] = {
        "loop_id": loop_id,
        "loop_dir": str(loop_dir),
        "workspace": str(workspace),
        "user_request": args.user_request,
        "plan_path": str(plan_dst),
        "pattern": "orca_plan_build_verify_loop",
        "orchestrator": "orca-plan-build-verify-loop",
        "status": "initialized",
        "phase": "init",
        "handles": handles,
        "cursor_grok_iteration": 0,
        "claude_gate_iteration": 0,
        "max_cursor_grok_iterations": int(config.get("max_cursor_grok_iterations") or 5),
        "max_claude_gate_iterations": int(config.get("max_claude_gate_iterations") or 3),
        "gates_command": config.get(
            "gates_command", "python3 scripts/ci/run_all_gates.py --profile full"
        ),
        "changed_files": git_changed_files(workspace),
        "last_task_id": None,
        "last_dispatch_id": None,
        "last_dispatch_to": None,
        "last_verdict": None,
        "history": [],
        "created_at": now,
        "updated_at": now,
    }

    (loop_dir / "loop.json").write_text(
        json.dumps(loop_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (loop_dir / "trace.log").write_text(
        f"{now} init loop_id={loop_id} handles={handles}\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "loop_id": loop_id,
                "loop_dir": str(loop_dir),
                "handles": handles,
                "max_cursor_grok_iterations": loop_json["max_cursor_grok_iterations"],
                "max_claude_gate_iterations": loop_json["max_claude_gate_iterations"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
