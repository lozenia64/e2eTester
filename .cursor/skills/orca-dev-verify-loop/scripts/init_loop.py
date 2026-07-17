#!/usr/bin/env python3
"""Initialize an Orca dev-verify loop session."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orca_cli import configure_stdout_utf8

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / ".cursor" / "orchestration" / "orca-loop.config.json"

LOOP_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


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
        merged = list(dict.fromkeys(names + staged + untracked))
        return merged
    except OSError:
        return []


def load_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Initialize Orca dev-verify loop")
    parser.add_argument("workspace", help="Project workspace root")
    parser.add_argument("user_request", help="Development goal")
    parser.add_argument("--loop-id", default=None, help="Optional 8-char hex loop id")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if args.loop_id is not None:
        if not LOOP_ID_PATTERN.fullmatch(args.loop_id):
            print(json.dumps({"error": "loop-id must be 8 lowercase hex chars"}))
            return 1
        loop_id = args.loop_id
    else:
        loop_id = str(uuid.uuid4())[:8]

    loop_dir = workspace / ".cursor" / "orchestration" / "loops" / loop_id
    loop_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(Path(args.config))
    now = datetime.now(UTC).isoformat()
    loop_json: dict[str, Any] = {
        "loop_id": loop_id,
        "loop_dir": str(loop_dir),
        "workspace": str(workspace),
        "user_request": args.user_request,
        "status": "developing",
        "pattern": "orca_dev_verify_loop",
        "orchestrator": "orca-dev-verify-loop",
        "iteration": 0,
        "max_iterations": int(config.get("max_verify_iterations") or 3),
        "gates_profile": config.get("gates_profile", "full"),
        "gates_command": config.get(
            "gates_command", "python3 scripts/ci/run_all_gates.py --profile full"
        ),
        "changed_files": git_changed_files(workspace),
        "verifier_handle": None,
        "coordinator_handle": None,
        "last_task_id": None,
        "last_dispatch_id": None,
        "last_verdict": None,
        "history": [],
        "created_at": now,
        "updated_at": now,
    }

    (loop_dir / "loop.json").write_text(
        json.dumps(loop_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    trace = loop_dir / "trace.log"
    trace.write_text(f"{now} init loop_id={loop_id}\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "loop_id": loop_id,
                "loop_dir": str(loop_dir),
                "workspace": str(workspace),
                "max_iterations": loop_json["max_iterations"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
