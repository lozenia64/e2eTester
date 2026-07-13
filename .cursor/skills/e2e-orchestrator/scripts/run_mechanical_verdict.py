#!/usr/bin/env python3
"""Compute mechanical verdict from gate/QC reports (no LLM)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from orchestration_gates import compute_mechanical_verdict  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run e2e mechanical verdict (T3)")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not (run_dir / "run.json").is_file():
        print(json.dumps({"error": "run.json not found"}))
        return 1

    result = compute_mechanical_verdict(run_dir)
    report = {
        **result,
        "ran_at": datetime.now(UTC).isoformat(),
    }
    out_path = run_dir / "mechanical-verdict.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "path": str(out_path)}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
