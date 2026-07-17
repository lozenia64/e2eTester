#!/usr/bin/env python3
"""Dispatch the next hop of the plan-build-verify loop (cursor|grok|claude)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from loop_state import append_trace, build_spec, git_changed_files, read_loop, write_loop
from orca_cli import configure_stdout_utf8, require_ok, run_orca

ROOT = Path(__file__).resolve().parents[4]

ITER_KEY = {
    "cursor": "cursor_grok_iteration",
    "grok": "cursor_grok_iteration",
    "claude": "claude_gate_iteration",
}
MAX_KEY = {
    "cursor": "max_cursor_grok_iterations",
    "grok": "max_cursor_grok_iterations",
    "claude": "max_claude_gate_iterations",
}
PHASE_AFTER = {
    "cursor": "cursor_implementing",
    "grok": "grok_verifying",
    "claude": "claude_final_verifying",
}


def read_feedback(args: argparse.Namespace) -> str:
    if args.feedback_file:
        return Path(args.feedback_file).read_text(encoding="utf-8")
    return args.feedback or ""


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Dispatch next hop of the plan-build-verify loop")
    parser.add_argument("--loop-dir", required=True)
    parser.add_argument("--to", required=True, choices=["cursor", "grok", "claude"])
    parser.add_argument("--feedback", default=None, help="Inline feedback text (e.g. prior FAIL reasons)")
    parser.add_argument("--feedback-file", default=None, help="Path to a file with feedback text")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    loop_dir = Path(args.loop_dir).resolve()
    loop = read_loop(loop_dir)
    workspace = Path(loop["workspace"])

    handles = loop.get("handles") or {}
    target_handle = handles.get(args.to)
    if not target_handle:
        print(json.dumps({"ok": False, "error": f"no resolved handle for target={args.to}"}))
        return 1

    iter_key = ITER_KEY[args.to]
    max_key = MAX_KEY[args.to]
    iteration = int(loop.get(iter_key) or 0) + 1
    max_iter = int(loop.get(max_key) or 5)
    if iteration > max_iter:
        print(json.dumps({"ok": False, "error": f"max iterations for {iter_key} ({max_iter}) exceeded"}))
        return 1

    loop[iter_key] = iteration
    loop["changed_files"] = git_changed_files(workspace)
    feedback = read_feedback(args)
    spec = build_spec(args.to, loop, feedback=feedback)

    loop_id = loop["loop_id"]
    title = f"{args.to}-{loop_id}-{iteration}"
    create = require_ok(
        run_orca(
            [
                "orchestration",
                "task-create",
                "--spec",
                spec,
                "--task-title",
                title,
                "--display-name",
                f"{args.to} #{iteration}",
                "--json",
            ]
        )
    )
    task_id = create["result"]["task"]["id"]

    dispatch_args = ["orchestration", "dispatch", "--task", task_id, "--to", target_handle, "--json"]
    if args.dry_run:
        dispatch_args.extend(["--dry-run", "--return-preamble"])
    else:
        dispatch_args.append("--inject")

    dispatch = require_ok(run_orca(dispatch_args))
    dispatch_id = None
    if not args.dry_run:
        dispatch_id = (dispatch.get("result") or {}).get("dispatch", {}).get("id")

    now = datetime.now(UTC).isoformat()
    loop["phase"] = PHASE_AFTER[args.to]
    loop["last_task_id"] = task_id
    loop["last_dispatch_id"] = dispatch_id
    loop["last_dispatch_to"] = args.to
    loop["last_dispatch_target_handle"] = target_handle
    loop["updated_at"] = now
    write_loop(loop_dir, loop)
    append_trace(loop_dir, f"{now} dispatch to={args.to} handle={target_handle} task={task_id} iter={iteration}")

    out = {
        "ok": True,
        "to": args.to,
        "target_handle": target_handle,
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "iteration": iteration,
        "max_iterations": max_iter,
        "dry_run": args.dry_run,
    }
    if args.dry_run:
        out["preamble_preview"] = (dispatch.get("result") or {}).get("preamble", "")[:500]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
