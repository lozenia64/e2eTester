#!/usr/bin/env python3
"""Append a handoff event to trace.log and handoffs.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Record orchestration handoff")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    parser.add_argument("--from-agent", required=True, help="Source agent skill name")
    parser.add_argument("--to-agent", required=True, help="Target agent skill name")
    parser.add_argument("--reason", default="", help="Handoff reason")
    parser.add_argument("--status", default="ok", help="ok | retry | backtrack")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    now = datetime.now(UTC).isoformat()
    event = {
        "timestamp": now,
        "from_agent": args.from_agent,
        "to_agent": args.to_agent,
        "reason": args.reason,
        "status": args.status,
    }

    handoffs_path = run_dir / "handoffs.jsonl"
    with handoffs_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    trace_path = run_dir / "trace.log"
    line = f"[{now}] handoff {args.from_agent} -> {args.to_agent} ({args.status})"
    if args.reason:
        line += f": {args.reason}"
    with trace_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    print(json.dumps({"recorded": True, "event": event}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
