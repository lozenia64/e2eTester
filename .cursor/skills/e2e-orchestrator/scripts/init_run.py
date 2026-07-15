#!/usr/bin/env python3
"""Initialize an e2e-orchestrator run directory and run.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def normalize_run_id(run_id: str) -> str | None:
    """Return run_id if safe (8 lowercase hex chars), else None."""
    if RUN_ID_PATTERN.fullmatch(run_id):
        return run_id
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize e2e orchestration run")
    parser.add_argument("workspace", help="Project workspace root (absolute path)")
    parser.add_argument("user_request", help="Original user request")
    parser.add_argument("--run-id", default=None, help="Optional run ID (8 hex chars)")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if args.run_id is not None:
        run_id = normalize_run_id(args.run_id)
        if run_id is None:
            print(json.dumps({"error": "run-id must be exactly 8 lowercase hex characters"}))
            return 1
    else:
        run_id = str(uuid.uuid4())[:8]
    run_dir = workspace / ".cursor" / "orchestration" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC).isoformat()
    run_json = {
        "run_id": run_id,
        "workspace": str(workspace),
        "run_dir": str(run_dir),
        "user_request": args.user_request,
        "status": "running",
        "orchestrator": "e2e-orchestrator",
        "orchestrator_version": "2.0",
        "pipeline_profile": None,
        "e2e_pipeline_profile": None,
        "dev_pipeline_profile": None,
        "current_agent": None,
        "agent_graph": [],
        "qc_agents": [],
        "ship_agents": [],
        "ship_requested": False,
        "ship_eligible": False,
        "last_planner": None,
        "skip_research": False,
        "stop_after_research": False,
        "implementer": None,
        "agent_graph_resolved_at": None,
        "context_variables": {
            "system_code": None,
            "layer": None,
            "touch_surfaces": [],
            "affected_modules": [],
            "risk_flags": [],
            "conditional_agents": [],
        },
        "attempts": {},
        "gate_attempts": {"preflight": 0, "full_ci": 0, "planning": 0, "research": 0},
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
