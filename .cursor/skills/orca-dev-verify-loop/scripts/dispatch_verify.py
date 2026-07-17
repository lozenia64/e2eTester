#!/usr/bin/env python3
"""Dispatch verify task to Claude Code via Orca orchestration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loop_state import append_trace, build_verifier_spec, read_loop, write_loop
from orca_cli import configure_stdout_utf8, require_ok, run_orca

ROOT = Path(__file__).resolve().parents[4]


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


def resolve_handles(
    workspace: Path, coordinator: str | None, verifier: str | None
) -> dict[str, Any]:
    script = (
        ROOT / ".cursor" / "skills" / "orca-dev-verify-loop" / "scripts" / "resolve_terminals.py"
    )
    cmd = [sys.executable, str(script), "--workspace", str(workspace)]
    if coordinator:
        cmd.extend(["--coordinator", coordinator])
    if verifier:
        cmd.extend(["--verifier", verifier])
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
    return data


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Dispatch verify task to Claude Code")
    parser.add_argument("--loop-dir", required=True)
    parser.add_argument("--coordinator", default=None)
    parser.add_argument("--verifier", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    loop_dir = Path(args.loop_dir).resolve()
    loop = read_loop(loop_dir)
    workspace = Path(loop["workspace"])
    iteration = int(loop.get("iteration") or 0) + 1
    max_iter = int(loop.get("max_iterations") or 3)
    if iteration > max_iter:
        print(json.dumps({"error": f"max verify iterations ({max_iter}) exceeded"}))
        return 1

    handles = resolve_handles(workspace, args.coordinator, args.verifier)
    verifier_handle = str(handles["verifier"]["handle"])
    coordinator_handle = str(handles["coordinator"]["handle"])

    loop["changed_files"] = git_changed_files(workspace)
    loop["iteration"] = iteration
    loop["status"] = "verifying"
    loop["verifier_handle"] = verifier_handle
    loop["coordinator_handle"] = coordinator_handle
    loop["updated_at"] = datetime.now(UTC).isoformat()
    write_loop(loop_dir, loop)

    spec = build_verifier_spec(loop, iteration=iteration)
    title = f"verify-{loop['loop_id']}-{iteration}"

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
                f"Verify {iteration}/{max_iter}",
                "--json",
            ]
        )
    )
    task_id = create["result"]["task"]["id"]

    dispatch_args = [
        "orchestration",
        "dispatch",
        "--task",
        task_id,
        "--to",
        verifier_handle,
        "--from",
        coordinator_handle,
        "--json",
    ]
    if args.dry_run:
        dispatch_args.append("--dry-run")
        dispatch_args.append("--return-preamble")
    else:
        dispatch_args.append("--inject")

    dispatch = require_ok(run_orca(dispatch_args))
    dispatch_id = None
    if not args.dry_run:
        dispatch_id = (dispatch.get("result") or {}).get("dispatch", {}).get("id")

    loop["last_task_id"] = task_id
    loop["last_dispatch_id"] = dispatch_id
    write_loop(loop_dir, loop)
    append_trace(loop_dir, f"{loop['updated_at']} dispatch task={task_id} to={verifier_handle}")

    out = {
        "ok": True,
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "iteration": iteration,
        "verifier_handle": verifier_handle,
        "coordinator_handle": coordinator_handle,
        "dry_run": args.dry_run,
    }
    if args.dry_run:
        out["preamble_preview"] = (dispatch.get("result") or {}).get("preamble", "")[:500]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
