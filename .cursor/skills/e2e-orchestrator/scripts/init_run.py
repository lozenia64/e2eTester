#!/usr/bin/env python3
"""Initialize an e2e-orchestrator run directory and run.json."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize e2e orchestration run")
    parser.add_argument("workspace", help="Project workspace root (absolute path)")
    parser.add_argument("user_request", help="Original user request")
    parser.add_argument("--run-id", default=None, help="Optional run ID (uuid prefix)")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    run_id = args.run_id or str(uuid.uuid4())[:8]
    run_dir = workspace / ".cursor" / "orchestration" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC).isoformat()
    run_json = {
        "run_id": run_id,
        "workspace": str(workspace),
        "run_dir": str(run_dir),
        "user_request": args.user_request,
        "status": "running",
        "pipeline_profile": None,
        "current_agent": None,
        "agent_graph": [],
        "context_variables": {
            "system_code": None,
            "layer": None,
            "touch_surfaces": [],
            "affected_modules": [],
            "risk_flags": [],
            "conditional_agents": [],
        },
        "attempts": {},
        "total_iterations": 0,
        "max_retries_per_agent": 2,
        "max_total_iterations": 10,
        "created_at": now,
        "updated_at": now,
    }

    run_path = run_dir / "run.json"
    run_path.write_text(json.dumps(run_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    trace_path = run_dir / "trace.log"
    if not trace_path.exists():
        trace_path.write_text(f"[{now}] e2e run initialized\n", encoding="utf-8")

    handoffs_path = run_dir / "handoffs.jsonl"
    if not handoffs_path.exists():
        handoffs_path.write_text("", encoding="utf-8")

    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "run_json": str(run_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
